"""Unit tests for elevation/client.py — convenience functions and edge cases.

Supplements elevation_test.py by covering:
- fetch_elevation: async convenience wrapper
- batch_fetch_elevation: batch async convenience wrapper
- ElevationResult dataclass
- ElevationCache._coord_key boundary conditions
- ElevationClient.get_elevations: no delay when only one batch
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

from client import (
    ElevationCache,
    ElevationClient,
    ElevationResult,
    batch_fetch_elevation,
    fetch_elevation,
)


# ---------------------------------------------------------------------------
# ElevationResult
# ---------------------------------------------------------------------------


class TestElevationResult:
    """Dataclass default values and field access."""

    def test_required_fields(self):
        result = ElevationResult(lat=45.0, lng=-122.0, elevation=300.0)
        assert result.lat == 45.0
        assert result.lng == -122.0
        assert result.elevation == 300.0

    def test_cached_defaults_false(self):
        result = ElevationResult(lat=45.0, lng=-122.0, elevation=None)
        assert result.cached is False

    def test_cached_can_be_set_true(self):
        result = ElevationResult(lat=45.0, lng=-122.0, elevation=100.0, cached=True)
        assert result.cached is True

    def test_elevation_can_be_none(self):
        result = ElevationResult(lat=45.0, lng=-122.0, elevation=None)
        assert result.elevation is None

    def test_equality(self):
        a = ElevationResult(lat=45.0, lng=-122.0, elevation=200.0, cached=False)
        b = ElevationResult(lat=45.0, lng=-122.0, elevation=200.0, cached=False)
        assert a == b

    def test_inequality_on_elevation(self):
        a = ElevationResult(lat=45.0, lng=-122.0, elevation=100.0)
        b = ElevationResult(lat=45.0, lng=-122.0, elevation=200.0)
        assert a != b


# ---------------------------------------------------------------------------
# ElevationCache._coord_key — boundary conditions
# ---------------------------------------------------------------------------


class TestElevationCacheCoordKeyBoundary:
    """Coordinate key rounding at boundaries not in the existing test."""

    @pytest.fixture
    def cache(self, tmp_path):
        return ElevationCache(tmp_path / "elev.db")

    def test_positive_boundary_rounds_up(self, cache):
        # 45.123455 rounds to 45.12346 (the '5' in the 6th decimal rounds up)
        key = cache._coord_key(45.1234550001)
        assert key == "45.12346"

    def test_negative_coordinate_has_negative_sign(self, cache):
        key = cache._coord_key(-122.5)
        assert key.startswith("-")

    def test_zero_coordinate(self, cache):
        assert cache._coord_key(0.0) == "0.00000"

    def test_very_large_positive(self, cache):
        key = cache._coord_key(179.99999)
        assert "179.99999" in key

    def test_very_large_negative(self, cache):
        key = cache._coord_key(-179.99999)
        assert "-179.99999" in key


# ---------------------------------------------------------------------------
# fetch_elevation convenience function
# ---------------------------------------------------------------------------


class TestFetchElevationConvenience:
    """fetch_elevation wraps ElevationClient in an async context manager."""

    @pytest.mark.asyncio
    async def test_returns_elevation_on_cache_hit(self, tmp_path):
        """fetch_elevation returns the elevation float from the client result."""
        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevation = AsyncMock(
                return_value=ElevationResult(lat=45.0, lng=-122.0, elevation=250.5)
            )

            result = await fetch_elevation(45.0, -122.0)

        assert result == pytest.approx(250.5)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_elevation(self, tmp_path):
        """fetch_elevation propagates None when API has no data for the point."""
        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevation = AsyncMock(
                return_value=ElevationResult(lat=45.0, lng=-122.0, elevation=None)
            )

            result = await fetch_elevation(45.0, -122.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_coordinates_to_client(self, tmp_path):
        """fetch_elevation forwards lat/lng to get_elevation."""
        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevation = AsyncMock(
                return_value=ElevationResult(lat=60.1, lng=-135.5, elevation=800.0)
            )

            await fetch_elevation(60.1, -135.5)

        mock_client.get_elevation.assert_awaited_once_with(60.1, -135.5)


# ---------------------------------------------------------------------------
# batch_fetch_elevation convenience function
# ---------------------------------------------------------------------------


class TestBatchFetchElevationConvenience:
    """batch_fetch_elevation wraps get_elevations and extracts elevation values."""

    @pytest.mark.asyncio
    async def test_returns_list_of_elevation_values(self, tmp_path):
        coords = [(45.0, -122.0), (46.0, -123.0)]
        results = [
            ElevationResult(lat=45.0, lng=-122.0, elevation=100.0),
            ElevationResult(lat=46.0, lng=-123.0, elevation=200.0),
        ]

        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevations = AsyncMock(return_value=results)

            elevations = await batch_fetch_elevation(coords)

        assert elevations == [pytest.approx(100.0), pytest.approx(200.0)]

    @pytest.mark.asyncio
    async def test_empty_coords_returns_empty_list(self):
        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevations = AsyncMock(return_value=[])

            result = await batch_fetch_elevation([])

        assert result == []

    @pytest.mark.asyncio
    async def test_none_elevations_preserved_in_output(self):
        """batch_fetch_elevation keeps None for points with no data."""
        coords = [(45.0, -122.0), (0.0, 0.0)]
        results = [
            ElevationResult(lat=45.0, lng=-122.0, elevation=100.0),
            ElevationResult(lat=0.0, lng=0.0, elevation=None),
        ]

        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevations = AsyncMock(return_value=results)

            elevations = await batch_fetch_elevation(coords)

        assert elevations[0] == pytest.approx(100.0)
        assert elevations[1] is None

    @pytest.mark.asyncio
    async def test_progress_callback_forwarded(self):
        """progress_callback is passed through to get_elevations."""
        coords = [(45.0, -122.0)]
        results = [ElevationResult(lat=45.0, lng=-122.0, elevation=50.0)]

        callback = MagicMock()

        with patch("client.ElevationClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_elevations = AsyncMock(return_value=results)

            await batch_fetch_elevation(coords, progress_callback=callback)

        mock_client.get_elevations.assert_awaited_once_with(
            coords, progress_callback=callback
        )


# ---------------------------------------------------------------------------
# ElevationClient.get_elevations — no sleep for single batch
# ---------------------------------------------------------------------------


class TestElevationClientSingleBatch:
    """asyncio.sleep is NOT called when all coords fit in one batch."""

    @pytest.mark.asyncio
    async def test_no_sleep_for_single_batch(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=10.0)
        client._session = MagicMock()

        coords = [(45.0 + i * 0.001, -122.0) for i in range(3)]  # fewer than BATCH_SIZE

        with patch("client.asyncio.sleep") as mock_sleep:
            await client.get_elevations(coords, batch_size=50)

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_correct_count(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=42.0)
        client._session = MagicMock()

        coords = [(45.0 + i * 0.001, -122.0) for i in range(5)]
        results = await client.get_elevations(coords)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_all_results_have_correct_lat_lng(self, tmp_path):
        db = tmp_path / "elev.db"
        client = ElevationClient(db)
        client._fetch_one = AsyncMock(return_value=99.0)
        client._session = MagicMock()

        coords = [(45.0, -122.0), (46.0, -123.0)]
        results = await client.get_elevations(coords)

        assert results[0].lat == 45.0
        assert results[0].lng == -122.0
        assert results[1].lat == 46.0
        assert results[1].lng == -123.0
