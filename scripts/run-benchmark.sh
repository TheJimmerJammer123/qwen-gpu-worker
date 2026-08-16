#!/usr/bin/env bash
set -euo pipefail

profile="${1:-baseline}"
case "$profile" in
  baseline) context_size=32768; target_input_tokens="${BENCHMARK_TARGET_INPUT_TOKENS:-30000}" ;;
  optimized) context_size=65536; target_input_tokens="${BENCHMARK_TARGET_INPUT_TOKENS:-60000}" ;;
  *) echo "usage: $0 baseline|optimized" >&2; exit 2 ;;
esac

export QWEN_GPU_API_KEY="${QWEN_GPU_API_KEY:-${LLAMA_API_KEY:-}}"
: "${QWEN_GPU_API_KEY:?set QWEN_GPU_API_KEY or run inside the server container}"
exec python3 /app/scripts/benchmark.py \
  --profile "$profile" \
  --context-size "$context_size" \
  --endpoint "${QWEN_GPU_BASE_URL:-http://127.0.0.1:8000/v1}" \
  --output "${BENCHMARK_OUTPUT:-/results/benchmarks.jsonl}" \
  --repeat "${BENCHMARK_REPEATS:-3}" \
  --max-tokens "${BENCHMARK_MAX_TOKENS:-512}" \
  --target-input-tokens "$target_input_tokens" \
  --max-attempts "${BENCHMARK_MAX_ATTEMPTS:-2}" \
  --hourly-cost "${GPU_HOURLY_COST_USD:-0}"
