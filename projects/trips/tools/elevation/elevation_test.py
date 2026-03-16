"""Tests for the elevation client and cache."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from client import (
    ElevationCache,
    ElevationClient,
)


# ---------------------------------------------------------------------------
# ElevationCache tests
# ---------------------------------------------------------------------------


class TestElevationCacheInit:
    """SQLite initialisation."""

    def test_creates_table(self, tmp_path):
        db = tmp_path / "test.db"
        ElevationCache(db)
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='elevations'"
            ).fetchall()
        assert len(rows) == 1

    def test_idempotent_init(self, tmp_path):
        """Calling __init__ twice must not raise (CREATE TABLE IF NOT EXISTS)."""
        db = tmp_path / "test.db"
        ElevationCache(db)
        ElevationCache(db)  # should not raise


class TestElevationCacheCoordKey:
    """Coordinate key precision."""

    def test_rounds_to_five_decimal_places(self, tmp_path):
        cache = ElevationCache(tmp_path / "test.db")
        assert cache._coord_key(45.123456789) == "45.12346"
        assert cache._coord_key(-122.999994) == "-122.99999"

    def test_same_key_for_nearby_coords(self, tmp_path):
        """Two coords within ~1 m should map to the same key."""
        cache = ElevationCache(tmp_path / "test.db")
        # Both have a 6th decimal < 5, so both round to 45.00000 at 5dp.
        assert cache._coord_key(45.000001) == cache._coord_key(45.000003)


class TestElevationCacheGetSet:
    """Cache hit/miss and set behaviour."""

    @pytest.fixture
    def cache(self, tmp_path):
        return ElevationCache(tmp_path / "elev.db")

    def test_cache_miss_returns_none(self, cache):
        result = cache.get(45.0, -122.0)
        assert result is None

    def test_cache_hit_returns_elevation(self, cache):
        cache.set(45.0, -122.0, 123.4)
        result = cache.get(45.0, -122.0)
        assert result == pytest.approx(123.4)

    def test_cache_stores_none_elevation(self, cache):
        """API returning no data should also be cached (avoids repeated requests)."""
        cache.set(45.0, -122.0, None)
        # get() returns None both for "not cached" and "cached as None".
        # Distinguish via get_many which only returns keys present in the DB.
        keys = cache.get_many([(45.0, -122.0)])
        assert ("45.00000", "-122.00000") in keys
        assert keys[("45.00000", "-122.00000")] is None

    def test_set_overwrites_existing(self, cache):
        cache.set(45.0, -122.0, 100.0)
        cache.set(45.0, -122.0, 200.0)
        assert cache.get(45.0, -122.0) == pytest.approx(200.0)

    def test_precision_key_collision(self, cache):
        """Coords that differ only after 5 dp should overwrite each other."""
        cache.set(45.000001, -122.0, 50.0)
        # 45.000003 has a 6th decimal < 5 so it rounds to the same key (45.00000)
        cache.set(45.000003, -122.0, 60.0)
        assert cache.get(45.000001, -122.0) == pytest.approx(60.0)


class TestElevationCacheGetMany:
    """Batch cache lookup."""

    @pytest.fixture
    def cache(self, tmp_path):
        return ElevationCache(tmp_path / "elev.db")

    def test_empty_input(self, cache):
        assert cache.get_many([]) == {}

    def test_all_miss(self, cache):
        result = cache.get_many([(45.0, -122.0), (46.0, -123.0)])
        assert result == {}

    def test_partial_hit(self, cache):
        cache.set(45.0, -122.0, 100.0)
        result = cache.get_many([(45.0, -122.0), (46.0, -123.0)])
        assert ("45.00000", "-122.00000") in result
        assert ("46.00000", "-123.00000") not in result

    def test_all_hit(self, cache):
        cache.set(45.0, -122.0, 100.0)
        cache.set(46.0, -123.0, 200.0)
        result = cache.get_many([(45.0, -122.0), (46.0, -123.0)])
        assert len(result) == 2


class TestElevationCacheSetMany:
    """Batch insert."""

    @pytest.fixture
    def cache(self, tmp_path):
        return ElevationCache(tmp_path / "elev.db")

    def test_empty_input(self, cache):
        cache.set_many([])  # should not raise

    def test_inserts_multiple(self, cache):
        cache.set_many([(45.0, -122.0, 100.0), (46.0, -123.0, 200.0)])
        assert cache.get(45.0, -122.0) == pytest.approx(100.0)
        assert cache.get(46.0, -123.0) == pytest.approx(200.0)

    def test_upsert_behaviour(self, cache):
        cache.set_many([(45.0, -122.0, 100.0)])
        cache.set_many([(45.0, -122.0, 999.0)])
        assert cache.get(45.0, -122.0) == pytest.approx(999.0)


class TestElevationCacheStats:
    """Cache statistics tracking."""

    @pytest.fixture
    def cache(self, tmp_path):
        return ElevationCache(tmp_path / "elev.db")

    def test_empty_stats(self, cache):
        stats = cache.stats()
        assert stats == {"total": 0, "with_data": 0, "no_data": 0}

    def test_stats_with_data(self, cache):
        cache.set(45.0, -122.0, 100.0)
        cache.set(46.0, -123.0, None)
        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["with_data"] == 1
        assert stats["no_data"] == 1

    def test_stats_all_null(self, cache):
        cache.set(45.0, -122.0, None)
        cache.set(46.0, -123.0, None)
        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["with_data"] == 0
        assert stats["no_data"] == 2


# ---------------------------------------------------------------------------
# ElevationClient tests
# ---------------------------------------------------------------------------


class TestElevationClientContextManager:
    """Session lifecycle."""

    @pytest.mark.asyncio
    async def test_session_created_on_enter(self, tmp_path):
        client = ElevationClient(tmp_path / "elev.db")
        async with client:
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_session_closed_on_exit(self, tmp_path):
        client = ElevationClient(tmp_path / "elev.db")
        async with client:
            pass
        # After exit the session is closed (we just check it doesn't raise)


class TestElevationClientFetchOne:
    """_fetch_one HTTP interaction."""

    @pytest.mark.asyncio
    async def test_returns_altitude_on_200(self, tmp_path):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"altitude": 250.5})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        client = ElevationClient(tmp_path / "elev.db")
        client._session = mock_session

        result = await client._fetch_one(45.0, -122.0)
        assert result == pytest.approx(250.5)

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self, tmp_path):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        client = ElevationClient(tmp_path / "elev.db")
        client._session = mock_session

        result = await client._fetch_one(45.0, -122.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, tmp_path):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("network error")

        client = ElevationClient(tmp_path / "elev.db")
        client._session = mock_session

        result = await client._fetch_one(45.0, -122.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_without_session(self, tmp_path):
        client = ElevationClient(tmp_path / "elev.db")
        # _session is None — must raise RuntimeError
        with pytest.raises(RuntimeError, match="context manager"):
            await client._fetch_one(45.0, -122.0)


class TestElevationClientGetElevation:
    """get_elevation cache integration."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self, tmp_path):
        db = tmp_path / "elev.db"
        cache = ElevationCache(db)
        cache.set(45.0, -122.0, 300.0)

        client = ElevationClient(db)
        mock_session = MagicMock()
        client._session = mock_session

        result = await client.get_elevation(45.0, -122.0)

        assert result.elevation == pytest.approx(300.0)
        assert result.cached is True
        mock_session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_caches(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)

        # Patch _fetch_one so we don't hit the network
        client._fetch_one = AsyncMock(return_value=150.0)
        client._session = MagicMock()  # satisfy the session check in real _fetch_one

        result = await client.get_elevation(45.0, -122.0)

        assert result.elevation == pytest.approx(150.0)
        assert result.cached is False
        # Verify it was written to cache
        assert client.cache.get(45.0, -122.0) == pytest.approx(150.0)


class TestElevationClientGetElevations:
    """get_elevations batch fetching and rate limiting."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, tmp_path):
        client = ElevationClient(tmp_path / "elev.db")
        client._session = MagicMock()
        results = await client.get_elevations([])
        assert results == []

    @pytest.mark.asyncio
    async def test_all_cached(self, tmp_path):
        db = tmp_path / "elev.db"
        cache = ElevationCache(db)
        cache.set(45.0, -122.0, 100.0)
        cache.set(46.0, -123.0, 200.0)

        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=999.0)
        client._session = MagicMock()

        results = await client.get_elevations([(45.0, -122.0), (46.0, -123.0)])

        assert len(results) == 2
        assert all(r.cached for r in results)
        client._fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_uncached_fetched_and_cached(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=42.0)
        client._session = MagicMock()

        results = await client.get_elevations([(45.0, -122.0)])

        assert len(results) == 1
        assert results[0].elevation == pytest.approx(42.0)
        assert results[0].cached is False
        # Should be cached now
        assert client.cache.get(45.0, -122.0) == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_progress_callback_called(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=10.0)
        client._session = MagicMock()

        calls = []
        await client.get_elevations(
            [(45.0, -122.0), (46.0, -123.0)],
            progress_callback=lambda done, total: calls.append((done, total)),
        )

        assert len(calls) > 0
        # Final call should report all done
        assert calls[-1][0] == calls[-1][1]

    @pytest.mark.asyncio
    async def test_batch_delay_called_between_batches(self, tmp_path):
        """asyncio.sleep should be called between batches when more than one batch exists."""
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=10.0)
        client._session = MagicMock()

        coords = [(45.0 + i * 0.001, -122.0) for i in range(6)]

        with patch("client.asyncio.sleep") as mock_sleep:
            await client.get_elevations(coords, batch_size=3, batch_delay=0.1)

        mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_mixed_cached_and_uncached(self, tmp_path):
        db = tmp_path / "elev.db"
        cache = ElevationCache(db)
        cache.set(45.0, -122.0, 100.0)

        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=200.0)
        client._session = MagicMock()

        results = await client.get_elevations([(45.0, -122.0), (46.0, -123.0)])

        cached_results = [r for r in results if r.cached]
        fetched_results = [r for r in results if not r.cached]
        assert len(cached_results) == 1
        assert len(fetched_results) == 1
        assert cached_results[0].elevation == pytest.approx(100.0)
        assert fetched_results[0].elevation == pytest.approx(200.0)
