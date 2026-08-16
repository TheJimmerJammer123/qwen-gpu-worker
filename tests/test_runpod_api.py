#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runpod_api", ROOT / "scripts/runpod-api.py")
assert SPEC is not None and SPEC.loader is not None
runpod_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runpod_api)


class RunPodApiTest(unittest.TestCase):
    def test_optional_list_accepts_no_content_as_empty(self) -> None:
        self.assertEqual(runpod_api.optional_list(None, "registries"), [])

    def test_sanitizes_pod_environment_values(self) -> None:
        pod = runpod_api.sanitized_pod(
            {
                "id": "pod-id",
                "name": "worker",
                "env": {"LLAMA_API_KEY": "must-not-leak", "PROFILE": "baseline"},
                "gpu": {"displayName": "RTX 3090", "count": 1},
            }
        )
        self.assertEqual(pod["environment_keys"], ["LLAMA_API_KEY", "PROFILE"])
        self.assertNotIn("must-not-leak", repr(pod))

    def test_sanitizes_create_response_image_field(self) -> None:
        pod = runpod_api.sanitized_pod({"id": "pod-id", "image": "example/qwen:tag"})
        self.assertEqual(pod["image"], "example/qwen:tag")

    def test_reports_non_secret_direct_tcp_endpoint(self) -> None:
        pod = runpod_api.sanitized_pod(
            {"id": "pod-id", "publicIp": "192.0.2.1", "portMappings": {"8000": 12345}}
        )
        self.assertEqual(pod["direct_tcp_base_url"], "http://192.0.2.1:12345/v1")
        self.assertEqual(pod["proxy_base_url"], "https://pod-id-8000.proxy.runpod.net/v1")

    def test_sanitizes_template_environment_values(self) -> None:
        template = runpod_api.sanitized_template(
            {
                "id": "template-id",
                "name": "worker",
                "env": {"LLAMA_API_KEY": "must-not-leak"},
                "imageName": "example/qwen:tag",
            }
        )
        self.assertEqual(template["environment_keys"], ["LLAMA_API_KEY"])
        self.assertNotIn("must-not-leak", repr(template))

    def test_prototype_payload_is_scoped_to_one_3090(self) -> None:
        env = {
            "LLAMA_API_KEY": "a" * 64,
            "QWEN_WORKER_IMAGE": "ghcr.io/example/qwen-worker:b10453",
            "GPU_HOURLY_COST_USD": "0.22",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            payload = runpod_api.prototype_payload()
        self.assertEqual(payload["gpuTypeIds"], ["NVIDIA GeForce RTX 3090"])
        self.assertEqual(payload["gpuCount"], 1)
        self.assertEqual(payload["cloudType"], "COMMUNITY")
        self.assertFalse(payload["interruptible"])
        self.assertEqual(payload["ports"], ["8000/http", "8000/tcp"])
        self.assertEqual(payload["volumeMountPath"], "/models")
        self.assertEqual(payload["env"]["PROFILE"], "baseline")

    def test_rejects_short_server_key(self) -> None:
        with mock.patch.dict(os.environ, {"LLAMA_API_KEY": "short"}, clear=True):
            with self.assertRaisesRegex(SystemExit, "at least 32"):
                runpod_api.prototype_payload()

    def test_rejects_non_prototype_mutation(self) -> None:
        with mock.patch.object(
            runpod_api, "find_pod", return_value={"id": "old", "name": "jammervision"}
        ):
            with self.assertRaisesRegex(SystemExit, "outside the Qwen prototype"):
                runpod_api.require_prototype_pod("old")


if __name__ == "__main__":
    unittest.main()
