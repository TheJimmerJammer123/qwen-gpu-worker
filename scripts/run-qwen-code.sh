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

mkdir -p "$qwen_home" "$runtime_dir"
jq --arg base_url "${QWEN_GPU_BASE_URL%/}" \
  --argjson context_size "${QWEN_CONTEXT_SIZE:-32768}" \
  '.modelProviders.openai[0].baseUrl = $base_url
   | .modelProviders.openai[0].generationConfig.contextWindowSize = $context_size' \
  "${project_root}/config/qwen-settings.template.json" > "${qwen_home}/settings.json"
chmod 700 "$qwen_home" "$runtime_dir"
chmod 600 "${qwen_home}/settings.json"

cd "$repository"
exec env -i \
  HOME="$HOME" \
  USER="${USER:-worker}" \
  PATH="$PATH" \
  LANG="${LANG:-C.UTF-8}" \
  QWEN_HOME="$qwen_home" \
  QWEN_RUNTIME_DIR="$runtime_dir" \
  OPENAI_API_KEY="$QWEN_GPU_API_KEY" \
  QWEN_SANDBOX="$sandbox_provider" \
  QWEN_CODE_SUPPRESS_YOLO_WARNING=1 \
  "$qwen_binary" \
  -p "$(<"$prompt_file")" \
  --model Qwen3.8-27B-Q4_K_M \
  --sandbox \
  --approval-mode yolo \
  --output-format json \
  --max-session-turns 45 \
  --max-tool-calls 60 \
  --max-wall-time 30m \
  --exclude-tools agent \
  --disabled-slash-commands auth,mcp,extensions
