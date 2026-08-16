#!/usr/bin/env bash
# shellcheck disable=SC2153
set -euo pipefail

readonly APP_DIR="/app"
readonly MODEL_CONFIG="${APP_DIR}/config/model.env"
readonly PROFILE_CONFIG="${APP_DIR}/config/profiles/${PROFILE:-baseline}.env"

die() {
  echo "error: $*" >&2
  exit 1
}

[[ -r "$MODEL_CONFIG" ]] || die "missing model config: $MODEL_CONFIG"
[[ -r "$PROFILE_CONFIG" ]] || die "unknown profile: ${PROFILE:-baseline}"

# shellcheck disable=SC1090
source "$MODEL_CONFIG"
# shellcheck disable=SC1090
source "$PROFILE_CONFIG"

: "${LLAMA_API_KEY:?LLAMA_API_KEY must be set to a fresh per-worker secret}"
[[ "$LLAMA_API_KEY" != "replace-with-random-per-worker-key" ]] || die "replace the example API key"

readonly MODEL_DIR="${MODEL_DIR:-/models}"
readonly RESULTS_DIR="${RESULTS_DIR:-/results}"
readonly LLAMA_HOST="${LLAMA_HOST:-0.0.0.0}"
readonly LLAMA_PORT="${LLAMA_PORT:-8000}"
mkdir -p "$MODEL_DIR" "$RESULTS_DIR"

download_artifact() {
  local repo="$1" revision="$2" file="$3" expected_size="$4" expected_sha="$5"
  local destination="${MODEL_DIR}/${file}"
  local partial="${destination}.partial"
  local actual_size actual_sha

  if [[ -f "$destination" ]]; then
    actual_size="$(stat -c %s "$destination")"
    if [[ "$actual_size" == "$expected_size" ]]; then
      actual_sha="$(sha256sum "$destination" | awk '{print $1}')"
      if [[ "$expected_sha" == "0" || "$actual_sha" == "$expected_sha" ]]; then
        echo "artifact-ready file=$file bytes=$actual_size sha256=$actual_sha"
        return
      fi
    fi
    die "existing artifact failed integrity check: $destination"
  fi

  echo "artifact-download repo=$repo revision=$revision file=$file bytes=$expected_size"
  curl --fail --location --retry 8 --retry-all-errors --continue-at - \
    --output "$partial" \
    "https://huggingface.co/${repo}/resolve/${revision}/${file}"

  actual_size="$(stat -c %s "$partial")"
  [[ "$actual_size" == "$expected_size" ]] || die "$file size mismatch: $actual_size != $expected_size"
  actual_sha="$(sha256sum "$partial" | awk '{print $1}')"
  [[ "$expected_sha" == "0" || "$actual_sha" == "$expected_sha" ]] \
    || die "$file sha256 mismatch: $actual_sha != $expected_sha"
  mv "$partial" "$destination"
  echo "artifact-ready file=$file bytes=$actual_size sha256=$actual_sha"
}

download_artifact "$MODEL_REPO" "$MODEL_REVISION" "$MODEL_FILE" "$MODEL_SIZE_BYTES" "$MODEL_SHA256"

if [[ "$SPECULATIVE_ENABLED" == "true" ]]; then
  download_artifact "$MODEL_REPO" "$MODEL_REVISION" "$MTP_FILE" "$MTP_SIZE_BYTES" "$MTP_SHA256"
fi

command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi is unavailable; GPU runtime was not attached"
gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)"
gpu_total_mib="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | xargs)"
[[ "$gpu_total_mib" =~ ^[0-9]+$ ]] || die "invalid GPU memory value from nvidia-smi: $gpu_total_mib"
(( gpu_total_mib >= 23000 )) || die "profile requires a 24 GB-class GPU; found ${gpu_name} (${gpu_total_mib} MiB)"

jq -n \
  --arg profile "${PROFILE:-baseline}" \
  --arg description "$PROFILE_DESCRIPTION" \
  --arg model "$MODEL_ID" \
  --arg model_repo "$MODEL_REPO" \
  --arg model_revision "$MODEL_REVISION" \
  --arg model_file "$MODEL_FILE" \
  --arg model_sha256 "$MODEL_SHA256" \
  --arg gpu_name "$gpu_name" \
  --argjson gpu_total_mib "$gpu_total_mib" \
  --argjson context_size "$LLAMA_CONTEXT_SIZE" \
  --arg cache_type_k "$LLAMA_CACHE_TYPE_K" \
  --arg cache_type_v "$LLAMA_CACHE_TYPE_V" \
  --arg flash_attention "$LLAMA_FLASH_ATTN" \
  --arg gpu_layers "$LLAMA_GPU_LAYERS" \
  --argjson parallel "$LLAMA_PARALLEL" \
  --argjson batch_size "$LLAMA_BATCH_SIZE" \
  --argjson ubatch_size "$LLAMA_UBATCH_SIZE" \
  --argjson threads "$LLAMA_THREADS" \
  --argjson speculative_enabled "$SPECULATIVE_ENABLED" \
  --arg speculative_type "${SPECULATIVE_TYPE:-none}" \
  --arg mtp_file "${MTP_FILE:-}" \
  --arg mtp_sha256 "${MTP_SHA256:-}" \
  --argjson speculative_draft_tokens "${SPECULATIVE_DRAFT_TOKENS:-0}" \
  --arg speculative_draft_cache_type_k "${SPECULATIVE_DRAFT_CACHE_TYPE_K:-none}" \
  --arg speculative_draft_cache_type_v "${SPECULATIVE_DRAFT_CACHE_TYPE_V:-none}" \
  --arg llama_cpp_release "${LLAMA_CPP_RELEASE:-b10453}" \
  --arg llama_cpp_commit "${LLAMA_CPP_COMMIT:-3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70}" \
  '{profile:$profile,profile_description:$description,model:$model,model_repo:$model_repo,
    model_revision:$model_revision,model_file:$model_file,model_sha256:$model_sha256,
    gpu:{name:$gpu_name,total_mib:$gpu_total_mib},context_size:$context_size,
    backend:{name:"llama.cpp",release:$llama_cpp_release,commit:$llama_cpp_commit,gpu_layers:$gpu_layers,
      flash_attention:$flash_attention,cache_type_k:$cache_type_k,cache_type_v:$cache_type_v,
      parallel:$parallel,batch_size:$batch_size,ubatch_size:$ubatch_size,threads:$threads,
      automatic_fit:false,multimodal_projector:false,jinja_tool_calling:true,unified_kv:true},
    speculative:{enabled:$speculative_enabled,type:$speculative_type,draft_file:$mtp_file,
      draft_sha256:$mtp_sha256,draft_tokens:$speculative_draft_tokens,
      draft_cache_type_k:$speculative_draft_cache_type_k,
      draft_cache_type_v:$speculative_draft_cache_type_v}}' \
  > "${RESULTS_DIR}/effective-config.json"

args=(
  --model "${MODEL_DIR}/${MODEL_FILE}"
  --alias "$MODEL_ID"
  --host "$LLAMA_HOST"
  --port "$LLAMA_PORT"
  --ctx-size "$LLAMA_CONTEXT_SIZE"
  --parallel "$LLAMA_PARALLEL"
  --batch-size "$LLAMA_BATCH_SIZE"
  --ubatch-size "$LLAMA_UBATCH_SIZE"
  --threads "$LLAMA_THREADS"
  --n-gpu-layers "$LLAMA_GPU_LAYERS"
  --flash-attn "$LLAMA_FLASH_ATTN"
  --cache-type-k "$LLAMA_CACHE_TYPE_K"
  --cache-type-v "$LLAMA_CACHE_TYPE_V"
  --no-mmproj
  --fit off
  --kv-unified
  --jinja
  --chat-template-kwargs '{"preserve_thinking":true}'
  --metrics
  --slots
  --cache-prompt
  --perf
)

if [[ "$SPECULATIVE_ENABLED" == "true" ]]; then
  args+=(
    --spec-type "$SPECULATIVE_TYPE"
    --spec-draft-model "${MODEL_DIR}/${MTP_FILE}"
    --spec-draft-n-max "$SPECULATIVE_DRAFT_TOKENS"
    --spec-draft-ngl "$SPECULATIVE_DRAFT_GPU_LAYERS"
    --spec-draft-type-k "$SPECULATIVE_DRAFT_CACHE_TYPE_K"
    --spec-draft-type-v "$SPECULATIVE_DRAFT_CACHE_TYPE_V"
  )
fi

echo "server-start profile=${PROFILE:-baseline} model=$MODEL_ID gpu=$gpu_name context=$LLAMA_CONTEXT_SIZE speculative=$SPECULATIVE_ENABLED"
exec llama-server "${args[@]}"
