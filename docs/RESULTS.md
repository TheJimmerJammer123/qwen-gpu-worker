# Phase 1 result record

Date: 2026-08-16

## Environment inspection

- Prototype repository: `/home/jim/development/projects/infrastructure/qwen-gpu-worker`.
- JammerVIO source: `/home/jim/development/projects/dualfin/jammervio`, currently
  `develop` at `e8c654a9e8a5b2e2eaf59e64aed99f26716eaaf9` with unrelated user
  modifications. It was not changed.
- The enclosing development control-plane repository also has extensive unrelated
  changes. It was not changed.
- Local GPU: NVIDIA Quadro P2000, 5,120 MiB. It cannot run this model.
- Local Qwen Code: 0.21.1, but the existing integration is quarantined after a
  credential appeared in a diagnostic process argument. No existing credentials
  were read or tested.
- Local Docker/Podman/RunPod CLI: unavailable.

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
| baseline 32K | blocked: no cloud GPU provisioned | — | — | — | — | 0 | $0 |
| optimized MTP 64K | not attempted until baseline passes | — | — | — | — | 0 | $0 |

These cells must be filled from `results/benchmarks.jsonl`; estimates must not be
substituted for measurements.

The official RunPod pricing page listed the RTX 3090 at $0.22/hour on Community
Cloud and $0.50/hour on Secure Cloud when checked. At the lower on-demand rate,
a continuously allocated 10-hour window costs about $2.20 per night or $66 for
30 nights, before storage. That is slightly above the target range; at the
eventual $0.10-$0.20/hour SaladCloud rate, the same window is $1-$2 per night.
The benchmark harness uses the actual displayed Pod rate and request wall time,
so the prototype report will not confuse a full-night allocation estimate with
GPU-hours actually consumed by the coding task.

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
be a meaningful benchmark. The Supabase task has not been dispatched because
inference has not yet run and the old Qwen credential path is quarantined. No
JammerVIO branch, commit, merge request, or pull request is claimed.

There is also a repository-authority mismatch to resolve before publication:
the closest checked-in JammerVIO instructions currently say GitLab is authoritative
and GitHub is pull-only, while a separate installed JammerVIO skill says GitHub is
authoritative. Until the repository instructions are reconciled, use a local task
branch as the checkpoint and do not push or open either kind of request by guess.

## Decision gate

Do not proceed to a nightly SaladCloud worker yet. Proceed to the inexpensive
single-3090 RunPod measurement now. Advance to SaladCloud packaging only if all of
these are observed:

1. Baseline starts with full target-model GPU offload and stays below 24 GB VRAM.
2. At least three baseline calls complete with no malformed tool calls or server
   restart and a useful output rate for an interactive coding loop.
3. Qwen Code completes the isolated repository task within the configured budgets.
4. Independent review finds the diff worth testing, and the sanctioned repository
   checks pass.
5. The measured GPU-hours and displayed RunPod rate support the expected economics.

The optimized 64K/MTP profile is a secondary result. A stable 32K baseline is
enough to justify continuing even if 64K plus MTP does not fit on one 3090.
