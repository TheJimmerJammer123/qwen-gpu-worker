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

Artifact hashes in `config/model.env` were taken from Hugging Face's pinned
revision response (`x-linked-etag`, the LFS SHA-256) and are rechecked after each
download.
