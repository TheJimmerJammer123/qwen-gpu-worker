#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QwenWrapperTest(unittest.TestCase):
    def test_forces_sandbox_without_forwarding_upstream_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bin_dir = temp / "bin"
            home = temp / "home"
            repo = temp / "repo"
            bin_dir.mkdir()
            home.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "qwen/test-task"], check=True)
            prompt = temp / "prompt.md"
            prompt.write_text("Make a harmless test change.", encoding="utf-8")
            fake_docker = bin_dir / "docker"
            fake_docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_qwen = bin_dir / "qwen"
            fake_qwen.write_text(
                "#!/bin/sh\n"
                "python3 -c 'import json,os,sys; settings=json.load(open(os.path.join(os.environ[\"QWEN_HOME\"], \"settings.json\"))); print(json.dumps({\"sandbox\": os.environ.get(\"QWEN_SANDBOX\"), \"openai_key\": os.environ.get(\"OPENAI_API_KEY\"), \"base_url\": settings[\"modelProviders\"][\"openai\"][0][\"baseUrl\"], \"args\": sys.argv[1:]}))' \"$@\"\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            fake_qwen.chmod(0o755)
            env = {
                "HOME": str(home),
                "USER": "test-worker",
                "LANG": "C.UTF-8",
                "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
                "QWEN_GPU_API_KEY": "disposable-test-key",
                "QWEN_GPU_BASE_URL": "http://127.0.0.1:8000/v1",
                "QWEN_PROTOTYPE_HOME": str(temp / "qwen-home"),
                "QWEN_PROTOTYPE_RUNTIME_DIR": str(temp / "runtime"),
                "QWEN_SANDBOX_PROVIDER": "docker",
                "QWEN_ALLOW_PRIMARY_WORKTREE": "true",
                "QWEN_QUARANTINE_MARKER": str(temp / "not-quarantined"),
            }
            output = subprocess.check_output(
                [str(ROOT / "scripts/run-qwen-code.sh"), str(repo), str(prompt)], env=env, text=True
            )
        result = json.loads(output)
        self.assertEqual(result["sandbox"], "docker")
        self.assertNotEqual(result["openai_key"], "disposable-test-key")
        self.assertRegex(result["openai_key"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["base_url"], r"^http://127\.0\.0\.1:[0-9]+/v1$")
        self.assertIn("--sandbox", result["args"])
        self.assertNotIn("--sandbox=docker", result["args"])


if __name__ == "__main__":
    unittest.main()
