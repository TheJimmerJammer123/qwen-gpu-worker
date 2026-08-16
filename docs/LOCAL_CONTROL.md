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

RunPod and registry credentials are injected into individual local child
processes through Bitwarden Agent Access. They are never copied to devserver2,
written to this repository, or placed on the GPU worker. RunPod inventory is
queried with:

```bash
cd /home/jim/.codex/skills/bitwarden-agent-access
./scripts/run-with-credential.sh \
  --domain runpod.io \
  --env RUNPOD_API_KEY=password \
  -- /home/jim/Documents/ChatGPT/JammerVIO/qwen/scripts/runpod-api.py inventory
```

The inventory client omits all Pod/template environment values and prints only
the environment variable names plus non-secret resource metadata.
