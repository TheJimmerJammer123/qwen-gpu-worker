#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("benchmark", ROOT / "scripts/benchmark.py")
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class BenchmarkTest(unittest.TestCase):
    def test_run_once_records_required_measurements(self) -> None:
        response = {
            "choices": [{"finish_reason": "stop"}],
            "usage": {"prompt_tokens": 321, "completion_tokens": 123},
            "timings": {"prompt_per_second": 456.7, "predicted_per_second": 18.9},
        }
        gpu_samples = [
            {"name": "RTX 3090", "memory_used_mib": 20000, "memory_total_mib": 24576, "driver_version": "580"},
            {"name": "RTX 3090", "memory_used_mib": 22000, "memory_total_mib": 24576, "driver_version": "580"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "effective.json"
            config_path.write_text(
                json.dumps(
                    {
                        "profile": "baseline",
                        "model": "Qwen3.8-27B-Q4_K_M",
                        "context_size": 32768,
                        "speculative": {"enabled": False, "type": "none"},
                        "backend": {"name": "llama.cpp", "ref": "b10453"},
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                endpoint="http://example.test/v1",
                api_key="not-recorded",
                model="Qwen3.8-27B-Q4_K_M",
                temperature=1.0,
                top_p=0.95,
                top_k=20,
                max_tokens=128,
                server_config=config_path,
                hourly_cost=0.22,
                profile="baseline",
                quantization="Q4_K_M",
                context_size=32768,
                target_input_tokens=100,
                max_attempts=2,
            )
            def delayed_response(*_args: object, **_kwargs: object) -> dict[str, object]:
                time.sleep(0.25)
                return response

            with mock.patch.object(benchmark, "request_json", side_effect=delayed_response), mock.patch.object(
                benchmark, "gpu_snapshot", side_effect=gpu_samples
            ):
                record = benchmark.run_once(args, "test prompt", 1)

        self.assertTrue(record["success"])
        self.assertEqual(record["prompt_tokens"], 321)
        self.assertEqual(record["output_tokens"], 123)
        self.assertEqual(record["prompt_tokens_per_second"], 456.7)
        self.assertEqual(record["output_tokens_per_second"], 18.9)
        self.assertEqual(record["gpu"]["name"], "RTX 3090")
        self.assertEqual(record["gpu"]["peak_memory_used_mib"], 22000)
        self.assertEqual(record["context_size"], 32768)
        self.assertEqual(record["requested_target_input_tokens"], 100)
        self.assertEqual(record["attempts"], 1)
        self.assertEqual(record["retries"], 0)
        self.assertFalse(record["speculative_enabled"])
        self.assertNotIn("api_key", record)

    def test_profile_mismatch_fails_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "effective.json"
            config_path.write_text(
                json.dumps(
                    {
                        "profile": "optimized",
                        "model": "Qwen3.8-27B-Q4_K_M",
                        "context_size": 65536,
                        "speculative": {"enabled": True, "type": "draft-mtp"},
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                endpoint="http://example.test/v1",
                api_key="not-recorded",
                model="Qwen3.8-27B-Q4_K_M",
                temperature=1.0,
                top_p=0.95,
                top_k=20,
                max_tokens=128,
                server_config=config_path,
                hourly_cost=0.22,
                profile="baseline",
                quantization="Q4_K_M",
                context_size=32768,
                target_input_tokens=0,
                max_attempts=2,
            )
            with mock.patch.object(benchmark, "request_json") as request, mock.patch.object(
                benchmark, "gpu_snapshot", return_value=None
            ):
                record = benchmark.run_once(args, "test prompt", 1)
        self.assertFalse(record["success"])
        self.assertIn("profile mismatch", record["error"])
        request.assert_not_called()

    def test_malformed_success_response_is_retried_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "effective.json"
            config_path.write_text(
                json.dumps(
                    {
                        "profile": "baseline",
                        "model": "Qwen3.8-27B-Q4_K_M",
                        "context_size": 32768,
                        "speculative": {"enabled": False, "type": "none"},
                    }
                ),
                encoding="utf-8",
            )
            args = Namespace(
                endpoint="http://example.test/v1",
                api_key="not-recorded",
                model="Qwen3.8-27B-Q4_K_M",
                temperature=1.0,
                top_p=0.95,
                top_k=20,
                max_tokens=128,
                server_config=config_path,
                hourly_cost=0.22,
                profile="baseline",
                quantization="Q4_K_M",
                context_size=32768,
                target_input_tokens=0,
                max_attempts=2,
            )
            with mock.patch.object(benchmark, "request_json", return_value={}) as request, mock.patch.object(
                benchmark, "gpu_snapshot", return_value=None
            ), mock.patch.object(benchmark.time, "sleep"):
                record = benchmark.run_once(args, "test prompt", 1)
        self.assertFalse(record["success"])
        self.assertEqual(record["attempts"], 2)
        self.assertEqual(record["retries"], 1)
        self.assertEqual(record["failure_classes"], ["ValueError", "ValueError"])
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
