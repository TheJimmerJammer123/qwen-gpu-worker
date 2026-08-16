#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly root
mode="${1:-source}"

pass() { echo "pass: $*"; }
fail() { echo "fail: $*" >&2; }
need() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "command $1"
  else
    fail "missing command: $1"
    return 1
  fi
}

case "$mode" in
  source|build|gpu|client) ;;
  *) echo "usage: $0 source|build|gpu|client" >&2; exit 2 ;;
esac

failures=0
for command in bash git jq python3 shellcheck; do
  need "$command" || failures=$((failures + 1))
done

for path in \
  Dockerfile compose.yaml config/model.env \
  config/profiles/baseline.env config/profiles/optimized.env; do
  if [[ -r "${root}/${path}" ]]; then
    pass "readable ${path}"
  else
    fail "missing ${path}"
    failures=$((failures + 1))
  fi
done

if [[ "$mode" != "source" ]]; then
  if [[ -n "$(git -C "$root" status --porcelain --untracked-files=all)" ]]; then
    fail "prototype worktree has uncommitted or untracked changes"
    failures=$((failures + 1))
  else
    pass "prototype tracked worktree is clean"
  fi
fi

if [[ "$mode" == "build" || "$mode" == "gpu" ]]; then
  need docker || failures=$((failures + 1))
  if command -v docker >/dev/null 2>&1; then
    if docker buildx version >/dev/null 2>&1; then
      pass "Docker Buildx"
    else
      fail "Docker Buildx is unavailable"
      failures=$((failures + 1))
    fi
    if docker compose version >/dev/null 2>&1; then
      pass "Docker Compose"
    else
      fail "Docker Compose is unavailable"
      failures=$((failures + 1))
    fi
  fi
fi

if [[ "$mode" == "gpu" ]]; then
  need nvidia-smi || failures=$((failures + 1))
  if command -v nvidia-smi >/dev/null 2>&1; then
    gpu_line="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | head -1 || true)"
    gpu_name="${gpu_line%,*}"
    gpu_memory="${gpu_line##*,}"
    gpu_memory="${gpu_memory//[[:space:]]/}"
    if [[ "$gpu_memory" =~ ^[0-9]+$ ]] && (( gpu_memory >= 23000 )); then
      pass "24 GB-class GPU: ${gpu_name} (${gpu_memory} MiB)"
    else
      fail "a 24 GB-class NVIDIA GPU is required; found ${gpu_line:-none}"
      failures=$((failures + 1))
    fi
  fi
fi

if [[ "$mode" == "client" ]]; then
  need qwen || failures=$((failures + 1))
  sandbox_provider="${QWEN_SANDBOX_PROVIDER:-docker}"
  need "$sandbox_provider" || failures=$((failures + 1))
  quarantine_marker="${QWEN_QUARANTINE_MARKER:-${root}/../work/qwen.disabled}"
  if [[ -e "$quarantine_marker" ]]; then
    fail "Qwen is quarantined by ${quarantine_marker}; rotate the affected credential before use"
    failures=$((failures + 1))
  else
    pass "no Qwen quarantine marker"
    expected_qwen_version="${QWEN_CODE_VERSION:-0.21.1}"
    actual_qwen_version="$(qwen --version 2>/dev/null | head -1 || true)"
    if [[ "$actual_qwen_version" == *"${expected_qwen_version}"* ]]; then
      pass "Qwen Code ${expected_qwen_version}"
    else
      fail "expected Qwen Code ${expected_qwen_version}; found ${actual_qwen_version:-unknown}"
      failures=$((failures + 1))
    fi
  fi
fi

if (( failures > 0 )); then
  echo "preflight failed with ${failures} issue(s)" >&2
  exit 1
fi
echo "preflight complete: ${mode}"
