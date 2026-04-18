"""Async Kubernetes client wrapper for read-only cluster queries.

Thin layer over kubernetes_asyncio. Designed for reuse by future
observability MCP tooling — keep the interface minimal and read-only.
"""

from __future__ import annotations

import logging

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient

logger = logging.getLogger(__name__)


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

    async def close(self) -> None:
        if self._api:
            await self._api.close()
            self._api = None
