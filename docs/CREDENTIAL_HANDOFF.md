# Credential and account handoff

The worker is designed so the inference Pod needs exactly one secret: a fresh,
disposable `LLAMA_API_KEY`. Do not reuse the previously exposed Qwen credential,
and do not place GitHub, GitLab, SSH, homelab, deployment, or production secrets
in the inference container.

## What must exist before the live run

1. The existing RunPod account has authenticated API access through Infisical's
   `/runpod` production path; billing capacity is checked at creation time.
2. The public GHCR repository that RunPod can pull. If the package must remain private,
   prototype image. If it must be private, store the registry pull credential in
   RunPod's registry authentication facility rather than a Pod environment
   variable.
3. A locally generated server key:

   ```bash
   export LLAMA_API_KEY="$(openssl rand -hex 32)"
   ```

4. After the Pod is healthy, its complete OpenAI base URL, including `/v1`.

The RunPod API token remains in Infisical and is exposed only to the local
provisioning child process—not the GPU container or Qwen Code sandbox.

## Safe handoff to Codex

Do not paste credentials into chat, commit them, or place them in command-line
arguments. Set them in the operator shell or inject them through the approved
credential mechanism, then provide only the non-secret endpoint location and the
fact that the variables are ready. The required local names are:

```text
LLAMA_API_KEY       server container and Compose operations
QWEN_GPU_API_KEY    benchmark/Qwen Code client; same disposable value
QWEN_GPU_BASE_URL   non-secret endpoint ending in /v1
GPU_HOURLY_COST_USD non-secret displayed Pod price
```

The key can appear in the disposable inference container's environment, but the
scripts do not place it in llama.cpp process arguments, Qwen settings, Qwen's
tool-sandbox arguments, benchmark output, or the evidence bundle. The Qwen
launcher keeps the real key in a short-lived localhost auth proxy and gives Qwen
only a random loopback token with no value against the remote endpoint.

For the first live Pod, the disposable client/server key is stored as
`QWEN_GPU_API_KEY` in Infisical project
`8e8371f7-6a39-4304-a608-1703604648ba`, environment `prod`, path `/qwen`.
It was written through stdin and its value was never placed in a process
argument. Use `infisical run` with that path to inject it into the Qwen launcher;
do not export, print, or copy it into a settings file.

## Rotation and teardown

- Rotate or permanently abandon the old credential referenced by
  `../work/qwen.disabled` before invoking the installed Qwen Code CLI.
- Generate a different `LLAMA_API_KEY` for every Pod.
- Copy the evidence bundle and preserve the coding work in Git before deleting
  the Pod.
- Delete the Pod after the run. Delete its model volume too unless retaining the
  public model cache is intentionally worth the storage charge.
- Unset `LLAMA_API_KEY` and `QWEN_GPU_API_KEY` in the operator shell after
  teardown.
