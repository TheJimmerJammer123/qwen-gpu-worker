#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpstreamHandler(http.server.BaseHTTPRequestHandler):
    authorization: str | None = None

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        type(self).authorization = self.headers.get("Authorization")
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AuthProxyTest(unittest.TestCase):
    def test_replaces_local_token_with_upstream_secret(self) -> None:
        upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as directory:
            port_file = Path(directory) / "port"
            environment = dict(os.environ)
            environment.update(
                {
                    "UPSTREAM_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/v1",
                    "UPSTREAM_API_KEY": "real-upstream-secret",
                    "PROXY_CLIENT_TOKEN": "local-throwaway-token",
                }
            )
            proxy = subprocess.Popen(
                ["python3", str(ROOT / "scripts/auth_proxy.py"), "--port-file", str(port_file)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                for _ in range(50):
                    if port_file.is_file():
                        break
                    time.sleep(0.02)
                self.assertTrue(port_file.is_file())
                port = port_file.read_text(encoding="ascii")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/v1/chat/completions",
                    data=b"{}",
                    headers={"Authorization": "Bearer local-throwaway-token"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response), {"ok": True})
                self.assertEqual(UpstreamHandler.authorization, "Bearer real-upstream-secret")

                unauthorized = urllib.request.Request(
                    f"http://127.0.0.1:{port}/v1/chat/completions",
                    data=b"{}",
                    headers={"Authorization": "Bearer wrong"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(unauthorized, timeout=5)
                self.assertEqual(raised.exception.code, 401)
            finally:
                proxy.terminate()
                proxy.wait(timeout=5)
                upstream.shutdown()
                upstream.server_close()


if __name__ == "__main__":
    unittest.main()
