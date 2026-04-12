"""Unit tests for backfill-elevation/main.py — cache_stats command and edge cases.

Supplements backfill_elevation_test.py by covering:
- cache_stats: reads ElevationCache and prints statistics
- run_backfill: early-exit paths (no points, all have elevation)
- TripPoint: edge-case field handling not in the existing test file
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

from main import TripPoint, cache_stats, publish_point, replay_stream, run_backfill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_point(pid: str, elevation: float | None = None) -> TripPoint:
    return TripPoint(
        id=pid,
        lat=45.0,
        lng=-122.0,
        timestamp="2025-01-01T10:00:00",
        image=None,
        source="gopro",
        tags=["car"],
        elevation=elevation,
    )


# ---------------------------------------------------------------------------
# TripPoint edge cases
# ---------------------------------------------------------------------------


class TestTripPointEdgeCases:
    """Edge-case handling not covered by existing backfill_elevation_test.py."""

    def test_zero_lat_lng_preserved(self):
        """Zero coordinates are valid values, not None."""
        point = TripPoint.from_dict({"id": "x", "lat": 0.0, "lng": 0.0})
        assert point.lat == 0.0
        assert point.lng == 0.0

    def test_very_precise_coordinates_preserved(self):
        data = {"id": "x", "lat": 60.123456789, "lng": -139.987654321}
        point = TripPoint.from_dict(data)
        assert point.lat == pytest.approx(60.123456789)
        assert point.lng == pytest.approx(-139.987654321)

    def test_deleted_field_defaults_false_when_absent(self):
        point = TripPoint.from_dict({"id": "x"})
        assert point.deleted is False

    def test_to_dict_excludes_elevation_when_none(self):
        point = _make_point("p1", elevation=None)
        d = point.to_dict()
        assert "elevation" not in d

    def test_to_dict_includes_zero_elevation(self):
        """Sea level (0.0 m) must appear in the serialised dict."""
        point = _make_point("p1", elevation=0.0)
        d = point.to_dict()
        assert "elevation" in d
        assert d["elevation"] == 0.0

    def test_to_dict_does_not_include_deleted(self):
        point = TripPoint.from_dict({"id": "p1", "deleted": True})
        d = point.to_dict()
        assert "deleted" not in d

    def test_source_preserved_in_to_dict(self):
        point = TripPoint.from_dict({"id": "p1", "source": "phone"})
        assert point.to_dict()["source"] == "phone"


# ---------------------------------------------------------------------------
# run_backfill — no points early exit
# ---------------------------------------------------------------------------


class TestRunBackfillNoPoints:
    """run_backfill handles the case where the stream has no points."""

    @pytest.mark.asyncio
    async def test_no_points_exits_without_publishing(self):
        mock_nc = AsyncMock()
        mock_js = AsyncMock()

        with (
            patch("main.nats.connect", return_value=mock_nc),
            patch("main.replay_stream", return_value=[]) as mock_replay,
        ):
            mock_nc.jetstream = MagicMock(return_value=mock_js)
            await run_backfill(dry_run=False, force=False)

        mock_js.publish.assert_not_called()


# ---------------------------------------------------------------------------
# run_backfill — all points have elevation (no work needed)
# ---------------------------------------------------------------------------


class TestRunBackfillAllHaveElevation:
    """run_backfill skips re-fetching when all points already have elevation."""

    @pytest.mark.asyncio
    async def test_all_points_have_elevation_no_api_call(self):
        """When all points have elevation and force=False, no HTTP requests made."""
        points = [
            _make_point("p1", elevation=100.0),
            _make_point("p2", elevation=200.0),
        ]
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with (
            patch("main.nats.connect", return_value=mock_nc),
            patch("main.replay_stream", return_value=points),
            patch("main.ElevationClient") as mock_elev_cls,
        ):
            await run_backfill(dry_run=False, force=False)

        # ElevationClient should never have been entered as context manager
        mock_elev_cls.return_value.__aenter__.assert_not_called()


# ---------------------------------------------------------------------------
# run_backfill — dry run does not publish
# ---------------------------------------------------------------------------


class TestRunBackfillDryRun:
    """Dry-run mode shows a preview but does not publish."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_publish(self):
        """With dry_run=True, no messages are sent to NATS."""
        points = [_make_point("p1", elevation=None)]
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with (
            patch("main.nats.connect", return_value=mock_nc),
            patch("main.replay_stream", return_value=points),
        ):
            await run_backfill(dry_run=True, force=False)

        mock_js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_force_does_not_publish(self):
        """force=True with dry_run=True still must not publish."""
        points = [_make_point("p1", elevation=100.0)]
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with (
            patch("main.nats.connect", return_value=mock_nc),
            patch("main.replay_stream", return_value=points),
        ):
            await run_backfill(dry_run=True, force=True)

        mock_js.publish.assert_not_called()


# ---------------------------------------------------------------------------
# publish_point
# ---------------------------------------------------------------------------


class TestPublishPointAdditional:
    """Additional publish_point edge cases."""

    @pytest.mark.asyncio
    async def test_source_field_preserved_in_payload(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p1",
            lat=45.0,
            lng=-122.0,
            timestamp="2025-01-01T00:00:00",
            image=None,
            source="phone",
            tags=["wildlife"],
        )
        await publish_point(mock_js, point)
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["source"] == "phone"
        assert payload["tags"] == ["wildlife"]

    @pytest.mark.asyncio
    async def test_image_field_preserved_when_set(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p1",
            lat=45.0,
            lng=-122.0,
            timestamp="2025-01-01T00:00:00",
            image="img_abc.jpg",
            source="gopro",
            tags=[],
        )
        await publish_point(mock_js, point)
        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert payload["image"] == "img_abc.jpg"

    @pytest.mark.asyncio
    async def test_publish_propagates_nats_errors(self):
        """NATS publish errors bubble up to the caller."""
        mock_js = AsyncMock()
        mock_js.publish.side_effect = Exception("NATS error")
        point = TripPoint(
            id="p1",
            lat=45.0,
            lng=-122.0,
            timestamp="2025-01-01T00:00:00",
            image=None,
            source="gopro",
            tags=[],
        )
        with pytest.raises(Exception, match="NATS error"):
            await publish_point(mock_js, point)


# ---------------------------------------------------------------------------
# cache_stats — ElevationCache statistics display
# ---------------------------------------------------------------------------


class TestCacheStatsCommand:
    """Tests for the cache_stats command.

    cache_stats() creates an ElevationCache instance, calls stats(), and
    prints the total / with_data / no_data counts.  All tests mock
    ElevationCache so no SQLite file is touched.
    """

    def test_creates_elevation_cache_instance(self):
        """cache_stats() must instantiate ElevationCache exactly once."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"total": 0, "with_data": 0, "no_data": 0}

        with patch("main.ElevationCache", return_value=mock_cache) as mock_cls:
            cache_stats()

        mock_cls.assert_called_once()

    def test_calls_stats_on_cache(self):
        """cache_stats() must call cache.stats() to obtain counts."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"total": 0, "with_data": 0, "no_data": 0}

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        mock_cache.stats.assert_called_once()

    def test_empty_cache_does_not_raise(self):
        """cache_stats() handles an empty cache (all counts zero) without error."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"total": 0, "with_data": 0, "no_data": 0}

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()  # must not raise

    def test_populated_cache_does_not_raise(self):
        """cache_stats() handles a fully-populated cache without error."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {
            "total": 1000,
            "with_data": 950,
            "no_data": 50,
        }

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()  # must not raise

    def test_all_entries_have_elevation(self):
        """cache_stats() handles the case where no_data == 0 (all points have elevation)."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"total": 200, "with_data": 200, "no_data": 0}

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        mock_cache.stats.assert_called_once()

    def test_all_entries_missing_elevation(self):
        """cache_stats() handles the case where with_data == 0 (no points have elevation)."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"total": 75, "with_data": 0, "no_data": 75}

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        mock_cache.stats.assert_called_once()

    def test_stats_dict_total_key_accessed(self):
        """cache_stats() accesses stats['total'] without raising KeyError."""
        accessed_keys: list[str] = []
        real_stats = {"total": 42, "with_data": 30, "no_data": 12}

        class _TrackingDict(dict):
            def __getitem__(self, key):
                accessed_keys.append(key)
                return super().__getitem__(key)

        mock_cache = MagicMock()
        mock_cache.stats.return_value = _TrackingDict(real_stats)

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        assert "total" in accessed_keys

    def test_stats_dict_with_data_key_accessed(self):
        """cache_stats() accesses stats['with_data'] without raising KeyError."""
        accessed_keys: list[str] = []
        real_stats = {"total": 42, "with_data": 30, "no_data": 12}

        class _TrackingDict(dict):
            def __getitem__(self, key):
                accessed_keys.append(key)
                return super().__getitem__(key)

        mock_cache = MagicMock()
        mock_cache.stats.return_value = _TrackingDict(real_stats)

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        assert "with_data" in accessed_keys

    def test_stats_dict_no_data_key_accessed(self):
        """cache_stats() accesses stats['no_data'] without raising KeyError."""
        accessed_keys: list[str] = []
        real_stats = {"total": 42, "with_data": 30, "no_data": 12}

        class _TrackingDict(dict):
            def __getitem__(self, key):
                accessed_keys.append(key)
                return super().__getitem__(key)

        mock_cache = MagicMock()
        mock_cache.stats.return_value = _TrackingDict(real_stats)

        with patch("main.ElevationCache", return_value=mock_cache):
            cache_stats()

        assert "no_data" in accessed_keys
