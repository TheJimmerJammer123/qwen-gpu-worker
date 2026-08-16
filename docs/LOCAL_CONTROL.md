# Local control boundary

All build, registry, RunPod API, benchmark orchestration, evidence collection, and
Qwen Code review work runs from `ubuntudailydriver`. Cloud Pods are disposable
inference workers only.

`devserver2:/home/jimmerjammer/development/runpod` was inspected once as legacy
operational evidence. Its useful lessons were that the HTTPS proxy is more
reliable than assuming SSH and that idle/storage time dominates careless costs.
It is not a build host, control plane, credential source, or durable state store
for this prototype. No Qwen image or active build directory is retained there.

## Local prerequisites

Ubuntu's packaged Docker engine requires one operator-authorized installation:

The preferred temporary-sudo bootstrap is:

```bash
cd /home/jim/Documents/ChatGPT/JammerVIO/qwen
/usr/sbin/visudo -cf config/sudoers.d/qwen-docker-bootstrap
sudo install -o root -g root -m 0440 \
  config/sudoers.d/qwen-docker-bootstrap \
  /etc/sudoers.d/qwen-docker-bootstrap
```

After that one authenticated `install`, Codex can run only the exact commands
listed in the rule, complete the installation, and remove the temporary rule.
It does not grant general passwordless sudo.

The equivalent manual installation is:

```bash
sudo apt update
sudo apt install -y docker.io docker-buildx docker-compose-v2
sudo usermod -aG docker jim
sudo systemctl enable --now docker
```

Log out and back in, or run `newgrp docker`, before continuing. Verify locally:

```bash
cd /home/jim/Documents/ChatGPT/JammerVIO/qwen
./scripts/preflight.sh build
```

The RunPod credential is injected into individual local child processes through
the healthy Infisical service. It is never copied to devserver2, written to this
repository, or placed on the GPU worker. RunPod inventory is queried with:

```bash
cd /home/jim/Documents/ChatGPT/JammerVIO/qwen
infisical run --domain https://infisical.tailbf2de.ts.net \
  --projectId 8e8371f7-6a39-4304-a608-1703604648ba \
  --env prod --path /runpod -- \
  python3 scripts/runpod-api.py inventory
```

Query the authenticated live 3090 stock/price view without creating anything:

```bash
infisical run --domain https://infisical.tailbf2de.ts.net \
  --projectId 8e8371f7-6a39-4304-a608-1703604648ba \
  --env prod --path /runpod -- \
  python3 scripts/runpod-api.py gpu-offers
```

The inventory client omits all Pod/template environment values and prints only
the environment variable names plus non-secret resource metadata.

Create and inspect the isolated prototype with a fresh process-only server key:

```bash
export LLAMA_API_KEY="$(openssl rand -hex 32)"
export GPU_HOURLY_COST_USD=0.22
export QWEN_WORKER_IMAGE=ghcr.io/thejimmerjammer123/qwen-gpu-worker:b10453
infisical run --domain https://infisical.tailbf2de.ts.net \
  --projectId 8e8371f7-6a39-4304-a608-1703604648ba \
  --env prod --path /runpod -- \
  python3 scripts/runpod-api.py create-prototype --yes
```

The API client refuses to create a second Pod in its prototype namespace and
refuses to stop or terminate any Pod whose name is outside that namespace. Keep
`LLAMA_API_KEY` in the controlling shell until benchmark evidence is collected.
