# First RTX 3090 runbook

This is the shortest path from new accounts to a reviewable experiment. Stop at
the first failed gate and preserve `results/`; do not tune several variables at
once.

## 1. Build host

```bash
cd /home/jim/Documents/ChatGPT/JammerVIO/qwen
./scripts/preflight.sh build

export IMAGE=REGISTRY/OWNER/qwen-gpu-worker:b10453
docker buildx build --platform linux/amd64 --push -t "$IMAGE" .
```

Record the pushed immutable image digest. Use that exact digest for both RunPod
and the later SaladCloud test rather than rebuilding between providers.

## 2. RunPod baseline Pod

Create one RTX 3090 Pod from `config/runpod-template.example.json`. Use a fresh
server key and set the actual displayed hourly price. Do not attach broad cloud
or source-control credentials.

The baseline gate is:

- `/v1/models` becomes healthy;
- effective configuration reports 32,768 context, full GPU offload, and no
  speculation;
- three long-prompt requests succeed;
- no server restart or malformed response occurs;
- peak VRAM stays below the physical limit.

On a Compose-capable GPU host the complete baseline is:

```bash
export LLAMA_API_KEY="$(openssl rand -hex 32)"
export GPU_HOURLY_COST_USD=ACTUAL_RATE
./scripts/preflight.sh gpu
RUN_OPTIMIZED=false ./scripts/run-matrix.sh
```

For a managed RunPod container, use its terminal:

```bash
/app/scripts/run-benchmark.sh baseline
python3 /app/scripts/summarize-benchmarks.py /results/benchmarks.jsonl
```

Download `/results/benchmarks.jsonl` and `/results/effective-config.json` before
changing or deleting the Pod. The first template deliberately makes the public
model cache durable but leaves `/results` on the disposable container; an
interrupted Pod can therefore lose evidence that was not downloaded. This is an
accepted first-manual-run limitation, not the nightly design.

## 3. Optimized Pod

Only after the baseline passes, recreate the same immutable image with
`PROFILE=optimized`. Run `/app/scripts/run-benchmark.sh optimized`. Treat an OOM,
server restart, or slower generation as a valid negative result; return to the
baseline instead of silently reducing target-model offload.

On a Compose-capable host, `./scripts/run-matrix.sh` performs both profiles,
always attempts to collect an evidence directory, and runs `docker compose down`
after success or failure. `KEEP_SERVER=true` is the explicit debugging override.
`results/allocations.jsonl` records controlled runner time/cost separately from
request-only benchmark cost; provider billing before/after the script must still
be reconciled from RunPod.

## 4. Qwen Code task

First rotate the quarantined credential and remove the marker only after that
rotation is verified. From the client host:

```bash
./scripts/preflight.sh client
export QWEN_GPU_BASE_URL='https://RUNPOD-ENDPOINT/v1'
export QWEN_GPU_API_KEY="$LLAMA_API_KEY"
export QWEN_CONTEXT_SIZE=32768
export QWEN_SANDBOX_PROVIDER=docker

# Create a fresh linked worktree on a dedicated task branch first:
./scripts/prepare-task-worktree.sh \
  /path/to/jammervio \
  /path/to/jammervio-qwen-supabase \
  qwen/supabase-config-guard \
  develop

./scripts/run-qwen-code.sh \
  /path/to/jammervio-qwen-supabase \
  prompts/jammervio-supabase-config-guard.md \
  > results/qwen-code-task.json \
  2> results/qwen-code-task.log
```

Codex then reviews the entire diff, runs the sanctioned JammerVIO verification
path, and creates the commit/request. Qwen receives no remote Git credential and
cannot merge.

## 5. Evidence and teardown

On a Compose host:

```bash
./scripts/collect-evidence.sh
docker compose down
unset LLAMA_API_KEY QWEN_GPU_API_KEY
```

The evidence directory contains hashes, prototype commit, image identity where
available, effective server configuration, GPU identity, server log, startup
timing, raw benchmark rows, summary, and Qwen task output. It intentionally does
not collect container environment or Compose's interpolated configuration because
those would expose the server key.
