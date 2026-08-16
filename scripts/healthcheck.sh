#!/usr/bin/env bash
set -euo pipefail

: "${LLAMA_API_KEY:?LLAMA_API_KEY is required}"
curl --fail --silent --show-error --max-time 5 \
  -H "Authorization: Bearer ${LLAMA_API_KEY}" \
  "http://127.0.0.1:${LLAMA_PORT:-8000}/v1/models" \
  | jq -e '.data | length > 0' >/dev/null
