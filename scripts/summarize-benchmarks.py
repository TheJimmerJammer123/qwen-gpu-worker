#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def median(records: list[dict[str, Any]], key: str) -> float | None:
    values = [float(record[key]) for record in records if record.get(key) is not None]
    return round(statistics.median(values), 3) if values else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with args.path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            groups[str(record["profile"])].append(record)
    summary = {}
    for profile, records in sorted(groups.items()):
        successes = [record for record in records if record.get("success")]
        summary[profile] = {
            "runs": len(records),
            "successes": len(successes),
            "failures": len(records) - len(successes),
            "retries": sum(int(record.get("retries", 0)) for record in records),
            "median_prompt_tokens_per_second": median(successes, "prompt_tokens_per_second"),
            "median_output_tokens_per_second": median(successes, "output_tokens_per_second"),
            "median_wall_clock_seconds": median(successes, "wall_clock_seconds"),
            "max_peak_vram_mib": max(
                (record.get("gpu", {}).get("peak_memory_used_mib", 0) for record in records if record.get("gpu")),
                default=None,
            ),
            "gpu_hours": round(sum(float(record.get("gpu_hours", 0)) for record in records), 6),
            "estimated_cost_usd": round(sum(float(record.get("estimated_cost_usd", 0)) for record in records), 4),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
