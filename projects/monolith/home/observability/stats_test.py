"""Tests for the public stats endpoint."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from home.observability import stats


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear module-level cache between tests."""
    stats._cache = None
    stats._cache_time = 0.0
    yield
    stats._cache = None
    stats._cache_time = 0.0


def _mock_k8s_client():
    """Return a mocked KubernetesClient with preset counts."""
    mock = MagicMock()
    mock.count_nodes = AsyncMock(return_value=4)
    mock.count_pods = AsyncMock(return_value=135)
    mock.count_deployments = AsyncMock(return_value=64)
    mock.count_argocd_applications = AsyncMock(return_value=28)
    mock.aggregate_node_resources = AsyncMock(
        return_value={
            "cpu_used_cores": 4.987,
            "cpu_capacity_cores": 32.0,
            "memory_used_bytes": 62.5 * 1024**3,
            "memory_capacity_bytes": 108.0 * 1024**3,
        }
    )
    mock.close = AsyncMock()
    return mock


def _mock_ch_client():
    """Mock ClickHouseClient that returns canned GPU values."""
    mock = MagicMock()
    queries = {
        "DCGM_FI_DEV_GPU_UTIL": 73.5,
        "DCGM_FI_DEV_FB_USED": 18432.0,  # 18 GiB in MiB
        "DCGM_FI_DEV_FB_FREE": 6144.0,  # 6 GiB in MiB
    }

    async def query_scalar(sql):
        for marker, value in queries.items():
            if marker in sql:
                return value
        return None

    mock.query_scalar = AsyncMock(side_effect=query_scalar)
    mock.close = AsyncMock()
    return mock


def _mock_session():
    """Return a mock SQLModel Session that returns preset counts."""
    session = MagicMock()
    call_count = 0
    expected = [1309, 5948, 366]

    def exec_side_effect(query):
        nonlocal call_count
        result = MagicMock()
        result.one.return_value = (expected[call_count],)
        call_count += 1
        return result

    session.exec = MagicMock(side_effect=exec_side_effect)
    return session


@pytest.mark.asyncio
async def test_build_stats_returns_expected_shape():
    mock_client = _mock_k8s_client()
    mock_ch = _mock_ch_client()
    mock_session = _mock_session()

    with (
        patch("home.observability.stats.KubernetesClient", return_value=mock_client),
        patch("home.observability.stats.ClickHouseClient", return_value=mock_ch),
        patch("home.observability.stats.get_engine", return_value=MagicMock()),
        patch("sqlmodel.Session", return_value=mock_session),
        patch(
            "home.observability.stats._query_deploy",
            new_callable=AsyncMock,
            return_value={
                "latest_commit_sha": "abc1234",
                "latest_commit_at": "2026-04-25T10:00:00Z",
                "deployed_at": "2026-04-25T10:05:00Z",
            },
        ),
    ):
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        result = await stats.build_stats()

    assert result["cluster"]["nodes"] == 4
    assert result["cluster"]["pods"] == 135
    assert result["cluster"]["deployments"] == 64
    assert result["cluster"]["argocd_apps"] == 28
    assert result["cluster"]["cpu_used_cores"] == 4.99
    assert result["cluster"]["cpu_capacity_cores"] == 32.0
    assert result["cluster"]["memory_used_gb"] == 62.5
    assert result["cluster"]["memory_capacity_gb"] == 108.0
    assert result["gpu"]["utilization_pct"] == 73.5
    assert result["gpu"]["memory_used_gb"] == 18.0
    assert result["gpu"]["memory_total_gb"] == 24.0
    assert result["knowledge"]["facts"] == 1309
    assert result["knowledge"]["chunks"] == 5948
    assert result["knowledge"]["raw_inputs"] == 366
    assert result["deploy"]["latest_commit_sha"] == "abc1234"
    assert result["deploy"]["deployed_at"] == "2026-04-25T10:05:00Z"
    assert result["platform"]["in_production_since"] == "2025-01"
    assert "cached_at" in result


@pytest.mark.asyncio
async def test_query_deploy_combines_github_and_argocd():
    commit_payload = {
        "sha": "abcdef1234567890",
        "commit": {"committer": {"date": "2026-04-25T10:00:00Z"}},
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json = MagicMock(return_value=commit_payload)
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    mock_k8s = MagicMock()
    mock_k8s.get_argocd_app_status = AsyncMock(
        return_value={"operationState": {"finishedAt": "2026-04-25T10:05:00Z"}}
    )
    mock_k8s.close = AsyncMock()

    with (
        patch("home.observability.stats.httpx.AsyncClient", return_value=mock_http),
        patch("home.observability.stats.KubernetesClient", return_value=mock_k8s),
    ):
        result = await stats._query_deploy()

    assert result["latest_commit_sha"] == "abcdef1"
    assert result["latest_commit_at"] == "2026-04-25T10:00:00Z"
    assert result["deployed_at"] == "2026-04-25T10:05:00Z"


@pytest.mark.asyncio
async def test_query_deploy_returns_partial_when_one_source_fails():
    """If GitHub is down but ArgoCD answers, the deployed_at item still surfaces."""
    mock_resp = MagicMock(status_code=503)
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    mock_k8s = MagicMock()
    mock_k8s.get_argocd_app_status = AsyncMock(
        return_value={"operationState": {"finishedAt": "2026-04-25T10:05:00Z"}}
    )
    mock_k8s.close = AsyncMock()

    with (
        patch("home.observability.stats.httpx.AsyncClient", return_value=mock_http),
        patch("home.observability.stats.KubernetesClient", return_value=mock_k8s),
    ):
        result = await stats._query_deploy()

    assert "latest_commit_sha" not in result
    assert result["deployed_at"] == "2026-04-25T10:05:00Z"


@pytest.mark.asyncio
async def test_get_cached_stats_uses_cache():
    fake_stats = {"cluster": {}, "cached_at": "test"}
    stats._cache = fake_stats
    stats._cache_time = time.monotonic()

    result = await stats.get_cached_stats()
    assert result is fake_stats


@pytest.mark.asyncio
async def test_get_cached_stats_refreshes_after_ttl():
    fake_stats = {"cluster": {}, "cached_at": "old"}
    stats._cache = fake_stats
    stats._cache_time = time.monotonic() - stats._CACHE_TTL - 1

    new_stats = {"cluster": {}, "cached_at": "new"}
    with patch(
        "home.observability.stats.build_stats",
        new_callable=AsyncMock,
        return_value=new_stats,
    ):
        result = await stats.get_cached_stats()

    assert result["cached_at"] == "new"


@pytest.mark.asyncio
async def test_cluster_counts_handles_k8s_errors():
    mock_client = _mock_k8s_client()
    mock_client.count_nodes = AsyncMock(side_effect=Exception("k8s unreachable"))
    mock_client.count_pods = AsyncMock(return_value=10)
    mock_client.count_deployments = AsyncMock(return_value=5)
    mock_client.count_argocd_applications = AsyncMock(return_value=2)
    mock_client.aggregate_node_resources = AsyncMock(
        side_effect=Exception("metrics-server unreachable")
    )

    with patch("home.observability.stats.KubernetesClient", return_value=mock_client):
        result = await stats._query_cluster_counts()

    assert result["nodes"] == 0  # failed, falls back to 0
    assert result["pods"] == 10
    # When aggregate_node_resources fails, the resource keys are simply absent.
    assert "cpu_used_cores" not in result
    assert "memory_used_gb" not in result
