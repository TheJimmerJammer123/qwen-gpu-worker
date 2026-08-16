#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly root

finish() {
  status=$?
  trap - EXIT
  "${root}/scripts/collect-evidence.sh" || true
  if [[ "${KEEP_SERVER:-false}" != "true" ]]; then
    docker compose -f "${root}/compose.yaml" down || true
  else
    echo "server retained because KEEP_SERVER=true"
  fi
  exit "$status"
}
trap finish EXIT

"${root}/scripts/run-profile.sh" baseline

if [[ "${RUN_OPTIMIZED:-true}" == "true" ]]; then
  "${root}/scripts/run-profile.sh" optimized
else
  echo "optimized profile skipped because RUN_OPTIMIZED=${RUN_OPTIMIZED:-false}"
fi
