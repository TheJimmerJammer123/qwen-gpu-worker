#!/usr/bin/env python3
"""Minimal RunPod REST client that never prints or persists credential values."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


API_ROOT = "https://rest.runpod.io/v1"


def request_json(path: str) -> Any:
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise SystemExit("error: RUNPOD_API_KEY is required")
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 204:
                return None
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1000]
        raise SystemExit(f"RunPod API HTTP {error.code}: {body}") from None


def sanitized_pod(pod: dict[str, Any]) -> dict[str, Any]:
    gpu = pod.get("gpu") if isinstance(pod.get("gpu"), dict) else {}
    machine = pod.get("machine") if isinstance(pod.get("machine"), dict) else {}
    return {
        "id": pod.get("id"),
        "name": pod.get("name"),
        "desired_status": pod.get("desiredStatus"),
        "cost_per_hour": pod.get("costPerHr"),
        "adjusted_cost_per_hour": pod.get("adjustedCostPerHr"),
        "image": pod.get("imageName"),
        "gpu": gpu.get("displayName") or machine.get("gpuDisplayName"),
        "gpu_count": gpu.get("count") or pod.get("gpuCount"),
        "cloud_type": pod.get("cloudType"),
        "container_disk_gb": pod.get("containerDiskInGb"),
        "volume_gb": pod.get("volumeInGb"),
        "environment_keys": sorted((pod.get("env") or {}).keys()),
        "registry_auth_id": pod.get("containerRegistryAuthId"),
        "last_started_at": pod.get("lastStartedAt"),
    }


def sanitized_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "image": template.get("imageName"),
        "is_public": template.get("isPublic"),
        "is_runpod": template.get("isRunpod"),
        "is_serverless": template.get("isServerless"),
        "ports": template.get("ports"),
        "container_disk_gb": template.get("containerDiskInGb"),
        "volume_gb": template.get("volumeInGb"),
        "volume_mount_path": template.get("volumeMountPath"),
        "environment_keys": sorted((template.get("env") or {}).keys()),
        "registry_auth_id": template.get("containerRegistryAuthId"),
    }


def require_list(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SystemExit(f"error: RunPod returned an invalid {name} response")
    return value


def optional_list(value: Any, name: str) -> list[dict[str, Any]]:
    """Treat RunPod's 204 response as an empty optional collection."""
    if value is None:
        return []
    return require_list(value, name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inventory", "list-pods"))
    args = parser.parse_args()
    if args.command == "list-pods":
        pods = require_list(request_json("/pods"), "Pods")
        print(json.dumps([sanitized_pod(pod) for pod in pods], indent=2, sort_keys=True))
    elif args.command == "inventory":
        pods = require_list(request_json("/pods"), "Pods")
        templates = require_list(request_json("/templates"), "templates")
        volumes = require_list(request_json("/networkvolumes"), "network volumes")
        registry_auth = optional_list(
            request_json("/containerregistryauth"), "container registry authentication"
        )
        result = {
            "pods": [sanitized_pod(pod) for pod in pods],
            "templates": [sanitized_template(template) for template in templates],
            "network_volumes": volumes,
            "registry_auth": [
                {"id": item.get("id"), "name": item.get("name")} for item in registry_auth
            ],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as error:
        print(f"RunPod API network error: {error.reason}", file=sys.stderr)
        raise SystemExit(1) from None
