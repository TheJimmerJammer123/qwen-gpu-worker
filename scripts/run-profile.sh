#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly root
profile="${1:-}"
case "$profile" in
  baseline|optimized) ;;
  *) echo "usage: $0 baseline|optimized" >&2; exit 2 ;;
esac

: "${LLAMA_API_KEY:?set a fresh disposable LLAMA_API_KEY}"
: "${GPU_HOURLY_COST_USD:?set the displayed GPU hourly price}"
[[ "$GPU_HOURLY_COST_USD" =~ ^[0-9]+([.][0-9]+)?$ ]] \
  || { echo "error: GPU_HOURLY_COST_USD must be numeric" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker is required" >&2; exit 127; }

export PROFILE="$profile"
startup_timeout="${STARTUP_TIMEOUT_SECONDS:-2700}"
poll_seconds="${STARTUP_POLL_SECONDS:-10}"
started_epoch="$(date +%s)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "${root}/results"

record_allocation() {
  status=$?
  trap - EXIT
  allocated_seconds=$(($(date +%s) - started_epoch))
  if (( status == 0 )); then succeeded=true; else succeeded=false; fi
  jq -cn \
    --arg profile "$profile" \
    --arg started_at "$started_at" \
    --argjson allocated_seconds "$allocated_seconds" \
    --argjson hourly_cost "$GPU_HOURLY_COST_USD" \
    --argjson success "$succeeded" \
    '{profile:$profile,started_at:$started_at,success:$success,
      controlled_allocation_seconds:$allocated_seconds,
      controlled_gpu_hours:($allocated_seconds / 3600),
      controlled_estimated_cost_usd:(($allocated_seconds / 3600) * $hourly_cost),
      hourly_cost_usd:$hourly_cost,
      scope:"compose-runner only; excludes provider time before and after this script"}' \
    >> "${root}/results/allocations.jsonl"
  exit "$status"
}
trap record_allocation EXIT

cd "$root"
docker compose up -d --force-recreate qwen-server

healthy=false
while (( $(date +%s) - started_epoch < startup_timeout )); do
  if docker compose exec -T qwen-server /app/scripts/healthcheck.sh >/dev/null 2>&1; then
    healthy=true
    break
  fi
  if ! docker compose ps --status running --services | grep -qx qwen-server; then
    break
  fi
  sleep "$poll_seconds"
done

finished_epoch="$(date +%s)"
startup_seconds=$((finished_epoch - started_epoch))
jq -cn \
  --arg profile "$profile" \
  --arg started_at "$started_at" \
  --argjson startup_seconds "$startup_seconds" \
  --argjson healthy "$healthy" \
  '{profile:$profile,started_at:$started_at,startup_seconds:$startup_seconds,healthy:$healthy}' \
  >> "${root}/results/startups.jsonl"

if [[ "$healthy" != "true" ]]; then
  docker compose logs --no-color qwen-server > "${root}/results/${profile}-startup-failure.log" 2>&1 || true
  echo "error: ${profile} did not become healthy; evidence saved under results/" >&2
  exit 1
fi

docker compose exec -T \
  -e "BENCHMARK_REPEATS=${BENCHMARK_REPEATS:-3}" \
  -e "BENCHMARK_MAX_TOKENS=${BENCHMARK_MAX_TOKENS:-512}" \
  qwen-server /app/scripts/run-benchmark.sh "$profile"

docker compose cp qwen-server:/results/benchmarks.jsonl "${root}/results/benchmarks.jsonl"
python3 "${root}/scripts/summarize-benchmarks.py" "${root}/results/benchmarks.jsonl" \
  > "${root}/results/benchmark-summary.json"
echo "profile complete: ${profile}; results/benchmark-summary.json"
