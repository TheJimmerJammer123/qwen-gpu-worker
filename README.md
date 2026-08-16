# Disposable Qwen GPU worker prototype

This repository is the single-GPU proof of concept for serving
`Qwen/Qwen3.8-27B` to Qwen Code through llama.cpp's OpenAI-compatible API. It is
deliberately separate from the Android repositories and the homelab control
plane. A GPU worker owns no durable state: model files are a cache, benchmark
records are copied out, and coding work survives through a task branch.

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

```bash
cd /path/to/qwen-gpu-worker
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
export IMAGE=REGISTRY/OWNER/qwen-gpu-worker:b10453
docker buildx build --platform linux/amd64 --push -t "$IMAGE" .
```

Create a RunPod Pod/template with these exact workload values:

- GPU: one RTX 3090, 24 GB.
- Container image: `$IMAGE`.
- Container disk: 20 GB.
- Persistent/network volume: at least 30 GB, mounted at `/models`.
- Exposed HTTP port: `8000`.
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

## Qwen Code

Qwen Code 0.21.1 supports custom OpenAI-compatible models through
`modelProviders.openai`. The template keeps the API key out of settings and reads
the standard sandbox-forwarded `OPENAI_API_KEY`; the wrapper maps the disposable
`QWEN_GPU_API_KEY` to it at runtime. Use a dedicated `QWEN_HOME` so this prototype
does not alter an existing provider configuration. The client host also needs
Docker or Podman for Qwen Code's tool sandbox:

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
container sandbox, against a disposable task worktree with no broad credentials.
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

The implementation and local static tests are complete. No cloud GPU was
available from this development host, which has a 5 GB Quadro P2000 and no local
Docker daemon. The existing Qwen integration is also intentionally quarantined
by `/home/jim/Documents/ChatGPT/JammerVIO/work/qwen.disabled` pending credential
rotation. Therefore no 3090 throughput numbers or Qwen-authored repository diff
are claimed yet; see `docs/RESULTS.md` for the exact remaining gate.

The local validation command is:

```bash
./scripts/validate.sh
```
