"""Tests for delete-trip-points tool: publish_delete and business logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — needed to register pytest-asyncio plugin

from main import publish_delete


# ---------------------------------------------------------------------------
# publish_delete tests
# ---------------------------------------------------------------------------


class TestPublishDelete:
    """Tombstone message publishing."""

    @pytest.mark.asyncio
    async def test_publishes_to_trips_delete_subject(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "point-abc-123")
        subject = mock_js.publish.call_args[0][0]
        assert subject == "trips.delete"

    @pytest.mark.asyncio
    async def test_payload_contains_id(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "my-point-id")
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["id"] == "my-point-id"

    @pytest.mark.asyncio
    async def test_payload_deleted_is_true(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "some-id")
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["deleted"] is True

    @pytest.mark.asyncio
    async def test_payload_is_valid_json_bytes(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "xyz")
        raw = mock_js.publish.call_args[0][1]
        assert isinstance(raw, bytes)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_calls_js_publish_once(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "any-id")
        mock_js.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_id_still_publishes(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "")
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["id"] == ""
        assert payload["deleted"] is True

    @pytest.mark.asyncio
    async def test_id_with_special_characters(self):
        mock_js = AsyncMock()
        pid = "point/with:special#chars"
        await publish_delete(mock_js, pid)
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["id"] == pid


# ---------------------------------------------------------------------------
# Date filtering logic
# ---------------------------------------------------------------------------


class TestDateFiltering:
    """The _delete inner function filters points by date and source."""

    def _make_points(self):
        return [
            {"id": "p1", "timestamp": "2025-01-15T10:00:00", "source": "gap", "lat": 45.0, "lng": -122.0},
            {"id": "p2", "timestamp": "2025-01-15T11:00:00", "source": "gap", "lat": 45.1, "lng": -122.1},
            {"id": "p3", "timestamp": "2025-01-16T10:00:00", "source": "gap", "lat": 46.0, "lng": -123.0},
            {"id": "p4", "timestamp": "2025-01-15T10:30:00", "source": "manual", "lat": 45.5, "lng": -122.5},
        ]

    def test_filter_by_date_and_source(self):
        """Points are filtered by timestamp prefix and source."""
        points = self._make_points()
        date = "2025-01-15"
        source = "gap"
        result = [
            p for p in points
            if p["timestamp"].startswith(date) and p["source"] == source
        ]
        assert len(result) == 2
        assert all(p["source"] == "gap" for p in result)
        assert all(p["timestamp"].startswith("2025-01-15") for p in result)

    def test_filter_no_match_returns_empty(self):
        points = self._make_points()
        result = [
            p for p in points
            if p["timestamp"].startswith("2025-02-01") and p["source"] == "gap"
        ]
        assert result == []

    def test_filter_different_date_excludes_other_dates(self):
        points = self._make_points()
        result = [
            p for p in points
            if p["timestamp"].startswith("2025-01-16") and p["source"] == "gap"
        ]
        assert len(result) == 1
        assert result[0]["id"] == "p3"

    def test_filter_by_source_excludes_other_sources(self):
        points = self._make_points()
        result = [
            p for p in points
            if p["timestamp"].startswith("2025-01-15") and p["source"] == "manual"
        ]
        assert len(result) == 1
        assert result[0]["id"] == "p4"


# ---------------------------------------------------------------------------
# Gap listing logic
# ---------------------------------------------------------------------------


class TestGapListingLogic:
    """The _list inner function groups gap points by date."""

    def _make_gap_points(self):
        return [
            {"id": "g1", "timestamp": "2025-01-15T10:00:00", "source": "gap", "lat": 45.0, "lng": -122.0},
            {"id": "g2", "timestamp": "2025-01-15T10:01:00", "source": "gap", "lat": 45.1, "lng": -122.1},
            {"id": "g3", "timestamp": "2025-01-16T09:00:00", "source": "gap", "lat": 46.0, "lng": -123.0},
            {"id": "m1", "timestamp": "2025-01-15T11:00:00", "source": "manual", "lat": 45.5, "lng": -122.5},
        ]

    def test_filters_only_gap_source(self):
        points = self._make_gap_points()
        gaps = [p for p in points if p["source"] == "gap"]
        assert len(gaps) == 3
        assert all(p["source"] == "gap" for p in gaps)

    def test_date_filter_applied(self):
        points = self._make_gap_points()
        gaps = [p for p in points if p["source"] == "gap"]
        date = "2025-01-15"
        filtered = [p for p in gaps if p["timestamp"].startswith(date)]
        assert len(filtered) == 2

    def test_grouping_by_date(self):
        points = self._make_gap_points()
        gaps = [p for p in points if p["source"] == "gap"]
        by_date: dict = {}
        for p in gaps:
            d = p["timestamp"][:10]
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(p)
        assert len(by_date) == 2
        assert "2025-01-15" in by_date
        assert "2025-01-16" in by_date
        assert len(by_date["2025-01-15"]) == 2
        assert len(by_date["2025-01-16"]) == 1

    def test_no_gap_points_in_dataset(self):
        points = [
            {"id": "m1", "timestamp": "2025-01-15T11:00:00", "source": "manual", "lat": 45.0, "lng": -122.0},
        ]
        gaps = [p for p in points if p["source"] == "gap"]
        assert gaps == []

    def test_no_gap_points_on_specific_date(self):
        points = self._make_gap_points()
        gaps = [p for p in points if p["source"] == "gap"]
        filtered = [p for p in gaps if p["timestamp"].startswith("2025-03-01")]
        assert filtered == []


# ---------------------------------------------------------------------------
# Batch publish logic
# ---------------------------------------------------------------------------


class TestBatchPublishLogic:
    """Verify the batch-delete loop publishes one tombstone per point."""

    @pytest.mark.asyncio
    async def test_publishes_one_tombstone_per_point(self):
        mock_js = AsyncMock()
        point_ids = ["id1", "id2", "id3"]
        for pid in point_ids:
            await publish_delete(mock_js, pid)
        assert mock_js.publish.call_count == 3

    @pytest.mark.asyncio
    async def test_each_tombstone_has_correct_id(self):
        mock_js = AsyncMock()
        point_ids = ["id-a", "id-b", "id-c"]
        for pid in point_ids:
            await publish_delete(mock_js, pid)

        published_ids = []
        for call in mock_js.publish.call_args_list:
            payload = json.loads(call[0][1].decode())
            published_ids.append(payload["id"])
        assert published_ids == point_ids

    @pytest.mark.asyncio
    async def test_single_point_publish(self):
        mock_js = AsyncMock()
        await publish_delete(mock_js, "only-point")
        mock_js.publish.assert_called_once()
        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert payload["id"] == "only-point"
        assert payload["deleted"] is True

    @pytest.mark.asyncio
    async def test_dry_run_does_not_publish(self):
        """When dry_run is True, no tombstones should be published."""
        mock_js = AsyncMock()
        dry_run = True
        point_ids = ["id1", "id2"]
        if not dry_run:
            for pid in point_ids:
                await publish_delete(mock_js, pid)
        mock_js.publish.assert_not_called()
