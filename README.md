# Disposable Qwen GPU worker prototype

This repository is the single-GPU proof of concept for serving
`Qwen/Qwen3.8-27B` to Qwen Code through llama.cpp's OpenAI-compatible API. It is
deliberately separate from the Android repositories and the homelab control
plane. A GPU worker owns no durable state: model files are a cache, benchmark
records are copied out, and coding work survives through a task branch.

The operator boundary is `ubuntudailydriver`: image builds, registry pushes,
RunPod API calls, evidence, and Qwen Code all originate here. `devserver2` is not
part of the execution path. See `docs/LOCAL_CONTROL.md`.

## Pinned baseline

- Model: `Qwen/Qwen3.8-27B`, upstream revision
  `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
- GGUF: `ggml-org/Qwen3.8-27B-GGUF` revision
  `0669b98607d47046c7c2b3f801011d54a08cfccf`.
- Quantization: `Qwen3.8-27B-Q4_K_M.gguf`, 18,973,870,432 bytes, SHA-256
  `31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`.
- Backend: llama.cpp release `b10453`, commit
  `3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70`.
- Vision projector: intentionally omitted. The first decision is text coding and
  tool-use reliability, and the projector consumes another 600-900 MB.

The GGUF is from the llama.cpp project's `ggml-org` organization and includes a
matching MTP draft artifact. `Q4_K_M` is preferred over a smaller IQ quant for
this first test: it leaves enough room on a 24 GB card while keeping a familiar,
quality-oriented K-quant and a single provenance chain for the target and MTP
files.

## Profiles

| Profile | Context | KV cache | Speculation | Purpose |
| --- | ---: | --- | --- | --- |
| `baseline` | 32,768 | Q8 K/V | off | conservative, one slot, establish correctness |
| `optimized` | 65,536 | Q8 target, Q4 draft | Qwen MTP Q4_0, 2 draft tokens | experimental fit/speed test after baseline |

Both profiles use one server slot, full GPU offload, flash attention, prompt
caching, explicit Jinja tool calling, no vision projector, disabled automatic
fit adjustment, and the same target-model bytes. Do not compare coding quality
across profiles using different target artifacts.

The container entrypoint uses root only to make provider-mounted `/models` and
`/results` directories writable, then drops permanently to UID 10001 before any
download or model-server process starts.

## Build and run on any NVIDIA Docker host

Prerequisites are Docker Buildx, the NVIDIA Container Toolkit, a driver that
supports CUDA 12.8, at least 30 GB free disk for the model cache, and one 24 GB
GPU.

Check the intended machine before building or renting time:

```bash
./scripts/preflight.sh build   # image build machine
./scripts/preflight.sh gpu     # Compose-capable 3090 host
./scripts/preflight.sh client  # Qwen Code client, after quarantine is cleared
```

```bash
cd /home/jim/Documents/ChatGPT/JammerVIO/qwen
export LLAMA_API_KEY="$(openssl rand -hex 32)"
export GPU_HOURLY_COST_USD=0.22
docker buildx build --load -t qwen-gpu-worker:b10453 .
PROFILE=baseline docker compose up -d
docker compose logs -f qwen-server
```

The first start downloads and verifies about 19 GB. The server becomes healthy
only after model load succeeds. By default Compose binds to `127.0.0.1:8000`.

```bash
curl --fail -H "Authorization: Bearer $LLAMA_API_KEY" \
  http://127.0.0.1:8000/v1/models | jq
```

To switch profiles, recreate the container without deleting the model volume:

```bash
PROFILE=optimized docker compose up -d --force-recreate
docker compose logs -f qwen-server
```

The optimized first start additionally downloads the pinned 1.68 GB Q4_0 MTP
draft. If it does not fit, first lower batch/ubatch, then keep the target KV at
Q8 while trying Q4 draft KV (already configured), and only then record a distinct
Q4 target-KV variant. If it is unstable, return to the baseline; do not partially
offload the target model and call that a successful single-3090 result.

## RunPod launch

Build once and push the same image that will later be used on SaladCloud:

```bash
export IMAGE=ghcr.io/thejimmerjammer123/qwen-gpu-worker:b10453
docker buildx build --platform linux/amd64 --push -t "$IMAGE" .
```

Create a RunPod Pod/template with these exact workload values:

- GPU: one RTX 3090, 24 GB.
- Container image: `$IMAGE`.
- Container disk: 20 GB.
- Persistent/network volume: at least 30 GB, mounted at `/models`.
- Exposed port: `8000/http` plus `8000/tcp`; direct TCP avoids the HTTPS
  proxy's 100-second request limit for long generations.
- Environment: `PROFILE=baseline`, `LLAMA_API_KEY=<fresh random secret>`, and
  `GPU_HOURLY_COST_USD=<the displayed pod rate>`.
- Do not inject GitHub, GitLab, homelab, production, or deployment credentials
  into the inference container.

`config/runpod-template.example.json` is a value checklist, not an account-ready
API request. Account/template identifiers and registry credentials belong in
RunPod secrets, not this repository.

RunPod's HTTP proxy URL is normally of the form shown in the Pod's Connect page.
Set the complete `/v1` URL locally rather than guessing it:

```bash
export QWEN_GPU_BASE_URL='https://YOUR-RUNPOD-PROXY/v1'
export QWEN_GPU_API_KEY="$LLAMA_API_KEY"
curl --fail -H "Authorization: Bearer $QWEN_GPU_API_KEY" \
  "$QWEN_GPU_BASE_URL/models" | jq
```

An SSH tunnel to port 8000 is preferable when practical. In either case, keep
llama.cpp authentication enabled and rotate the disposable key with the Pod.

## Benchmark

Run benchmarks inside the GPU container so `nvidia-smi` can record GPU identity
and peak VRAM. Three uncached requests are the default:

```bash
docker compose exec qwen-server /app/scripts/run-benchmark.sh baseline
docker compose exec qwen-server \
  python3 /app/scripts/summarize-benchmarks.py /results/benchmarks.jsonl
docker compose cp qwen-server:/results/benchmarks.jsonl ./results/benchmarks.jsonl
```

For the optimized profile:

```bash
PROFILE=optimized docker compose up -d --force-recreate
docker compose exec qwen-server /app/scripts/run-benchmark.sh optimized
docker compose exec qwen-server \
  python3 /app/scripts/summarize-benchmarks.py /results/benchmarks.jsonl
docker compose cp qwen-server:/results/benchmarks.jsonl ./results/benchmarks.jsonl
```

The default prompts include a deterministic 30,000-token filler for the 32K
profile and 60,000-token filler for the 64K profile; llama.cpp's reported input
count remains authoritative. Each JSONL row records the pinned model/quant, GPU
and peak VRAM, configured context, requested and actual input size, llama.cpp
timing rates, output tokens, attempts/retries, wall duration, backend
configuration, speculative state, GPU-hours, and estimated cost. Keep the raw
`results/benchmarks.jsonl` outside the disposable Pod before deletion.

On a Compose-capable 3090 host, the repeatable matrix command starts each
profile, waits for health, records model startup time, runs the benchmarks, and
collects a hashed evidence directory even if a later profile fails:

```bash
export LLAMA_API_KEY="$(openssl rand -hex 32)"
export GPU_HOURLY_COST_USD=0.22  # replace with the displayed rate
./scripts/run-matrix.sh
```

Set `RUN_OPTIMIZED=false` for a baseline-only gate. See `docs/FIRST_RUN.md` for
the full stop/go runbook.

## Qwen Code

Qwen Code 0.21.1 supports custom OpenAI-compatible models through
`modelProviders.openai`. The template keeps the API key out of settings and reads
the standard `OPENAI_API_KEY`. The wrapper starts a loopback-only auth proxy and
gives Qwen a random local token; only the proxy receives `QWEN_GPU_API_KEY`, so
the real endpoint key is not copied into Qwen's Docker sandbox arguments or
metadata. Use a dedicated `QWEN_HOME` so this prototype does not alter an existing
provider configuration. The client host also needs Docker or Podman for Qwen
Code's tool sandbox:

```bash
npm install --global @qwen-code/qwen-code@0.21.1
```

```bash
export QWEN_GPU_BASE_URL='https://YOUR-ENDPOINT/v1'
export QWEN_GPU_API_KEY='THE-DISPOSABLE-SERVER-KEY'
export QWEN_CONTEXT_SIZE=32768
export QWEN_SANDBOX_PROVIDER=docker
./scripts/run-qwen-code.sh /path/to/task-worktree /path/to/task-brief.md \
  > results/qwen-code-task.json 2> results/qwen-code-task.log
```

The wrapper limits the run to 45 turns, 60 top-level tool calls, and 30 minutes;
it disables nested agents and provider-changing commands. It launches Qwen Code
with a scrubbed environment and uses YOLO approval only inside Qwen Code's
container sandbox. It enforces a clean `qwen/*` task branch, rejects protected or
detached branches and ignored files, and requires a linked disposable worktree by
default. The override `QWEN_ALLOW_PRIMARY_WORKTREE=true` is intentionally
explicit and is not appropriate for the JammerVIO trial.
The orchestrator—not Qwen—reviews the diff, runs sanctioned tests, commits,
pushes, and opens a merge/pull request.

## Stop and remove

```bash
docker compose down
```

That removes the container but preserves the model cache. Remove the named model
volume only when the cached 20+ GB is no longer useful. On RunPod, copy out
benchmark/task evidence and push the task branch before terminating the Pod.

## Current prototype status

The paid RunPod inference gate is complete. The pinned image ran fully on one RTX
3090: the stable 32K baseline used 19,142 MiB and generated at a 29.755 tok/s
median; the 64K/MTP profile used 21,994 MiB and generated at 37.511 tok/s. Both
profiles completed three long-context calls without retries. The Pod is stopped
with its model cache retained.

The prepared JammerVIO task ran through the bounded Qwen Code worktree route.
The 32K run reached the model and completed 14 read-only tool calls but exceeded
Qwen Code's context safety limit before editing. The 64K/MTP retry produced the
requested fail-fast Supabase configuration guard and five focused tests. Codex
and an independent reviewer found no blocking issue; sanctioned remote compile
and focused tests passed. The change is available as draft GitLab MR !98 and was
not merged. The authorized disposable runner was restored; pipeline 392's build
job passed and its quality-baseline job is running.

Qwen Code truncated the earlier monolithic JSON report at exactly 65,536 bytes.
The wrapper now requests JSON Lines streaming, validates its terminal result,
and probes the authenticated endpoint before launching the agent. A live
end-to-end smoke passed through the registered Codex worker route: Qwen edited a
disposable worktree, ran 4/4 tests, returned a complete report, preserved HEAD,
produced a verified hashed checkpoint, and received a clean read-only Codex
review. The distinct route is `/home/jim/development/bin/qwen-selfhosted-worker.sh`;
the existing native Bailian-backed `qwen_worker` remains unchanged. Current vLLM
releases expose a dedicated Codex Responses integration worth evaluating later,
but it is no longer required to get the self-hosted worker running. See
`docs/RESULTS.md` and `docs/CODEX_WORKER.md`.

The local validation command is:

```bash
./scripts/validate.sh
```

Account and secret handling is documented in `docs/CREDENTIAL_HANDOFF.md`. The
operator explicitly authorized clearing the local quarantine without claiming
that the older credential was rotated; that exception is recorded under `work/`.
Only the disposable Infisical `/qwen` key was injected through the scrubbed
wrapper. No source-control credential belongs on the GPU worker. Both Qwen
prototype Pods are stopped with their model caches retained.
