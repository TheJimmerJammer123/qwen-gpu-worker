# Codex worker integration research

Checked 2026-08-16 against Codex CLI 0.147.0 and llama.cpp `b10453`.

## What is supported

Official Codex configuration supports custom model providers and custom agent
files. A provider can set a base URL and environment-supplied key, but the only
supported wire protocol is the Responses API. A custom agent can select that
provider, model, sandbox, and its own developer instructions.

llama.cpp `b10453` exposes `/v1/responses`. Direct non-agent responses, SSE
streaming, and ordinary function calls all passed against the RunPod server.
That is necessary but not sufficient for a full Codex worker.

## Reproduced incompatibilities

A real ephemeral `codex exec` request failed before generation:

1. Codex serialized configured tool groups as `type: "namespace"`; llama.cpp
   warned that each namespace and `web_search` tool was unsupported and skipped.
2. The Responses-to-Chat conversion left a system/developer message ordering that
   Qwen's template rejects with `System message must be at the beginning`.
3. llama.cpp's standard `/v1/models` response does not match Codex's undocumented
   richer model-catalog schema, so Codex logs a fallback-metadata warning.

These exact classes are independently reported by Codex and llama.cpp users.
The Codex-side request for a `namespace_tools = false` compatibility capability
remains open. llama.cpp users report successful local Qwen coding only after a
two-way proxy flattens namespace tools into uniquely named functions and restores
the namespace on returned calls. Other users also merge system/developer messages
into one leading instruction block and provide an explicit Codex model catalog.

## Current vLLM alternative

Current vLLM documentation now includes a dedicated Codex backend integration and
implements the Responses API. Its Qwen examples enable both automatic tool choice
and the Qwen reasoning/tool parsers. That makes a pinned vLLM experiment a valid
native-route candidate; it is stronger evidence than copying the older Unsloth
profile snippet unchanged.

The commonly circulated recipe is still incomplete for this prototype. A plain
`vllm serve ... --trust-remote-code` command omits `--enable-auto-tool-choice`,
`--tool-call-parser qwen3_coder`, and `--reasoning-parser qwen3`. Current Codex
provider configuration is TOML with a provider block and `wire_api = "responses"`,
not the pasted `~/.config/codex/profiles.json` shape. Most importantly, the route
must reproduce namespace and custom-tool calls before it can replace the bounded
Qwen Code worker. The existing llama.cpp failure proves that exposing
`/v1/responses` alone is insufficient.

The hardware claim is also a deployment choice, not a prerequisite. FP8 on a
48-80 GB GPU may preserve more model quality and KV headroom, but this prototype
already measured the pinned Q4_K_M target at 32K and 64K fully resident on one
24 GB RTX 3090. Do not discard that economic baseline until a comparable FP8
quality/cost run justifies it.

## Practical community patterns

### 1. Headless Qwen Code as an external worker — recommended first

Projects integrating Qwen today commonly launch Qwen Code as a bounded subprocess
in a dedicated Git worktree. The wrapper scrubs the environment, uses a scratch
`QWEN_HOME`, applies an OS sandbox and timeout, validates the resulting diff, and
returns a structured report to the orchestrator. Codex stays outside that process
as reviewer and owner of commits/pushes.

This matches the prototype already built here and avoids translating Codex's
private tool shapes. It is the shortest path to a useful nightly bulk worker.

### 2. Responses compatibility proxy — viable second phase

For a native Codex custom agent, community workarounds place a loopback-only proxy
between Codex and llama.cpp. A complete adapter needs to:

- flatten and reversibly restore namespace tools;
- translate custom/freeform tools such as native `apply_patch` into functions and
  restore their response events;
- coalesce system/developer history into leading instructions;
- preserve Responses SSE framing and tool-call history;
- serve or configure a compatible model catalog and context/compaction metadata;
- inject the upstream key without writing it to Codex configuration.

There is a new MIT project implementing this larger surface, but it was created on
the day of this research and has no adoption evidence yet. Treat it as design
reference or audit input, not a dependency to install blindly.

### 3. Patched Codex or llama.cpp forks — not recommended for phase 1

Users have published branches that add provider capability flags in Codex or
reversible namespace handling in llama.cpp. They report working Qwen sessions,
but the relevant upstream issues remain open and one llama.cpp proposal was
closed as stale. Carrying either fork would add maintenance risk before coding
quality has been established.

## Recommendation

Register this prototype operationally as a **Qwen Code subprocess worker invoked
by Codex**, reusing the existing worktree/checkpoint harness. Do not replace the
current native Bailian-backed `qwen_worker` yet. After the real repository task
passes review, add a distinct self-hosted worker route with explicit availability
checks and fallback to Codex review.

Evaluate a native custom-agent adapter only after that path is producing valuable
nightly diffs. In parallel, a pinned current-vLLM native integration test is now
reasonable and may avoid a custom adapter. If an adapter remains necessary,
implement the smallest audited loopback proxy against captured Codex 0.147.0
fixtures and pin both Codex and the inference backend versions.

## Primary references

- Official Codex configuration reference:
  <https://developers.openai.com/codex/config-reference/>
- Official Codex custom agents guide:
  <https://developers.openai.com/codex/subagents/>
- Codex namespace-flattening request and tested branch:
  <https://github.com/openai/codex/issues/26234>
- Codex llama-server compatibility report and production proxy description:
  <https://github.com/openai/codex/issues/36942>
- Codex standard `/models` catalog incompatibility:
  <https://github.com/openai/codex/issues/37122>
- llama.cpp namespace-tool issue and working Qwen reports:
  <https://github.com/ggml-org/llama.cpp/issues/24295>
- Unsloth user's end-to-end Qwen/Codex proxy reproduction:
  <https://github.com/unslothai/unsloth/issues/5141>
- Official vLLM Codex integration:
  <https://docs.vllm.ai/en/latest/serving/integrations/codex/>
- Official vLLM OpenAI-compatible serving reference:
  <https://docs.vllm.ai/en/latest/serving/online_serving/>
- Unsloth discussion of current Codex provider/profile syntax:
  <https://github.com/unslothai/unsloth/issues/6003>
- Headless Qwen Code worker implementation report:
  <https://github.com/procoders/superpowers-v/pull/8>
- Emerging full Responses adapter (audit before reuse):
  <https://github.com/madmax24-ubuntu/codex-proxy-llama.cpp>
