#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly root
cd "$root"

command -v shellcheck >/dev/null || { echo "error: shellcheck is required" >&2; exit 127; }
command -v jq >/dev/null || { echo "error: jq is required" >&2; exit 127; }

./scripts/preflight.sh source
bash -n scripts/*.sh
shellcheck -S warning scripts/*.sh
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
jq empty config/qwen-settings.template.json config/runpod-template.example.json
for file in config/model.env config/profiles/*.env; do
  bash -n "$file"
done
git diff --check
