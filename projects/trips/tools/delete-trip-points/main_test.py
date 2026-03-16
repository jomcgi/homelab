"""Tests for delete-trip-points main.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import publish_delete


# ---------------------------------------------------------------------------
# TestPublishDelete
# ---------------------------------------------------------------------------


class TestPublishDelete:
    @pytest.mark.asyncio
    async def test_publishes_to_trips_delete_subject(self):
        js = AsyncMock()
        await publish_delete(js, "point-id-123")

        js.publish.assert_called_once()
        subject, payload = js.publish.call_args[0]
        assert subject == "trips.delete"

    @pytest.mark.asyncio
    async def test_tombstone_payload_structure(self):
        js = AsyncMock()
        await publish_delete(js, "point-id-abc")

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["id"] == "point-id-abc"
        assert msg["deleted"] is True

    @pytest.mark.asyncio
    async def test_tombstone_contains_only_id_and_deleted(self):
        js = AsyncMock()
        await publish_delete(js, "xyz")

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert set(msg.keys()) == {"id", "deleted"}

    @pytest.mark.asyncio
    async def test_empty_id_is_published(self):
        """Even an empty ID should produce a valid tombstone message."""
        js = AsyncMock()
        await publish_delete(js, "")

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["id"] == ""
        assert msg["deleted"] is True


# ---------------------------------------------------------------------------
# TestByDateFiltering (logic extracted from the _delete inner function)
# ---------------------------------------------------------------------------


class TestByDateFiltering:
    """Tests for the date/source filtering logic used in the by_date command."""

    def _filter_points(self, points, date, source):
        """Replicate the filter from the by_date inner function."""
        return [
            p
            for p in points
            if p["timestamp"].startswith(date) and p["source"] == source
        ]

    def test_filters_by_date_and_source(self):
        points = [
            {"id": "1", "lat": 49.0, "lng": -123.0, "timestamp": "2025-07-01T10:00:00", "source": "gap"},
            {"id": "2", "lat": 50.0, "lng": -124.0, "timestamp": "2025-07-01T11:00:00", "source": "gopro"},
            {"id": "3", "lat": 51.0, "lng": -125.0, "timestamp": "2025-07-02T10:00:00", "source": "gap"},
        ]
        result = self._filter_points(points, "2025-07-01", "gap")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_returns_empty_when_no_match(self):
        points = [
            {"id": "1", "timestamp": "2025-07-01T10:00:00", "source": "gopro"},
        ]
        result = self._filter_points(points, "2025-07-02", "gap")
        assert result == []

    def test_matches_multiple_on_same_date(self):
        points = [
            {"id": "1", "timestamp": "2025-07-01T10:00:00", "source": "gap"},
            {"id": "2", "timestamp": "2025-07-01T11:00:00", "source": "gap"},
        ]
        result = self._filter_points(points, "2025-07-01", "gap")
        assert len(result) == 2

    def test_date_prefix_matches_any_time(self):
        """Timestamp prefix matching works for different time portions."""
        points = [
            {"id": "a", "timestamp": "2025-07-01T00:00:00", "source": "gap"},
            {"id": "b", "timestamp": "2025-07-01T23:59:59", "source": "gap"},
        ]
        result = self._filter_points(points, "2025-07-01", "gap")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestListGapsFiltering
# ---------------------------------------------------------------------------


class TestListGapsFiltering:
    """Tests for the gap filtering logic used in list_gaps."""

    def _filter_gaps(self, points, date=None):
        """Replicate the filter from the list_gaps inner function."""
        gaps = [p for p in points if p["source"] == "gap"]
        if date:
            gaps = [p for p in gaps if p["timestamp"].startswith(date)]
        return gaps

    def test_filters_only_gap_source(self):
        points = [
            {"id": "1", "timestamp": "2025-07-01T10:00:00", "source": "gap"},
            {"id": "2", "timestamp": "2025-07-01T10:00:00", "source": "gopro"},
        ]
        result = self._filter_gaps(points)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_no_gaps_returns_empty(self):
        points = [
            {"id": "1", "timestamp": "2025-07-01T10:00:00", "source": "gopro"},
        ]
        result = self._filter_gaps(points)
        assert result == []

    def test_date_filter_applied(self):
        points = [
            {"id": "1", "timestamp": "2025-07-01T10:00:00", "source": "gap"},
            {"id": "2", "timestamp": "2025-07-02T10:00:00", "source": "gap"},
        ]
        result = self._filter_gaps(points, date="2025-07-01")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_groups_by_date_logic(self):
        """Verify the grouping logic used in list_gaps output."""
        gaps = [
            {"id": "a", "timestamp": "2025-07-01T10:00:00", "lat": 49.0, "lng": -123.0},
            {"id": "b", "timestamp": "2025-07-01T11:00:00", "lat": 49.1, "lng": -123.1},
            {"id": "c", "timestamp": "2025-07-02T10:00:00", "lat": 50.0, "lng": -124.0},
        ]
        by_date = {}
        for p in gaps:
            d = p["timestamp"][:10]
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(p)

        assert "2025-07-01" in by_date
        assert "2025-07-02" in by_date
        assert len(by_date["2025-07-01"]) == 2
        assert len(by_date["2025-07-02"]) == 1
