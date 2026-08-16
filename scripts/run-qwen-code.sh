#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 REPOSITORY PROMPT_FILE" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
repository="$(realpath "$1")"
prompt_file="$(realpath "$2")"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly repository prompt_file project_root
readonly qwen_home="${QWEN_PROTOTYPE_HOME:-${project_root}/.qwen-home}"
readonly runtime_dir="${QWEN_PROTOTYPE_RUNTIME_DIR:-${project_root}/.runtime}"

[[ -d "$repository/.git" || -f "$repository/.git" ]] || { echo "error: not a git worktree: $repository" >&2; exit 2; }
[[ -r "$prompt_file" ]] || { echo "error: unreadable prompt: $prompt_file" >&2; exit 2; }
: "${QWEN_GPU_API_KEY:?set QWEN_GPU_API_KEY to the disposable server key}"
: "${QWEN_GPU_BASE_URL:?set QWEN_GPU_BASE_URL, including /v1}"
command -v qwen >/dev/null || { echo "error: qwen not found" >&2; exit 127; }
qwen_binary="$(command -v qwen)"
readonly qwen_binary
readonly sandbox_provider="${QWEN_SANDBOX_PROVIDER:-docker}"
command -v "$sandbox_provider" >/dev/null \
  || { echo "error: Qwen Code sandbox provider not found: $sandbox_provider" >&2; exit 127; }
command -v python3 >/dev/null || { echo "error: python3 is required" >&2; exit 127; }

quarantine_marker="${QWEN_QUARANTINE_MARKER:-${project_root}/../work/qwen.disabled}"
[[ ! -e "$quarantine_marker" ]] \
  || { echo "error: Qwen remains quarantined by ${quarantine_marker}" >&2; exit 2; }

repository_root="$(git -C "$repository" rev-parse --show-toplevel)"
[[ "$repository_root" == "$repository" ]] \
  || { echo "error: pass the task worktree root, not a subdirectory" >&2; exit 2; }
[[ -z "$(git -C "$repository" status --porcelain --untracked-files=all)" ]] \
  || { echo "error: task worktree must start completely clean" >&2; exit 2; }
[[ -z "$(git -C "$repository" status --ignored --porcelain \
  | grep -vE '^!! \.harness(/|$)' | head -1)" ]] \
  || { echo "error: task worktree contains ignored files; use a fresh linked worktree" >&2; exit 2; }
branch="$(git -C "$repository" symbolic-ref --quiet --short HEAD)" \
  || { echo "error: task worktree cannot use detached HEAD" >&2; exit 2; }
case "$branch" in
  main|master|develop|release/*) echo "error: protected branch is not a Qwen task branch: ${branch}" >&2; exit 2 ;;
esac
branch_prefix="${QWEN_TASK_BRANCH_PREFIX:-qwen/}"
[[ "$branch" == "${branch_prefix}"* ]] \
  || { echo "error: task branch must begin with ${branch_prefix}; found ${branch}" >&2; exit 2; }
primary_worktree="$(git -C "$repository" worktree list --porcelain | awk '/^worktree / {print substr($0, 10); exit}')"
if [[ "$repository" == "$primary_worktree" && "${QWEN_ALLOW_PRIMARY_WORKTREE:-false}" != "true" ]]; then
  echo "error: use a disposable linked worktree, or explicitly set QWEN_ALLOW_PRIMARY_WORKTREE=true" >&2
  exit 2
fi

mkdir -p "$qwen_home" "$runtime_dir"
chmod 700 "$qwen_home" "$runtime_dir"
proxy_port_file="${runtime_dir}/auth-proxy-${BASHPID}.port"
qwen_output_file="${runtime_dir}/qwen-output-${BASHPID}.jsonl"
proxy_client_token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
proxy_bind_host="127.0.0.1"
proxy_client_host="127.0.0.1"
if [[ "$sandbox_provider" == "docker" ]]; then
  proxy_bind_host="$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')"
  [[ -n "$proxy_bind_host" ]] \
    || { echo "error: Docker bridge has no gateway for the local auth proxy" >&2; exit 1; }
  proxy_client_host="host.docker.internal"
fi
readonly proxy_port_file qwen_output_file proxy_client_token proxy_bind_host proxy_client_host
rm -f "$proxy_port_file" "$qwen_output_file"

# shellcheck disable=SC2329  # invoked by trap
cleanup() {
  if [[ -n "${proxy_pid:-}" ]]; then
    kill "$proxy_pid" >/dev/null 2>&1 || true
    wait "$proxy_pid" 2>/dev/null || true
  fi
  rm -f "$proxy_port_file" "$qwen_output_file"
}
trap cleanup EXIT INT TERM

UPSTREAM_BASE_URL="${QWEN_GPU_BASE_URL%/}" \
UPSTREAM_API_KEY="$QWEN_GPU_API_KEY" \
PROXY_CLIENT_TOKEN="$proxy_client_token" \
  python3 "${project_root}/scripts/auth_proxy.py" \
    --bind-host "$proxy_bind_host" --port-file "$proxy_port_file" &
proxy_pid=$!
readonly proxy_pid
for _ in $(seq 1 50); do
  [[ -s "$proxy_port_file" ]] && break
  kill -0 "$proxy_pid" >/dev/null 2>&1 || { echo "error: local auth proxy exited" >&2; exit 1; }
  sleep 0.1
done
[[ -s "$proxy_port_file" ]] || { echo "error: local auth proxy did not start" >&2; exit 1; }
local_base_url="http://${proxy_client_host}:$(<"$proxy_port_file")/v1"
probe_base_url="http://${proxy_bind_host}:$(<"$proxy_port_file")/v1"

PROBE_BASE_URL="$probe_base_url" \
PROBE_CLIENT_TOKEN="$proxy_client_token" \
  python3 - <<'PY'
import json
import os
import urllib.request

request = urllib.request.Request(
    os.environ["PROBE_BASE_URL"].rstrip("/") + "/models",
    headers={"Authorization": "Bearer " + os.environ["PROBE_CLIENT_TOKEN"]},
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
except Exception as error:
    raise SystemExit(f"error: Qwen endpoint availability probe failed: {error}") from error
if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or not payload["data"]:
    raise SystemExit("error: Qwen endpoint availability probe returned no models")
PY

jq --arg base_url "$local_base_url" \
  --argjson context_size "${QWEN_CONTEXT_SIZE:-32768}" \
  '.modelProviders.openai[0].baseUrl = $base_url
   | .modelProviders.openai[0].generationConfig.contextWindowSize = $context_size' \
  "${project_root}/config/qwen-settings.template.json" > "${qwen_home}/settings.json"
chmod 600 "${qwen_home}/settings.json"

cd "$repository"
status=0
env -i \
  HOME="$HOME" \
  USER="${USER:-worker}" \
  PATH="$PATH" \
  LANG="${LANG:-C.UTF-8}" \
  QWEN_HOME="$qwen_home" \
  QWEN_RUNTIME_DIR="$runtime_dir" \
  OPENAI_API_KEY="$proxy_client_token" \
  QWEN_SANDBOX="$sandbox_provider" \
  QWEN_CODE_SUPPRESS_YOLO_WARNING=1 \
  "$qwen_binary" \
  -p "$(<"$prompt_file")" \
  --model Qwen3.8-27B-Q4_K_M \
  --sandbox \
  --approval-mode yolo \
  --output-format stream-json \
  --max-session-turns 45 \
  --max-tool-calls 60 \
  --max-wall-time 30m \
  --exclude-tools agent \
  --disabled-slash-commands auth,mcp,extensions \
  > "$qwen_output_file" \
  || status=$?

python3 -c 'import pathlib,sys; sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' \
  "$qwen_output_file"
if [[ "$status" -eq 0 ]] && ! jq -s -e '
  map(select(.type == "result"))
  | last
  | .subtype == "success"
    and .is_error == false
    and ((.usage.input_tokens // 0) > 0)
    and ((.result // "") | contains("[API Error:") | not)
' "$qwen_output_file" >/dev/null; then
  echo "error: Qwen returned no successful model-backed result" >&2
  status=1
fi
if [[ "$status" -eq 0 ]] \
  && [[ -z "$(git -C "$repository" status --porcelain --untracked-files=all)" ]]; then
  echo "error: Qwen completed without producing a source diff" >&2
  status=1
fi
exit "$status"
