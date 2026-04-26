"""Async Kubernetes client wrapper for read-only cluster queries.

Thin layer over kubernetes_asyncio. Designed for reuse by future
observability MCP tooling — keep the interface minimal and read-only.
"""

from __future__ import annotations

import asyncio
import logging

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient

logger = logging.getLogger(__name__)


_CPU_SUFFIXES = {"n": 1e-9, "u": 1e-6, "m": 1e-3}
_MEM_SUFFIXES = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


def _parse_cpu(s: str) -> float:
    """Parse a Kubernetes CPU quantity to cores (e.g. '618m' → 0.618)."""
    if not s:
        return 0.0
    if s[-1] in _CPU_SUFFIXES:
        return float(s[:-1]) * _CPU_SUFFIXES[s[-1]]
    return float(s)


def _parse_memory(s: str) -> float:
    """Parse a Kubernetes memory quantity to bytes."""
    if not s:
        return 0.0
    for suffix, mult in _MEM_SUFFIXES.items():
        if s.endswith(suffix):
            return float(s[: -len(suffix)]) * mult
    return float(s)


class KubernetesClient:
    """Lightweight async k8s client scoped to list operations."""

    def __init__(self) -> None:
        self._api: ApiClient | None = None

    async def _ensure_client(self) -> ApiClient:
        if self._api is None:
            config.load_incluster_config()
            self._api = ApiClient()
        return self._api

    async def count_nodes(self) -> int:
        api = await self._ensure_client()
        v1 = client.CoreV1Api(api)
        nodes = await v1.list_node()
        return len(nodes.items)

    async def count_pods(self) -> int:
        api = await self._ensure_client()
        v1 = client.CoreV1Api(api)
        pods = await v1.list_pod_for_all_namespaces()
        return len(pods.items)

    async def count_deployments(self) -> int:
        api = await self._ensure_client()
        apps = client.AppsV1Api(api)
        deps = await apps.list_deployment_for_all_namespaces()
        return len(deps.items)

    async def count_argocd_applications(self) -> int:
        api = await self._ensure_client()
        custom = client.CustomObjectsApi(api)
        result = await custom.list_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applications",
        )
        return len(result.get("items", []))

    async def get_argocd_app_status(
        self, name: str, namespace: str = "argocd"
    ) -> dict | None:
        """Return the raw status block of a single ArgoCD Application, or None on miss.

        Lets callers pull whatever subfield they need (operationState.finishedAt,
        sync.revision, health.status, ...) without baking field choices into the
        client.
        """
        api = await self._ensure_client()
        custom = client.CustomObjectsApi(api)
        try:
            result = await custom.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="applications",
                name=name,
            )
        except client.exceptions.ApiException:
            return None
        return result.get("status")

    async def aggregate_node_resources(self) -> dict[str, float]:
        """Sum CPU and memory across all nodes from the metrics API.

        Returns cores and bytes. Capacity comes from node.status.allocatable
        (what the scheduler can actually assign), not status.capacity.
        """
        api = await self._ensure_client()
        v1 = client.CoreV1Api(api)
        custom = client.CustomObjectsApi(api)

        nodes_resp, metrics_resp = await asyncio.gather(
            v1.list_node(),
            custom.list_cluster_custom_object(
                group="metrics.k8s.io", version="v1beta1", plural="nodes"
            ),
        )

        cpu_cap = mem_cap = 0.0
        for n in nodes_resp.items:
            alloc = n.status.allocatable or {}
            cpu_cap += _parse_cpu(alloc.get("cpu", "0"))
            mem_cap += _parse_memory(alloc.get("memory", "0"))

        cpu_used = mem_used = 0.0
        for item in metrics_resp.get("items", []):
            usage = item.get("usage", {})
            cpu_used += _parse_cpu(usage.get("cpu", "0"))
            mem_used += _parse_memory(usage.get("memory", "0"))

        return {
            "cpu_used_cores": cpu_used,
            "cpu_capacity_cores": cpu_cap,
            "memory_used_bytes": mem_used,
            "memory_capacity_bytes": mem_cap,
        }

    async def close(self) -> None:
        if self._api:
            await self._api.close()
            self._api = None
