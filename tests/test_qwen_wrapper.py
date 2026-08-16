#!/usr/bin/env python3
from __future__ import annotations

import json
import http.server
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModelHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = b'{"data":[{"id":"Qwen3.8-27B-Q4_K_M"}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def model_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


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
            fake_docker.write_text(
                "#!/bin/sh\n"
                "if [ \"$1 $2\" = \"network inspect\" ]; then printf '127.0.0.1\\n'; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_qwen = bin_dir / "qwen"
            fake_qwen.write_text(
                "#!/bin/sh\n"
                "printf 'changed\\n' > qwen-test-change.txt\n"
                "python3 -c 'import json,os,sys; settings=json.load(open(os.path.join(os.environ[\"QWEN_HOME\"], \"settings.json\"))); detail=json.dumps({\"sandbox\": os.environ.get(\"QWEN_SANDBOX\"), \"openai_key\": os.environ.get(\"OPENAI_API_KEY\"), \"base_url\": settings[\"modelProviders\"][\"openai\"][0][\"baseUrl\"], \"args\": sys.argv[1:]}); print(json.dumps({\"type\": \"result\", \"subtype\": \"success\", \"is_error\": False, \"result\": detail, \"usage\": {\"input_tokens\": 1}}))' \"$@\"\n",
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
                "QWEN_PROTOTYPE_HOME": str(temp / "qwen-home"),
                "QWEN_PROTOTYPE_RUNTIME_DIR": str(temp / "runtime"),
                "QWEN_SANDBOX_PROVIDER": "docker",
                "QWEN_ALLOW_PRIMARY_WORKTREE": "true",
                "QWEN_QUARANTINE_MARKER": str(temp / "not-quarantined"),
            }
            with model_server() as base_url:
                env["QWEN_GPU_BASE_URL"] = base_url
                output = subprocess.check_output(
                    [str(ROOT / "scripts/run-qwen-code.sh"), str(repo), str(prompt)], env=env, text=True
                )
        result = json.loads(json.loads(output)["result"])
        self.assertEqual(result["sandbox"], "docker")
        self.assertNotEqual(result["openai_key"], "disposable-test-key")
        self.assertRegex(result["openai_key"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["base_url"], r"^http://host\.docker\.internal:[0-9]+/v1$")
        self.assertIn("--sandbox", result["args"])
        self.assertNotIn("--sandbox=docker", result["args"])
        self.assertIn("stream-json", result["args"])

    def test_fails_closed_on_semantic_api_error_without_diff(self) -> None:
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
            fake_docker.write_text(
                "#!/bin/sh\n"
                "if [ \"$1 $2\" = \"network inspect\" ]; then printf '127.0.0.1\\n'; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_qwen = bin_dir / "qwen"
            fake_qwen.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"result\":\"[API Error: Connection error.]\",\"usage\":{\"input_tokens\":0}}'\n",
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
                "QWEN_PROTOTYPE_HOME": str(temp / "qwen-home"),
                "QWEN_PROTOTYPE_RUNTIME_DIR": str(temp / "runtime"),
                "QWEN_SANDBOX_PROVIDER": "docker",
                "QWEN_ALLOW_PRIMARY_WORKTREE": "true",
                "QWEN_QUARANTINE_MARKER": str(temp / "not-quarantined"),
            }
            with model_server() as base_url:
                env["QWEN_GPU_BASE_URL"] = base_url
                completed = subprocess.run(
                    [str(ROOT / "scripts/run-qwen-code.sh"), str(repo), str(prompt)],
                    env=env,
                    text=True,
                    capture_output=True,
                )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("no successful model-backed result", completed.stderr)


if __name__ == "__main__":
    unittest.main()
