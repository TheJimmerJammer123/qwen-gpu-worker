#!/usr/bin/env python3
"""Run one or more non-streaming llama.cpp OpenAI benchmarks and append JSONL."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def gpu_snapshot() -> dict[str, Any] | None:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).splitlines()[0]
        name, used, total, driver = [part.strip() for part in output.split(",", 3)]
        return {
            "name": name,
            "memory_used_mib": int(used),
            "memory_total_mib": int(total),
            "driver_version": driver,
        }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def request_json(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("server returned a non-object JSON response")
    return value


def request_speculative_metrics(endpoint: str, api_key: str) -> dict[str, float]:
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    request = urllib.request.Request(
        f"{base}/metrics",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}
    metrics: dict[str, float] = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, raw_value = line.rpartition(" ")
        lowered = name.lower()
        if not separator or not any(word in lowered for word in ("draft", "spec", "accept")):
            continue
        try:
            metrics[name] = float(raw_value)
        except ValueError:
            continue
    return metrics


def validate_server_config(args: argparse.Namespace, config: dict[str, Any] | None) -> None:
    if config is None:
        raise ValueError("effective server configuration is missing")
    expected_speculation = args.profile == "optimized"
    expected_speculation_type = "draft-mtp" if expected_speculation else "none"
    checks = {
        "profile": (config.get("profile"), args.profile),
        "model": (config.get("model"), args.model),
        "context_size": (config.get("context_size"), args.context_size),
        "speculative.enabled": (
            bool(config.get("speculative", {}).get("enabled", False)),
            expected_speculation,
        ),
        "speculative.type": (config.get("speculative", {}).get("type"), expected_speculation_type),
    }
    mismatches = [
        f"{name}: effective={actual!r} requested={expected!r}"
        for name, (actual, expected) in checks.items()
        if actual != expected
    ]
    if mismatches:
        raise ValueError("benchmark/server profile mismatch: " + "; ".join(mismatches))


def expand_prompt(prompt: str, target_input_tokens: int) -> str:
    if target_input_tokens <= 0:
        return prompt
    # " repository" is normally one tokenizer token. The server-reported usage is
    # authoritative; this target only creates a stable, compressible long prompt.
    return f"{prompt}\n\nContext-capacity filler follows:\n" + (" repository" * target_input_tokens)


def validate_response(response: dict[str, Any]) -> None:
    choices = response.get("choices")
    usage = response.get("usage")
    timings = response.get("timings")
    if not isinstance(choices, list) or not choices:
        raise ValueError("response has no completion choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("completion choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str) or not message["content"].strip():
        raise ValueError("completion choice has no nonempty message content")
    if not isinstance(usage, dict) or usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
        raise ValueError("response is missing token usage")
    if not isinstance(timings, dict) or timings.get("prompt_per_second") is None or timings.get("predicted_per_second") is None:
        raise ValueError("response is missing llama.cpp timings")


def run_once(args: argparse.Namespace, prompt: str, sequence: int) -> dict[str, Any]:
    config = load_json(args.server_config)
    samples: list[dict[str, Any]] = []
    stop = threading.Event()

    def sample_gpu() -> None:
        while not stop.wait(0.20):
            value = gpu_snapshot()
            if value is not None:
                samples.append(value)

    sampler = threading.Thread(target=sample_gpu, daemon=True)
    sampler.start()
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    error: str | None = None
    failure_classes: list[str] = []
    attempts = 0
    response: dict[str, Any] = {}
    server_speculative_metrics: dict[str, float] = {}
    try:
        validate_server_config(args, config)
        payload = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a precise senior software engineer."},
                {"role": "user", "content": f"{expand_prompt(prompt, args.target_input_tokens)}\n\nBenchmark nonce: {uuid.uuid4()}"},
            ],
            "temperature": args.temperature,
            "top_p": args.top_p,
            "top_k": args.top_k,
            "max_tokens": args.max_tokens,
            "stream": False,
            "cache_prompt": False,
        }
        for attempts in range(1, args.max_attempts + 1):
            try:
                response = request_json(f"{args.endpoint.rstrip('/')}/chat/completions", args.api_key, payload)
                validate_response(response)
                server_speculative_metrics = request_speculative_metrics(args.endpoint, args.api_key)
                error = None
                break
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionResetError,
                http.client.RemoteDisconnected,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                error = f"{type(exc).__name__}: {exc}"
                failure_classes.append(type(exc).__name__)
                if attempts < args.max_attempts:
                    time.sleep(min(2 ** (attempts - 1), 4))
    except ValueError as exc:
        error = f"{type(exc).__name__}: {exc}"
        failure_classes.append(type(exc).__name__)
    finally:
        elapsed = time.monotonic() - started
        stop.set()
        sampler.join(timeout=2)
        final_gpu = gpu_snapshot()
        if final_gpu is not None:
            samples.append(final_gpu)

    timings = response.get("timings") or {}
    usage = response.get("usage") or {}
    peak_used = max((sample["memory_used_mib"] for sample in samples), default=None)
    gpu = samples[-1] if samples else None
    if gpu is not None:
        gpu = dict(gpu)
        gpu["peak_memory_used_mib"] = peak_used

    hourly_cost = args.hourly_cost
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    speculative_metrics = {
        key: value
        for key, value in timings.items()
        if "draft" in key.lower() or "accept" in key.lower()
    }
    return {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "sequence": sequence,
        "started_at": started_wall.isoformat(),
        "success": error is None,
        "error": error,
        "profile": (config or {}).get("profile"),
        "requested_profile": args.profile,
        "model": args.model,
        "quantization": args.quantization,
        "gpu": gpu,
        "context_size": (config or {}).get("context_size", args.context_size),
        "prompt_tokens": usage.get("prompt_tokens", timings.get("prompt_n")),
        "requested_target_input_tokens": args.target_input_tokens,
        "output_tokens": usage.get("completion_tokens", timings.get("predicted_n")),
        "prompt_tokens_per_second": timings.get("prompt_per_second"),
        "output_tokens_per_second": timings.get("predicted_per_second"),
        "wall_clock_seconds": round(elapsed, 6),
        "gpu_hours": round(elapsed / 3600, 8),
        "estimated_cost_usd": round(elapsed / 3600 * hourly_cost, 6),
        "hourly_cost_usd": hourly_cost,
        "attempts": attempts,
        "retries": max(0, attempts - 1),
        "failure_classes": failure_classes,
        "backend_config": config,
        "server_usage": usage,
        "server_timings": timings,
        "speculative_enabled": bool((config or {}).get("speculative", {}).get("enabled", False)),
        "speculative_type": (config or {}).get("speculative", {}).get("type", "unknown"),
        "speculative_metrics": speculative_metrics,
        "server_speculative_metrics": server_speculative_metrics,
        "finish_reason": choice.get("finish_reason"),
        "response_text": message.get("content"),
        "reasoning_content": message.get("reasoning_content"),
        "host": {"platform": platform.platform(), "python": platform.python_version()},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=os.getenv("QWEN_GPU_BASE_URL", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--api-key", default=os.getenv("QWEN_GPU_API_KEY"))
    parser.add_argument("--model", default="Qwen3.8-27B-Q4_K_M")
    parser.add_argument("--quantization", default="Q4_K_M")
    parser.add_argument("--profile", choices=("baseline", "optimized"), required=True)
    parser.add_argument("--context-size", type=int, choices=(32768, 65536), required=True)
    parser.add_argument("--prompt-file", type=Path, default=Path("/app/prompts/benchmark.md"))
    parser.add_argument("--server-config", type=Path, default=Path("/results/effective-config.json"))
    parser.add_argument("--output", type=Path, default=Path("/results/benchmarks.jsonl"))
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--target-input-tokens", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--hourly-cost", type=float, default=float(os.getenv("GPU_HOURLY_COST_USD", "0")))
    args = parser.parse_args()
    if not args.api_key:
        parser.error("set QWEN_GPU_API_KEY or pass --api-key")
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")
    if args.target_input_tokens < 0:
        parser.error("--target-input-tokens cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    with args.output.open("a", encoding="utf-8") as handle:
        for sequence in range(1, args.repeat + 1):
            record = run_once(args, prompt, sequence)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            print(json.dumps(record, indent=2, sort_keys=True))
            failures += int(not record["success"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
