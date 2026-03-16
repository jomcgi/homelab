"""Tests for ElevationCache and ElevationClient (elevation/client.py)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from client import (
    ElevationCache,
    ElevationClient,
    ElevationResult,
    batch_fetch_elevation,
    fetch_elevation,
)


# ---------------------------------------------------------------------------
# TestElevationCache
# ---------------------------------------------------------------------------


class TestElevationCache:
    @pytest.fixture
    def cache(self, tmp_path) -> ElevationCache:
        return ElevationCache(tmp_path / "test_cache.db")

    def test_init_creates_table(self, tmp_path):
        db = tmp_path / "cache.db"
        cache = ElevationCache(db)
        assert db.exists()

    def test_coord_key_rounds_to_five_decimals(self):
        assert ElevationCache._coord_key(49.123456789) == "49.12346"
        assert ElevationCache._coord_key(-123.0) == "-123.00000"
        assert ElevationCache._coord_key(0.0) == "0.00000"

    def test_get_returns_none_when_missing(self, cache):
        result = cache.get(49.0, -123.0)
        assert result is None

    def test_set_and_get_roundtrip(self, cache):
        cache.set(49.12345, -123.45678, 123.4)
        result = cache.get(49.12345, -123.45678)
        assert result == 123.4

    def test_set_stores_none_elevation(self, cache):
        """Cache should store None (no data) as well as numeric values."""
        cache.set(49.0, -123.0, None)
        # get() returns None both when not cached and when cached as None —
        # that's by design per the docstring. Verify it was stored via get_many.
        cached = cache.get_many([(49.0, -123.0)])
        key = (ElevationCache._coord_key(49.0), ElevationCache._coord_key(-123.0))
        assert key in cached
        assert cached[key] is None

    def test_set_overwrites_existing(self, cache):
        cache.set(49.0, -123.0, 100.0)
        cache.set(49.0, -123.0, 200.0)
        assert cache.get(49.0, -123.0) == 200.0

    def test_get_many_empty_coords(self, cache):
        result = cache.get_many([])
        assert result == {}

    def test_get_many_returns_only_cached(self, cache):
        cache.set(49.0, -123.0, 50.0)
        result = cache.get_many([(49.0, -123.0), (50.0, -124.0)])
        lat_key = ElevationCache._coord_key(49.0)
        lng_key = ElevationCache._coord_key(-123.0)
        assert (lat_key, lng_key) in result
        assert result[(lat_key, lng_key)] == 50.0
        # Second coord not in cache
        assert len(result) == 1

    def test_set_many_stores_multiple(self, cache):
        entries = [(49.0, -123.0, 10.0), (50.0, -124.0, 20.0), (51.0, -125.0, None)]
        cache.set_many(entries)
        assert cache.get(49.0, -123.0) == 10.0
        assert cache.get(50.0, -124.0) == 20.0

    def test_set_many_empty_is_noop(self, cache):
        # Should not raise
        cache.set_many([])
        stats = cache.stats()
        assert stats["total"] == 0

    def test_stats_empty_cache(self, cache):
        stats = cache.stats()
        assert stats == {"total": 0, "with_data": 0, "no_data": 0}

    def test_stats_with_entries(self, cache):
        cache.set(49.0, -123.0, 100.0)
        cache.set(50.0, -124.0, None)
        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["with_data"] == 1
        assert stats["no_data"] == 1

    def test_coordinate_precision_collisions(self, cache):
        """Coordinates that round to the same key share a cache entry."""
        # These differ only beyond 5 decimal places
        cache.set(49.000001, -123.000001, 55.0)
        # 49.000001 rounds to "49.00000", same as 49.0
        result = cache.get(49.0, -123.0)
        assert result == 55.0


# ---------------------------------------------------------------------------
# TestElevationClient
# ---------------------------------------------------------------------------


def _make_mock_response(status: int, json_data: dict | None = None):
    """Build a mock aiohttp response as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return resp, cm


class TestElevationClientFetchOne:
    @pytest.mark.asyncio
    async def test_fetch_one_returns_altitude(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        resp, cm = _make_mock_response(200, {"altitude": 42.0})
        session = MagicMock()
        session.get.return_value = cm
        client._session = session

        result = await client._fetch_one(49.0, -123.0)
        assert result == 42.0

    @pytest.mark.asyncio
    async def test_fetch_one_returns_none_on_404(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        resp, cm = _make_mock_response(404)
        session = MagicMock()
        session.get.return_value = cm
        client._session = session

        result = await client._fetch_one(49.0, -123.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_one_returns_none_on_exception(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        session = MagicMock()
        session.get.side_effect = Exception("connection refused")
        client._session = session

        result = await client._fetch_one(49.0, -123.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_one_raises_without_session(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        # _session is None by default
        with pytest.raises(RuntimeError, match="context manager"):
            await client._fetch_one(49.0, -123.0)


class TestElevationClientGetElevation:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client.cache.set(49.0, -123.0, 99.9)
        client._session = MagicMock()  # Should not be called

        result = await client.get_elevation(49.0, -123.0)
        assert result.elevation == 99.9
        assert result.cached is True
        client._session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_from_api_when_not_cached(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        resp, cm = _make_mock_response(200, {"altitude": 77.5})
        session = MagicMock()
        session.get.return_value = cm
        client._session = session

        result = await client.get_elevation(49.0, -123.0)
        assert result.elevation == 77.5
        assert result.cached is False

    @pytest.mark.asyncio
    async def test_caches_fetched_result(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        resp, cm = _make_mock_response(200, {"altitude": 55.0})
        session = MagicMock()
        session.get.return_value = cm
        client._session = session

        await client.get_elevation(49.0, -123.0)
        # Second call should use cache, not API
        cached = client.cache.get(49.0, -123.0)
        assert cached == 55.0

    @pytest.mark.asyncio
    async def test_caches_none_when_api_returns_no_data(self, tmp_path):
        """Even a None elevation result is cached to avoid re-fetching."""
        client = ElevationClient(tmp_path / "cache.db")
        resp, cm = _make_mock_response(404)
        session = MagicMock()
        session.get.return_value = cm
        client._session = session

        result = await client.get_elevation(49.0, -123.0)
        assert result.elevation is None

        cached = client.cache.get_many([(49.0, -123.0)])
        lat_key = ElevationCache._coord_key(49.0)
        lng_key = ElevationCache._coord_key(-123.0)
        assert (lat_key, lng_key) in cached


class TestElevationClientGetElevations:
    @pytest.mark.asyncio
    async def test_empty_coords_returns_empty(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client._session = MagicMock()

        results = await client.get_elevations([])
        assert results == []

    @pytest.mark.asyncio
    async def test_all_from_cache(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client.cache.set(49.0, -123.0, 10.0)
        client.cache.set(50.0, -124.0, 20.0)
        session = MagicMock()
        session.get.assert_not_called  # Should not be hit
        client._session = session

        results = await client.get_elevations([(49.0, -123.0), (50.0, -124.0)])
        assert len(results) == 2
        assert all(r.cached for r in results)
        assert results[0].elevation == 10.0
        assert results[1].elevation == 20.0

    @pytest.mark.asyncio
    async def test_fetches_uncached_in_batch(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")

        call_count = 0

        async def fake_fetch(lat, lng):
            nonlocal call_count
            call_count += 1
            return lat * 1.0  # Return lat as elevation for testing

        client._fetch_one = fake_fetch
        client._session = MagicMock()

        results = await client.get_elevations([(49.0, -123.0), (50.0, -124.0)])
        assert call_count == 2
        assert results[0].elevation == 49.0
        assert results[1].elevation == 50.0

    @pytest.mark.asyncio
    async def test_progress_callback_called(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client.cache.set(49.0, -123.0, 10.0)  # One cached

        async def fake_fetch(lat, lng):
            return 20.0

        client._fetch_one = fake_fetch
        client._session = MagicMock()

        progress_calls = []

        def callback(completed, total):
            progress_calls.append((completed, total))

        await client.get_elevations(
            [(49.0, -123.0), (50.0, -124.0)],
            progress_callback=callback,
        )
        assert len(progress_calls) >= 1
        # Final call should have completed == total
        assert progress_calls[-1][1] == 2

    @pytest.mark.asyncio
    async def test_all_cached_progress_callback_called_once(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client.cache.set(49.0, -123.0, 10.0)
        client._session = MagicMock()

        calls = []
        await client.get_elevations([(49.0, -123.0)], progress_callback=lambda c, t: calls.append((c, t)))
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    @pytest.mark.asyncio
    async def test_batch_size_respected(self, tmp_path):
        """Verify batching with batch_size=1 processes sequentially."""
        client = ElevationClient(tmp_path / "cache.db")

        fetched = []

        async def fake_fetch(lat, lng):
            fetched.append((lat, lng))
            return lat

        client._fetch_one = fake_fetch
        client._session = MagicMock()

        coords = [(float(i), float(-i)) for i in range(3)]
        results = await client.get_elevations(coords, batch_size=1, batch_delay=0)
        assert len(results) == 3
        assert len(fetched) == 3

    @pytest.mark.asyncio
    async def test_mixed_cached_and_uncached(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")
        client.cache.set(49.0, -123.0, 5.0)  # Cached

        async def fake_fetch(lat, lng):
            return 99.0

        client._fetch_one = fake_fetch
        client._session = MagicMock()

        results = await client.get_elevations([(49.0, -123.0), (50.0, -124.0)])
        assert results[0].elevation == 5.0
        assert results[0].cached is True
        assert results[1].elevation == 99.0
        assert results[1].cached is False

    @pytest.mark.asyncio
    async def test_caches_fetched_results(self, tmp_path):
        client = ElevationClient(tmp_path / "cache.db")

        async def fake_fetch(lat, lng):
            return 42.0

        client._fetch_one = fake_fetch
        client._session = MagicMock()

        await client.get_elevations([(49.0, -123.0)])
        # Should now be cached
        assert client.cache.get(49.0, -123.0) == 42.0


# ---------------------------------------------------------------------------
# TestAsyncContextManager
# ---------------------------------------------------------------------------


class TestElevationClientContextManager:
    @pytest.mark.asyncio
    async def test_session_opened_and_closed(self, tmp_path):
        with patch("client.aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value = mock_session

            async with ElevationClient(tmp_path / "cache.db") as client:
                assert client._session is not None

            mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestConvenienceFunctions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    @pytest.mark.asyncio
    async def test_fetch_elevation(self, tmp_path):
        with patch("client.ElevationClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevation = AsyncMock(
                return_value=ElevationResult(lat=49.0, lng=-123.0, elevation=88.0)
            )
            mock_cls.return_value = mock_client

            result = await fetch_elevation(49.0, -123.0)
            assert result == 88.0

    @pytest.mark.asyncio
    async def test_batch_fetch_elevation(self, tmp_path):
        with patch("client.ElevationClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevations = AsyncMock(
                return_value=[
                    ElevationResult(lat=49.0, lng=-123.0, elevation=10.0),
                    ElevationResult(lat=50.0, lng=-124.0, elevation=None),
                ]
            )
            mock_cls.return_value = mock_client

            results = await batch_fetch_elevation([(49.0, -123.0), (50.0, -124.0)])
            assert results == [10.0, None]
