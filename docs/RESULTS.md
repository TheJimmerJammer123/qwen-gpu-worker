# Phase 1 result record

Date: 2026-08-16

## Environment inspection

- Prototype repository: `/home/jim/Documents/ChatGPT/JammerVIO/qwen`.
- JammerVIO source: `/home/jim/development/projects/dualfin/jammervio`, currently
  `develop` at `e8c654a9e8a5b2e2eaf59e64aed99f26716eaaf9` with unrelated user
  modifications. It was not changed.
- The enclosing development control-plane repository also has extensive unrelated
  changes. It was not changed.
- Local GPU: NVIDIA Quadro P2000, 5,120 MiB. It cannot run this model.
- Local Qwen Code: 0.21.1. A credential quarantine was cleared only after the
  operator explicitly authorized proceeding without verified rotation. No older
  credential was read or reused; the exception is recorded under `work/`.
- Local container toolchain: Docker Engine 29.1.3, Compose 2.40.3, and Buildx
  0.30.1. The engine is enabled and `jim` is in the `docker` group. The
  temporary bootstrap sudo rule was removed after installation.

## Artifact decision

The official model is `Qwen/Qwen3.8-27B`, a 27B dense vision-language model with
native 262,144 context and MTP training. The first prototype uses only its text
path. The llama.cpp project publishes the pinned GGUF and matching MTP draft in
`ggml-org/Qwen3.8-27B-GGUF`.

The selected Q4_K_M target is 18.97 decimal GB (about 17.67 GiB). This is a
deliberate quality/reliability choice. The baseline uses 32K and Q8 KV; the
optimized profile attempts 64K with Q8 target KV, Q4 draft KV, and a 1.68 GB
Q4_0 MTP draft. Actual peak allocation must be measured on the 3090; file-size
arithmetic is not accepted as proof that the optimized profile fits.

## Measured results

| Profile | Status | Peak VRAM | Prompt tok/s | Output tok/s | Failures/retries | GPU-hours | Cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline 32K | 3/3 stable | 19,142 MiB | 1,014.959 median | 29.755 median | 0/0 | 0.048113 | $0.0106 |
| optimized MTP 64K | 3/3 stable | 21,994 MiB | 847.999 median | 37.511 median | 0/0 | 0.089717 | $0.0197 |

The baseline used 30,181 median input tokens. The optimized profile used 60,180
median input tokens and improved median generation speed by 26.1%. Across its
three runs, MTP accepted 2,092 of 3,748 drafted tokens (55.8%). The prompt-rate
figures are not an apples-to-apples speed comparison because the optimized run
processed twice as much context.

A deliberately retained first baseline attempt capped output at 512 tokens. All
three calls exhausted that cap while reasoning, one produced no visible answer,
and the other two needed retries. Raising the conservative allowance to 2,048
tokens yielded three natural `stop` completions with no retries. Qwen Code remains
configured for up to 8,192 output tokens; a 512-token agent budget is not viable
for this thinking model.

Request wall time across the failed-cap run and the two accepted three-run
profiles was 0.217 GPU-hours and about $0.048 at $0.22/hour. The Pod was allocated
from 16:00:29Z to 16:46:35Z, about 0.768 hours and $0.169 before any storage fee;
that broader number includes cold downloads, profile restarts, API/tool smokes,
and the native Codex compatibility test.

## Credential-ready preparation

The pre-account work is complete:

- both pinned Hugging Face artifacts respond at their immutable revisions;
- the llama.cpp `b10453` tag resolves to the pinned commit;
- host preflight distinguishes build, 24 GB GPU, and Qwen Code client roles;
- GPU suitability is checked before any multi-gigabyte artifact download;
- the Compose profile runner records startup health and timing before benchmarking;
- the matrix runner preserves baseline evidence if the optimized profile fails
  and tears down the server by default;
- benchmark rows retain raw llama.cpp timings and extracted draft/acceptance
  metrics plus a best-effort `/metrics` snapshot for the MTP comparison;
- request-only cost and controlled Compose allocation cost are recorded
  separately;
- the Qwen launcher enforces a clean disposable task worktree and uses a local
  auth proxy so the real endpoint key is not forwarded into sandbox arguments;
- the evidence collector deliberately avoids container environment and
  interpolated Compose output, hashes every collected file, and has a regression
  test proving the disposable key is not collected.

The pinned CUDA 12.8.1/llama.cpp image was built successfully on
`ubuntudailydriver` as `qwen-gpu-worker:b10453`. Its local image ID is
`sha256:1d9d4b1a5648276614ec6bf786487cef09298b7939c0deef994d886c355afb9c`
and its uncompressed image size is 2,361,013,079 bytes. The payload, entrypoint,
three llama.cpp executables, and pinned revision label were inspected. As
expected on the CPU-only build path, `libcuda.so.1` is absent until the NVIDIA
container runtime injects the host driver; the executable runtime check remains
a RunPod GPU gate.

This host's GPU preflight correctly stops on the 5 GB local GPU. Client preflight
passed after the explicitly authorized quarantine exception was recorded.

The official RunPod pricing page listed the RTX 3090 at $0.22/hour on Community
Cloud and $0.50/hour on Secure Cloud when checked. At the lower on-demand rate,
a continuously allocated 10-hour window costs about $2.20 per night or $66 for
30 nights, before storage. That is slightly above the target range; at the
eventual $0.10-$0.20/hour SaladCloud rate, the same window is $1-$2 per night.
The benchmark harness uses the actual displayed Pod rate and request wall time,
so the prototype report will not confuse a full-night allocation estimate with
GPU-hours actually consumed by the coding task.

The authenticated RunPod GPU inventory also returned one 24 GB RTX 3090 offer
with `stockStatus=Medium` and a lowest non-interruptible price of $0.22/hour.
The first Pod is therefore pinned to Community Cloud, one exact RTX 3090, and
non-interruptible service. Both authenticated HTTPS proxy and direct TCP are
exposed; the latter is the preferred coding path because RunPod documents a
100-second HTTP-proxy request ceiling.

The published image is
`ghcr.io/thejimmerjammer123/qwen-gpu-worker:b10453`, OCI index digest
`sha256:fbd9214685eb9f7ca3fa814303a8cd897b500ce102ac76e39f499f4953b7528c`.
GitHub Actions run `31956017154` built it successfully. RunPod Pod
`whmvwff58c7wk5` pulled that image on one Community RTX 3090 at $0.22/hour.
The 18.97 GB target artifact took about 14 minutes to download and verify on the
cold volume; the 1.68 GB MTP artifact took about 91 seconds. The stopped Pod and
its `/models` volume are retained temporarily so the coding-task run can restart
without downloading the artifacts again.

The server's basic Responses API, streaming SSE, and a required function call all
worked. A real Codex CLI 0.147.0 turn did not: Codex emitted `namespace` tools that
llama.cpp skipped, then Qwen's template rejected the converted request because a
system message was not first. This is a protocol-adapter gap, not a model or GPU
failure. See `docs/CODEX_WORKER.md`.

## Real coding task

The best non-duplicative first task is a fail-fast Supabase configuration guard in
JammerVIO. `SupabaseModule.kt` currently passes the build-config URL and anonymous
key directly into client construction without rejecting blank or whitespace-only
values. The corresponding backlog explicitly records the guard as undone, and a
scan of local/remote branches and worktrees found no existing implementation. The
task is one small production helper/path plus focused pure unit tests, with no UI
or device dependency. The exact bounded brief is
`prompts/jammervio-supabase-config-guard.md`; it must run in a fresh JammerVIO
worktree from `develop`.

The earlier zero/special-episode candidate was rejected after discovery that it
already exists on `feat/22-series-hero-download`; reproducing user work would not
be a meaningful benchmark.

Four bounded task launches established the end-to-end behavior:

1. The first stopped before inference because Qwen Code's pinned Docker sandbox
   image was absent and the current desktop process lacked Docker group access.
2. The second exposed a real isolation bug: the host auth proxy was loopback-only
   and unreachable from the sandbox. Qwen Code returned exit zero despite seven
   API errors and no model tokens. The wrapper now binds only to the private
   Docker bridge, maps `host.docker.internal`, and rejects semantic false-success.
3. The 32K baseline reached the model, made 10 successful API requests and 14
   successful read/search tool calls, and used 219,320 cumulative prompt tokens
   plus 16,288 output tokens. Compression still left an estimated 31,071-token
   prompt above Qwen Code's 30,852.8 safety limit, so it stopped without editing.
4. The optimized 64K/MTP retry produced the complete requested source diff. Qwen
   Code truncated its JSON report at exactly 65,536 bytes, so the hardened wrapper
   correctly returned failure even though the worktree diff was available for
   untrusted Codex review.

The wrapper now uses JSON Lines streaming instead of the truncated monolithic
report, validates the terminal result across the stream, and probes the
authenticated `/models` endpoint before launching Qwen. All 25 local prototype
tests pass. A targeted restart of the retained Pod failed because its host had no
free GPU, so a replacement Pod was allocated without deleting the original cache.

The registered route at
`/home/jim/development/bin/qwen-selfhosted-worker.sh` then passed a live smoke in
a disposable linked worktree. Qwen added one Python function and a built-in
`unittest` file, ran 4/4 tests successfully, returned a complete 13,192-byte JSON
Lines report, and left HEAD unchanged. The report recorded 63,406 input tokens,
1,173 output tokens, and 47,763 cached input tokens. Its hashed before/after/diff
checkpoint verified, and the automatic read-only Codex review returned `pass`
with no findings. This proves the Codex subprocess integration path independently
of the earlier JammerVIO quality task.

Replacement Pod `zv2pp8ozdcwdyl` was allocated from 18:08:06Z to about 18:22:44Z,
approximately 0.244 hours or $0.054 at $0.22/hour, including the cold model
download. It and retained Pod `whmvwff58c7wk5` are both stopped with separate
model caches.

The resulting change validates blank and whitespace-only Supabase URL/key values
before client construction, names the two expected Gradle properties in actionable
errors, and never includes configured values. It adds five pure unit tests. Codex
review and an independent read-only review found no blocker. The sanctioned Netcup
compile passed in 3m33s; the full suite reported 1,179 tests with the repository's
existing 12-failure ceiling; and the focused class passed 5/5 in 19s.

The orchestrator committed the reviewed diff as
`84b0ec1ddfff54050a19a8df8aa4e23993474f48` on
`fix/supabase-config-guard`, pushed it through the canonical GitLab control plane,
and opened draft MR !98. It was not merged. The authorized disposable runner
boundary was restored to `gitlab-clean-base`; pipeline 392's build job passed and
the quality-baseline job is running through the one-job controller.

The four task allocations totaled about 0.44 GPU-hours, estimated from start/stop
timestamps, or about $0.10 at $0.22/hour. This is an allocation estimate rather
than provider billing reconciliation. The Pod is stopped with its model cache
retained.

## Decision gate

The self-hosted Qwen Code subprocess route is now running and integrated into the
Codex harness with worktree isolation, timeout/budget, shared writer exclusion,
Git checkpoints, availability checks, the run ledger, and Codex review/escalation.
The native Bailian-backed `qwen_worker` remains unchanged.

Further model-quality evaluation, SaladCloud preparation, and a separate native
vLLM Responses experiment are follow-up work rather than integration blockers.
Pipeline 392 should be allowed to finish and clean up, but it is evidence for the
sample JammerVIO change rather than a prerequisite for the registered worker.

Both the 32K baseline and 64K/MTP profile fit fully on one 3090. At the measured
rates, the inference side is economically attractive; the open decision is agent
quality and orchestration reliability, not GPU feasibility.
