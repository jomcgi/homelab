"""Tests for the async Kubernetes client wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.kubernetes import KubernetesClient, _parse_cpu, _parse_memory


@pytest.fixture
def k8s_client():
    return KubernetesClient()


def test_parse_cpu_handles_milli_and_plain():
    assert _parse_cpu("618m") == pytest.approx(0.618)
    assert _parse_cpu("16") == 16.0
    assert _parse_cpu("500u") == pytest.approx(0.0005)
    assert _parse_cpu("") == 0.0


def test_parse_memory_handles_binary_and_decimal_suffixes():
    assert _parse_memory("8309276Ki") == 8309276 * 1024
    assert _parse_memory("131072Mi") == 131072 * 1024**2
    assert _parse_memory("4Gi") == 4 * 1024**3
    assert _parse_memory("1000K") == 1_000_000
    assert _parse_memory("") == 0.0


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
async def test_aggregate_node_resources_sums_cpu_and_memory(k8s_client):
    mock_api = MagicMock()
    mock_v1 = MagicMock()
    mock_custom = MagicMock()

    node_a = MagicMock()
    node_a.status.allocatable = {"cpu": "16", "memory": "65536Mi"}
    node_b = MagicMock()
    node_b.status.allocatable = {"cpu": "8", "memory": "32768Mi"}
    mock_v1.list_node = AsyncMock(return_value=MagicMock(items=[node_a, node_b]))

    mock_custom.list_cluster_custom_object = AsyncMock(
        return_value={
            "items": [
                {
                    "metadata": {"name": "node-a"},
                    "usage": {"cpu": "1500m", "memory": "20480Mi"},
                },
                {
                    "metadata": {"name": "node-b"},
                    "usage": {"cpu": "500m", "memory": "10240Mi"},
                },
            ]
        }
    )

    with (
        patch("shared.kubernetes.config.load_incluster_config"),
        patch("shared.kubernetes.ApiClient", return_value=mock_api),
        patch("shared.kubernetes.client.CoreV1Api", return_value=mock_v1),
        patch("shared.kubernetes.client.CustomObjectsApi", return_value=mock_custom),
    ):
        result = await k8s_client.aggregate_node_resources()

    assert result["cpu_used_cores"] == pytest.approx(2.0)
    assert result["cpu_capacity_cores"] == pytest.approx(24.0)
    assert result["memory_used_bytes"] == pytest.approx(30720 * 1024**2)
    assert result["memory_capacity_bytes"] == pytest.approx(98304 * 1024**2)


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
