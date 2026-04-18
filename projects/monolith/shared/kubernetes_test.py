"""Tests for the async Kubernetes client wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.kubernetes import KubernetesClient


@pytest.fixture
def k8s_client():
    return KubernetesClient()


@pytest.mark.asyncio
async def test_count_nodes(k8s_client):
    mock_api = MagicMock()
    mock_v1 = MagicMock()
    mock_v1.list_node = AsyncMock(
        return_value=MagicMock(items=[MagicMock(), MagicMock(), MagicMock()])
    )

    with (
        patch("shared.kubernetes.config.load_incluster_config"),
        patch("shared.kubernetes.ApiClient", return_value=mock_api),
        patch("shared.kubernetes.client.CoreV1Api", return_value=mock_v1),
    ):
        count = await k8s_client.count_nodes()

    assert count == 3


@pytest.mark.asyncio
async def test_count_argocd_applications(k8s_client):
    mock_api = MagicMock()
    mock_custom = MagicMock()
    mock_custom.list_namespaced_custom_object = AsyncMock(
        return_value={
            "items": [{"metadata": {"name": "app1"}}, {"metadata": {"name": "app2"}}]
        }
    )

    with (
        patch("shared.kubernetes.config.load_incluster_config"),
        patch("shared.kubernetes.ApiClient", return_value=mock_api),
        patch("shared.kubernetes.client.CustomObjectsApi", return_value=mock_custom),
    ):
        count = await k8s_client.count_argocd_applications()

    assert count == 2


@pytest.mark.asyncio
async def test_close_cleans_up(k8s_client):
    mock_api = MagicMock()
    mock_api.close = AsyncMock()

    with (
        patch("shared.kubernetes.config.load_incluster_config"),
        patch("shared.kubernetes.ApiClient", return_value=mock_api),
    ):
        # Force client creation
        await k8s_client._ensure_client()
        await k8s_client.close()

    mock_api.close.assert_called_once()
    assert k8s_client._api is None
