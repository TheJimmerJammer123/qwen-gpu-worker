#!/usr/bin/env python3
"""Minimal RunPod REST client that never prints or persists credential values."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


API_ROOT = "https://rest.runpod.io/v1"
GRAPHQL_ROOT = "https://api.runpod.io/graphql"
PROTOTYPE_NAME_PREFIX = "qwen38-27b-llamacpp-"
DEFAULT_IMAGE = "ghcr.io/thejimmerjammer123/qwen-gpu-worker:b10453"


def request_json(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise SystemExit("error: RUNPOD_API_KEY is required")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "qwen-gpu-worker-prototype/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 204:
                return None
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1000]
        raise SystemExit(f"RunPod API HTTP {error.code}: {body}") from None


def graphql_json(query: str) -> dict[str, Any]:
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise SystemExit("error: RUNPOD_API_KEY is required")
    request = urllib.request.Request(
        GRAPHQL_ROOT,
        data=json.dumps({"query": query}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "qwen-gpu-worker-prototype/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1000]
        raise SystemExit(f"RunPod GraphQL HTTP {error.code}: {body}") from None
    if not isinstance(result, dict) or result.get("errors"):
        raise SystemExit("error: RunPod returned an invalid GraphQL response")
    return result


def sanitized_pod(pod: dict[str, Any]) -> dict[str, Any]:
    gpu = pod.get("gpu") if isinstance(pod.get("gpu"), dict) else {}
    machine = pod.get("machine") if isinstance(pod.get("machine"), dict) else {}
    port_mappings = pod.get("portMappings") if isinstance(pod.get("portMappings"), dict) else {}
    direct_port = port_mappings.get("8000") or port_mappings.get(8000)
    public_ip = pod.get("publicIp")
    return {
        "id": pod.get("id"),
        "name": pod.get("name"),
        "desired_status": pod.get("desiredStatus"),
        "cost_per_hour": pod.get("costPerHr"),
        "adjusted_cost_per_hour": pod.get("adjustedCostPerHr"),
        "image": pod.get("imageName") or pod.get("image"),
        "gpu": gpu.get("displayName") or machine.get("gpuDisplayName"),
        "gpu_count": gpu.get("count") or pod.get("gpuCount"),
        "cloud_type": pod.get("cloudType"),
        "container_disk_gb": pod.get("containerDiskInGb"),
        "volume_gb": pod.get("volumeInGb"),
        "environment_keys": sorted((pod.get("env") or {}).keys()),
        "registry_auth_id": pod.get("containerRegistryAuthId"),
        "last_started_at": pod.get("lastStartedAt"),
        "ports": pod.get("ports"),
        "public_ip_available": bool(public_ip),
        "port_mapping_keys": sorted(str(key) for key in port_mappings),
        "proxy_base_url": (
            f"https://{pod.get('id')}-8000.proxy.runpod.net/v1" if pod.get("id") else None
        ),
        "direct_tcp_base_url": (
            f"http://{public_ip}:{direct_port}/v1" if public_ip and direct_port else None
        ),
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


def prototype_payload() -> dict[str, Any]:
    image = os.environ.get("QWEN_WORKER_IMAGE", DEFAULT_IMAGE)
    if not re.fullmatch(r"[a-z0-9.-]+/[a-z0-9._/-]+:[A-Za-z0-9._-]+", image):
        raise SystemExit("error: QWEN_WORKER_IMAGE must be a pinned registry image tag")
    api_key = os.environ.get("LLAMA_API_KEY")
    if not api_key or len(api_key) < 32:
        raise SystemExit("error: LLAMA_API_KEY must be a fresh secret of at least 32 characters")
    hourly_cost = os.environ.get("GPU_HOURLY_COST_USD", "0.22")
    try:
        cost = float(hourly_cost)
    except ValueError:
        raise SystemExit("error: GPU_HOURLY_COST_USD must be numeric") from None
    if not 0 < cost <= 1:
        raise SystemExit("error: GPU_HOURLY_COST_USD is outside the prototype safety range")

    return {
        "name": f"{PROTOTYPE_NAME_PREFIX}baseline",
        "imageName": image,
        "cloudType": "COMMUNITY",
        "computeType": "GPU",
        "gpuTypeIds": ["NVIDIA GeForce RTX 3090"],
        "gpuTypePriority": "custom",
        "gpuCount": 1,
        "interruptible": False,
        "containerDiskInGb": 20,
        "volumeInGb": 30,
        "volumeMountPath": "/models",
        "ports": ["8000/http", "8000/tcp"],
        "supportPublicIp": True,
        "allowedCudaVersions": ["12.8"],
        "minRAMPerGPU": 24,
        "minVCPUPerGPU": 4,
        "env": {
            "PROFILE": "baseline",
            "LLAMA_API_KEY": api_key,
            "GPU_HOURLY_COST_USD": str(cost),
        },
    }


def require_confirmation(args: argparse.Namespace, action: str) -> None:
    if not args.yes:
        raise SystemExit(f"error: {action} changes cloud resources; rerun with --yes")


def find_pod(pod_id: str) -> dict[str, Any]:
    pod = request_json(f"/pods/{pod_id}")
    if not isinstance(pod, dict):
        raise SystemExit("error: RunPod returned an invalid Pod response")
    return pod


def require_prototype_pod(pod_id: str) -> dict[str, Any]:
    pod = find_pod(pod_id)
    if not str(pod.get("name", "")).startswith(PROTOTYPE_NAME_PREFIX):
        raise SystemExit("error: refusing to mutate a Pod outside the Qwen prototype namespace")
    return pod


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "inventory",
            "list-pods",
            "gpu-offers",
            "get-pod",
            "create-prototype",
            "stop",
            "terminate",
        ),
    )
    parser.add_argument("--pod-id")
    parser.add_argument("--yes", action="store_true")
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
    elif args.command == "gpu-offers":
        result = graphql_json(
            """query { gpuTypes(input: { id: \"NVIDIA GeForce RTX 3090\" }) {
              id displayName memoryInGb secureCloud communityCloud
              lowestPrice(input: { gpuCount: 1 }) {
                stockStatus uninterruptablePrice availableGpuCounts
              }
            } }"""
        )
        offers = (result.get("data") or {}).get("gpuTypes")
        print(json.dumps(require_list(offers, "GPU offers"), indent=2, sort_keys=True))
    elif args.command == "get-pod":
        if not args.pod_id:
            raise SystemExit("error: --pod-id is required")
        print(json.dumps(sanitized_pod(find_pod(args.pod_id)), indent=2, sort_keys=True))
    elif args.command == "create-prototype":
        require_confirmation(args, "create-prototype")
        pods = require_list(request_json("/pods"), "Pods")
        duplicates = [
            pod
            for pod in pods
            if str(pod.get("name", "")).startswith(PROTOTYPE_NAME_PREFIX)
            and pod.get("desiredStatus") != "TERMINATED"
        ]
        if duplicates:
            ids = ", ".join(str(pod.get("id")) for pod in duplicates)
            raise SystemExit(f"error: prototype Pod already exists: {ids}")
        created = request_json("/pods", method="POST", payload=prototype_payload())
        if not isinstance(created, dict):
            raise SystemExit("error: RunPod returned an invalid create response")
        print(json.dumps(sanitized_pod(created), indent=2, sort_keys=True))
    elif args.command in {"stop", "terminate"}:
        require_confirmation(args, args.command)
        if not args.pod_id:
            raise SystemExit("error: --pod-id is required")
        pod = require_prototype_pod(args.pod_id)
        if args.command == "stop":
            changed = request_json(f"/pods/{args.pod_id}/stop", method="POST")
            if isinstance(changed, dict):
                pod = changed
            else:
                pod["desiredStatus"] = "EXITED"
            print(json.dumps(sanitized_pod(pod), indent=2, sort_keys=True))
        else:
            request_json(f"/pods/{args.pod_id}", method="DELETE")
            print(json.dumps({"id": args.pod_id, "terminated": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as error:
        print(f"RunPod API network error: {error.reason}", file=sys.stderr)
        raise SystemExit(1) from None
