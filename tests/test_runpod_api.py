#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runpod_api", ROOT / "scripts/runpod-api.py")
assert SPEC is not None and SPEC.loader is not None
runpod_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runpod_api)


class RunPodApiTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
