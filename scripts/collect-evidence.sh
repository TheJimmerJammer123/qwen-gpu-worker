#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly root
command -v docker >/dev/null || { echo "error: docker is required" >&2; exit 127; }

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${1:-${root}/results/evidence-${timestamp}}"
mkdir -p "$destination"

git -C "$root" rev-parse HEAD > "${destination}/prototype-commit.txt"
git -C "$root" status --short --branch > "${destination}/prototype-status.txt"
docker compose -f "${root}/compose.yaml" images --format json > "${destination}/container-images.json" 2>/dev/null || true
docker compose -f "${root}/compose.yaml" logs --no-color qwen-server > "${destination}/server.log" 2>&1 || true
docker compose -f "${root}/compose.yaml" cp \
  qwen-server:/results/effective-config.json "${destination}/effective-config.json" >/dev/null 2>&1 || true
docker compose -f "${root}/compose.yaml" exec -T qwen-server \
  nvidia-smi --query-gpu=name,uuid,driver_version,memory.total \
  --format=csv,noheader > "${destination}/gpu.csv" 2>/dev/null || true

for file in allocations.jsonl benchmarks.jsonl benchmark-summary.json startups.jsonl qwen-code-task.json qwen-code-task.log; do
  if [[ -f "${root}/results/${file}" ]]; then
    cp "${root}/results/${file}" "$destination/"
  fi
done

(
  cd "$destination"
  checksum_file="$(mktemp)"
  trap 'rm -f "$checksum_file"' EXIT
  find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' \
    | sort \
    | xargs -r sha256sum \
    > "$checksum_file"
  mv "$checksum_file" SHA256SUMS
  trap - EXIT
)

echo "$destination"
