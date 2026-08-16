#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SummaryTest(unittest.TestCase):
    def test_aggregates_success_failure_speed_vram_and_cost(self) -> None:
        records = [
            {
                "profile": "baseline",
                "success": True,
                "prompt_tokens_per_second": 100,
                "output_tokens_per_second": 20,
                "wall_clock_seconds": 10,
                "gpu": {"peak_memory_used_mib": 21000},
                "gpu_hours": 0.002,
                "estimated_cost_usd": 0.001,
                "retries": 1,
            },
            {
                "profile": "baseline",
                "success": True,
                "prompt_tokens_per_second": 120,
                "output_tokens_per_second": 24,
                "wall_clock_seconds": 8,
                "gpu": {"peak_memory_used_mib": 21500},
                "gpu_hours": 0.003,
                "estimated_cost_usd": 0.002,
                "retries": 0,
            },
            {"profile": "baseline", "success": False, "gpu_hours": 0.001, "estimated_cost_usd": 0.001},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.jsonl"
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            output = subprocess.check_output(
                ["python3", str(ROOT / "scripts/summarize-benchmarks.py"), str(path)], text=True
            )
        summary = json.loads(output)["baseline"]
        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["retries"], 1)
        self.assertEqual(summary["median_prompt_tokens_per_second"], 110)
        self.assertEqual(summary["median_output_tokens_per_second"], 22)
        self.assertEqual(summary["max_peak_vram_mib"], 21500)
        self.assertEqual(summary["gpu_hours"], 0.006)
        self.assertEqual(summary["estimated_cost_usd"], 0.004)


if __name__ == "__main__":
    unittest.main()
