#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationalScriptsTest(unittest.TestCase):
    def test_prepares_clean_linked_qwen_task_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "source"
            target = temporary / "task"
            subprocess.run(["git", "init", "-q", "-b", "develop", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.invalid"], check=True)
            (source / "README.md").write_text("test\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "initial"], check=True)
            result = subprocess.run(
                [
                    str(ROOT / "scripts/prepare-task-worktree.sh"),
                    str(source),
                    str(target),
                    "qwen/test-task",
                    "develop",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            branch = subprocess.check_output(
                ["git", "-C", str(target), "branch", "--show-current"], text=True
            ).strip()
            self.assertEqual(branch, "qwen/test-task")
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(target), "status", "--porcelain"], text=True
                ),
                "",
            )

    def test_source_preflight_passes_without_cloud_tools(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts/preflight.sh"), "source"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preflight complete: source", result.stdout)

    def test_profile_runner_rejects_invalid_cost_before_docker(self) -> None:
        environment = dict(os.environ)
        environment.update(
            {
                "LLAMA_API_KEY": "disposable-test-value",
                "GPU_HOURLY_COST_USD": "not-a-number",
            }
        )
        result = subprocess.run(
            [str(ROOT / "scripts/run-profile.sh"), "baseline"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be numeric", result.stderr)
        self.assertNotIn("disposable-test-value", result.stdout + result.stderr)

    def test_evidence_bundle_is_hashed_and_does_not_collect_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            fake_bin = temporary / "bin"
            fake_bin.mkdir()
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
case " $* " in
  *" images "*) echo '{"Repository":"qwen-gpu-worker","Tag":"test"}' ;;
  *" logs "*) echo 'server-start profile=baseline' ;;
  *" cp "*) printf '{"profile":"baseline"}\\n' > "${@: -1}" ;;
  *" exec "*) echo 'NVIDIA GeForce RTX 3090, GPU-test, 580.0, 24576' ;;
  *) exit 2 ;;
esac
""",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            destination = temporary / "evidence"
            environment = dict(os.environ)
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            environment["LLAMA_API_KEY"] = "must-not-be-collected"
            result = subprocess.run(
                [str(ROOT / "scripts/collect-evidence.sh"), str(destination)],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((destination / "SHA256SUMS").is_file())
            verification = subprocess.run(
                ["sha256sum", "--check", "SHA256SUMS"],
                cwd=destination,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            collected = "".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in destination.iterdir()
                if path.is_file()
            )
            self.assertNotIn("must-not-be-collected", collected)


if __name__ == "__main__":
    unittest.main()
