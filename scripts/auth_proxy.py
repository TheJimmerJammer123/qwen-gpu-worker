#!/usr/bin/env python3
"""Local bearer-token proxy that keeps the upstream key out of Qwen sandbox args."""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class AuthProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _proxy(self) -> None:
        server = self.server
        assert isinstance(server, AuthProxyServer)
        if self.headers.get("Authorization") != f"Bearer {server.client_token}":
            self.send_error(401)
            return
        if not self.path.startswith(server.upstream.path.rstrip("/") + "/"):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP | {"authorization", "host", "content-length"}
        }
        headers["Authorization"] = f"Bearer {server.upstream_key}"
        if body is not None:
            headers["Content-Length"] = str(len(body))

        connection_class = (
            http.client.HTTPSConnection if server.upstream.scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_class(
            server.upstream.hostname,
            server.upstream.port,
            timeout=1800,
        )
        try:
            target = self.path
            connection.request(self.command, target, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            has_content_length = False
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP:
                    self.send_header(key, value)
                    has_content_length = has_content_length or key.lower() == "content-length"
            if not has_content_length:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            while chunk := response.read1(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException):
            self.send_error(502)
        finally:
            connection.close()

    do_DELETE = _proxy
    do_GET = _proxy
    do_PATCH = _proxy
    do_POST = _proxy
    do_PUT = _proxy


class AuthProxyServer(ThreadingHTTPServer):
    upstream: object
    upstream_key: str
    client_token: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port-file", type=Path, required=True)
    parser.add_argument("--bind-host", default="127.0.0.1")
    args = parser.parse_args()
    upstream_url = os.environ.get("UPSTREAM_BASE_URL", "")
    upstream_key = os.environ.get("UPSTREAM_API_KEY", "")
    client_token = os.environ.get("PROXY_CLIENT_TOKEN", "")
    upstream = urlsplit(upstream_url)
    if upstream.scheme not in {"http", "https"} or not upstream.hostname or not upstream.path:
        parser.error("UPSTREAM_BASE_URL must be an http(s) URL with a path")
    if not upstream_key or not client_token:
        parser.error("UPSTREAM_API_KEY and PROXY_CLIENT_TOKEN are required")

    try:
        bind_address = ipaddress.ip_address(args.bind_host)
    except ValueError:
        parser.error("--bind-host must be an IP address")
    if not (bind_address.is_loopback or bind_address.is_private):
        parser.error("--bind-host must be a loopback or private IP address")

    server = AuthProxyServer((args.bind_host, 0), AuthProxyHandler)
    server.upstream = upstream
    server.upstream_key = upstream_key
    server.client_token = client_token
    args.port_file.write_text(str(server.server_port), encoding="ascii")
    args.port_file.chmod(0o600)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        args.port_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
