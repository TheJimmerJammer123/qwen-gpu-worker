# Verified upstream references

Checked 2026-08-16.

- Official model card and artifacts:
  <https://huggingface.co/Qwen/Qwen3.8-27B>
- llama.cpp-owned GGUF, target quant, projector, and MTP artifacts:
  <https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF>
- Pinned llama.cpp release:
  <https://github.com/ggml-org/llama.cpp/releases/tag/b10453>
- llama.cpp server flags, OpenAI endpoints, timings, metrics, and speculative
  decoding options:
  <https://github.com/ggml-org/llama.cpp/blob/b10453/tools/server/README.md>
- Qwen Code model-provider configuration:
  <https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md>
- Qwen Code settings and `QWEN_HOME`:
  <https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/settings.md>
- Qwen Code headless budgets and approval modes:
  <https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/headless.md>
- Current RunPod GPU pricing (RTX 3090 Community and Secure Cloud rates):
  <https://www.runpod.io/pricing>
- RunPod REST Pod creation contract:
  <https://docs.runpod.io/api-reference/pods/POST/pods>
- RunPod HTTP proxy/direct TCP behavior and 100-second proxy limit:
  <https://docs.runpod.io/pods/configuration/expose-ports>
- RunPod Pod lifecycle and storage behavior:
  <https://docs.runpod.io/pods/manage-pods>
- RunPod authenticated GPU stock/price query:
  <https://docs.runpod.io/sdks/graphql/manage-pods>
- Official Codex custom-provider configuration:
  <https://developers.openai.com/codex/config-reference/>
- Official Codex custom-agent configuration:
  <https://developers.openai.com/codex/subagents/>
- Current Codex/llama.cpp compatibility evidence and community workarounds:
  <https://github.com/openai/codex/issues/26234>
  <https://github.com/openai/codex/issues/36942>
  <https://github.com/ggml-org/llama.cpp/issues/24295>
  <https://github.com/unslothai/unsloth/issues/5141>

Artifact hashes in `config/model.env` were taken from Hugging Face's pinned
revision response (`x-linked-etag`, the LFS SHA-256) and are rechecked after each
download.
