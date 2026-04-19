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
    mock_session = _mock_session()

    with (
        patch("home.observability.stats.KubernetesClient", return_value=mock_client),
        patch("home.observability.stats.get_engine", return_value=MagicMock()),
        patch("sqlmodel.Session", return_value=mock_session),
    ):
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        result = await stats.build_stats()

    assert result["cluster"]["nodes"] == 4
    assert result["cluster"]["pods"] == 135
    assert result["cluster"]["deployments"] == 64
    assert result["cluster"]["argocd_apps"] == 28
    assert result["knowledge"]["facts"] == 1309
    assert result["knowledge"]["chunks"] == 5948
    assert result["knowledge"]["raw_inputs"] == 366
    assert result["platform"]["in_production_since"] == "2025-01"
    assert "cached_at" in result


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

    with patch("home.observability.stats.KubernetesClient", return_value=mock_client):
        result = await stats._query_cluster_counts()

    assert result["nodes"] == 0  # failed, falls back to 0
    assert result["pods"] == 10
