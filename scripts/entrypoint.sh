#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" == "0" ]]; then
  mkdir -p "${MODEL_DIR:-/models}" "${RESULTS_DIR:-/results}"
  chown worker:worker "${MODEL_DIR:-/models}" "${RESULTS_DIR:-/results}"
  exec gosu worker /app/scripts/serve.sh "$@"
fi

[[ -w "${MODEL_DIR:-/models}" ]] || { echo "error: model directory is not writable" >&2; exit 1; }
[[ -w "${RESULTS_DIR:-/results}" ]] || { echo "error: results directory is not writable" >&2; exit 1; }
exec /app/scripts/serve.sh "$@"
