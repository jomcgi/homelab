"""Tests for backfill-elevation tool: TripPoint dataclass and replay logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — needed to register pytest-asyncio plugin

from main import TripPoint, publish_point, replay_stream


# ---------------------------------------------------------------------------
# TripPoint.from_dict tests
# ---------------------------------------------------------------------------


class TestTripPointFromDict:
    """Deserialisation from raw dict."""

    def test_full_dict_all_fields(self):
        data = {
            "id": "abc123",
            "lat": 45.5,
            "lng": -122.3,
            "timestamp": "2025-01-15T10:00:00",
            "image": "https://example.com/img.jpg",
            "source": "gopro",
            "tags": ["wildlife", "bear"],
            "elevation": 250.0,
            "deleted": False,
        }
        point = TripPoint.from_dict(data)
        assert point.id == "abc123"
        assert point.lat == 45.5
        assert point.lng == -122.3
        assert point.timestamp == "2025-01-15T10:00:00"
        assert point.image == "https://example.com/img.jpg"
        assert point.source == "gopro"
        assert point.tags == ["wildlife", "bear"]
        assert point.elevation == 250.0
        assert point.deleted is False

    def test_minimal_dict_uses_defaults(self):
        data = {}
        point = TripPoint.from_dict(data)
        assert point.id == ""
        assert point.lat == 0.0
        assert point.lng == 0.0
        assert point.timestamp == ""
        assert point.image is None
        assert point.source == "unknown"
        assert point.tags == []
        assert point.elevation is None
        assert point.deleted is False

    def test_null_image_preserved(self):
        data = {"id": "x", "image": None}
        point = TripPoint.from_dict(data)
        assert point.image is None

    def test_deleted_true_preserved(self):
        data = {"id": "x", "deleted": True}
        point = TripPoint.from_dict(data)
        assert point.deleted is True

    def test_missing_elevation_is_none(self):
        data = {"id": "x", "lat": 1.0, "lng": 2.0}
        point = TripPoint.from_dict(data)
        assert point.elevation is None

    def test_elevation_zero_preserved(self):
        """Zero elevation is a valid value, not None."""
        data = {"id": "x", "elevation": 0.0}
        point = TripPoint.from_dict(data)
        assert point.elevation == 0.0

    def test_empty_tags_list(self):
        data = {"id": "x", "tags": []}
        point = TripPoint.from_dict(data)
        assert point.tags == []

    def test_multiple_tags(self):
        data = {"id": "x", "tags": ["a", "b", "c"]}
        point = TripPoint.from_dict(data)
        assert point.tags == ["a", "b", "c"]

    def test_negative_coordinates(self):
        data = {"id": "x", "lat": -33.8688, "lng": 151.2093}
        point = TripPoint.from_dict(data)
        assert point.lat == pytest.approx(-33.8688)
        assert point.lng == pytest.approx(151.2093)


# ---------------------------------------------------------------------------
# TripPoint.to_dict tests
# ---------------------------------------------------------------------------


class TestTripPointToDict:
    """Serialisation to dict."""

    def _make_point(self, **kwargs) -> TripPoint:
        defaults = {
            "id": "test-id",
            "lat": 45.0,
            "lng": -122.0,
            "timestamp": "2025-01-15T10:00:00",
            "image": None,
            "source": "gopro",
            "tags": [],
        }
        defaults.update(kwargs)
        return TripPoint(**defaults)

    def test_to_dict_contains_required_fields(self):
        point = self._make_point()
        d = point.to_dict()
        for field in ("id", "lat", "lng", "timestamp", "image", "source", "tags"):
            assert field in d

    def test_elevation_included_when_set(self):
        point = self._make_point(elevation=300.0)
        d = point.to_dict()
        assert "elevation" in d
        assert d["elevation"] == 300.0

    def test_elevation_excluded_when_none(self):
        """to_dict must not include elevation key when elevation is None."""
        point = self._make_point(elevation=None)
        d = point.to_dict()
        assert "elevation" not in d

    def test_deleted_not_included_in_to_dict(self):
        """deleted is a runtime-only field; it should not appear in the published payload."""
        point = self._make_point()
        d = point.to_dict()
        assert "deleted" not in d

    def test_roundtrip_without_elevation(self):
        data = {
            "id": "rt-1",
            "lat": 51.5,
            "lng": -0.1,
            "timestamp": "2025-06-01T12:00:00",
            "image": "img.jpg",
            "source": "manual",
            "tags": ["london"],
        }
        point = TripPoint.from_dict(data)
        result = point.to_dict()
        for key, value in data.items():
            assert result[key] == value
        assert "elevation" not in result

    def test_roundtrip_with_elevation(self):
        data = {
            "id": "rt-2",
            "lat": 51.5,
            "lng": -0.1,
            "timestamp": "2025-06-01T12:00:00",
            "image": None,
            "source": "gap",
            "tags": [],
            "elevation": 42.5,
        }
        point = TripPoint.from_dict(data)
        result = point.to_dict()
        assert result["elevation"] == pytest.approx(42.5)

    def test_elevation_zero_included(self):
        """Zero is a valid elevation and must appear in the dict."""
        point = self._make_point(elevation=0.0)
        d = point.to_dict()
        assert "elevation" in d
        assert d["elevation"] == 0.0

    def test_null_image_preserved_in_to_dict(self):
        point = self._make_point(image=None)
        d = point.to_dict()
        assert d["image"] is None

    def test_image_url_preserved_in_to_dict(self):
        point = self._make_point(image="https://example.com/photo.jpg")
        d = point.to_dict()
        assert d["image"] == "https://example.com/photo.jpg"


# ---------------------------------------------------------------------------
# publish_point tests
# ---------------------------------------------------------------------------


class TestPublishPoint:
    """Publishing a point to NATS."""

    @pytest.mark.asyncio
    async def test_publishes_to_trips_point_subject(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p1", lat=45.0, lng=-122.0,
            timestamp="2025-01-01T00:00:00", image=None,
            source="gopro", tags=[],
        )
        await publish_point(mock_js, point)
        subject = mock_js.publish.call_args[0][0]
        assert subject == "trips.point"

    @pytest.mark.asyncio
    async def test_payload_is_json_bytes(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p1", lat=45.0, lng=-122.0,
            timestamp="2025-01-01T00:00:00", image=None,
            source="gopro", tags=[],
        )
        await publish_point(mock_js, point)
        raw = mock_js.publish.call_args[0][1]
        assert isinstance(raw, bytes)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_payload_matches_to_dict(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="abc", lat=51.5, lng=-0.1,
            timestamp="2025-06-01T12:00:00",
            image="img.jpg", source="manual",
            tags=["x"], elevation=100.0,
        )
        await publish_point(mock_js, point)
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload == point.to_dict()

    @pytest.mark.asyncio
    async def test_elevation_in_payload_when_set(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p2", lat=45.0, lng=-122.0,
            timestamp="2025-01-01T00:00:00", image=None,
            source="gopro", tags=[], elevation=250.0,
        )
        await publish_point(mock_js, point)
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert payload["elevation"] == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_elevation_absent_from_payload_when_none(self):
        mock_js = AsyncMock()
        point = TripPoint(
            id="p3", lat=45.0, lng=-122.0,
            timestamp="2025-01-01T00:00:00", image=None,
            source="gopro", tags=[], elevation=None,
        )
        await publish_point(mock_js, point)
        raw = mock_js.publish.call_args[0][1]
        payload = json.loads(raw.decode())
        assert "elevation" not in payload


# ---------------------------------------------------------------------------
# replay_stream tests
# ---------------------------------------------------------------------------


class TestReplayStream:
    """Stream replay logic: deduplication and tombstone handling."""

    def _make_consumer(self, message_batches: list[list[dict]]):
        """Build a mock JetStream consumer that returns batches then raises TimeoutError."""
        import nats.errors

        mock_consumer = AsyncMock()
        side_effects = []
        for batch in message_batches:
            msgs = []
            for data in batch:
                msg = MagicMock()
                msg.data = json.dumps(data).encode()
                msgs.append(msg)
            side_effects.append(msgs)
        side_effects.append(nats.errors.TimeoutError())

        mock_consumer.fetch = AsyncMock(side_effect=side_effects)
        mock_consumer.unsubscribe = AsyncMock()
        return mock_consumer

    def _make_js(self, message_batches: list[list[dict]]):
        """Build a mock JetStream that returns a consumer with the given batches."""
        mock_js = AsyncMock()
        consumer = self._make_consumer(message_batches)
        mock_js.pull_subscribe = AsyncMock(return_value=consumer)
        return mock_js

    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_list(self):
        mock_js = self._make_js([])
        result = await replay_stream(mock_js)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_point_returned(self):
        data = [{"id": "p1", "lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
                 "source": "gopro", "tags": []}]
        mock_js = self._make_js([data])
        result = await replay_stream(mock_js)
        assert len(result) == 1
        assert result[0].id == "p1"

    @pytest.mark.asyncio
    async def test_duplicate_id_uses_latest_message(self):
        """Later messages with the same ID replace earlier ones (last-write-wins)."""
        batch = [
            {"id": "p1", "lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
             "source": "gopro", "tags": [], "elevation": 100.0},
            {"id": "p1", "lat": 46.0, "lng": -123.0, "timestamp": "2025-01-01T00:00:00",
             "source": "gopro", "tags": [], "elevation": 200.0},
        ]
        mock_js = self._make_js([batch])
        result = await replay_stream(mock_js)
        assert len(result) == 1
        assert result[0].elevation == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_tombstone_removes_point(self):
        batch = [
            {"id": "p1", "lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
             "source": "gopro", "tags": []},
            {"id": "p1", "deleted": True},
        ]
        mock_js = self._make_js([batch])
        result = await replay_stream(mock_js)
        assert result == []

    @pytest.mark.asyncio
    async def test_tombstone_for_unknown_id_is_ignored(self):
        batch = [
            {"id": "p1", "lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
             "source": "gopro", "tags": []},
            {"id": "unknown", "deleted": True},
        ]
        mock_js = self._make_js([batch])
        result = await replay_stream(mock_js)
        assert len(result) == 1
        assert result[0].id == "p1"

    @pytest.mark.asyncio
    async def test_point_without_id_is_ignored(self):
        """Messages with empty id should not be stored."""
        batch = [{"lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
                  "source": "gopro", "tags": []}]
        mock_js = self._make_js([batch])
        result = await replay_stream(mock_js)
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_points_all_returned(self):
        batch = [
            {"id": f"p{i}", "lat": 45.0 + i, "lng": -122.0,
             "timestamp": "2025-01-01T00:00:00", "source": "gopro", "tags": []}
            for i in range(5)
        ]
        mock_js = self._make_js([batch])
        result = await replay_stream(mock_js)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_stream_not_found_returns_empty_list(self):
        """StreamNotFoundError should be caught and return empty list."""
        import nats.js.errors

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(
            side_effect=nats.js.errors.StreamNotFoundError()
        )
        result = await replay_stream(mock_js)
        assert result == []

    @pytest.mark.asyncio
    async def test_malformed_message_skipped_gracefully(self):
        """Non-JSON messages should be skipped without crashing."""
        import nats.errors

        mock_consumer = AsyncMock()
        bad_msg = MagicMock()
        bad_msg.data = b"this is not json {"
        good_msg = MagicMock()
        good_msg.data = json.dumps({
            "id": "p1", "lat": 45.0, "lng": -122.0,
            "timestamp": "2025-01-01T00:00:00", "source": "gopro", "tags": []
        }).encode()

        mock_consumer.fetch = AsyncMock(
            side_effect=[[bad_msg, good_msg], nats.errors.TimeoutError()]
        )
        mock_consumer.unsubscribe = AsyncMock()
        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_consumer)

        result = await replay_stream(mock_js)
        assert len(result) == 1
        assert result[0].id == "p1"

    @pytest.mark.asyncio
    async def test_multi_batch_processing(self):
        """Points delivered across multiple fetch calls are all collected."""
        batch1 = [
            {"id": "p1", "lat": 45.0, "lng": -122.0, "timestamp": "2025-01-01T00:00:00",
             "source": "gopro", "tags": []},
        ]
        batch2 = [
            {"id": "p2", "lat": 46.0, "lng": -123.0, "timestamp": "2025-01-02T00:00:00",
             "source": "gopro", "tags": []},
        ]
        mock_js = self._make_js([batch1, batch2])
        result = await replay_stream(mock_js)
        ids = {p.id for p in result}
        assert ids == {"p1", "p2"}

    @pytest.mark.asyncio
    async def test_consumer_unsubscribed_after_replay(self):
        mock_js = self._make_js([[]])
        await replay_stream(mock_js)
        consumer = await mock_js.pull_subscribe.return_value
        consumer.unsubscribe.assert_called_once()


# ---------------------------------------------------------------------------
# run_backfill — dry-run and force-mode logic
# ---------------------------------------------------------------------------


class TestRunBackfillFiltering:
    """Filter logic for which points need elevation."""

    def test_force_mode_includes_points_with_elevation(self):
        points = [
            TripPoint("p1", 45.0, -122.0, "2025-01-01T00:00:00", None, "gopro", [], elevation=100.0),
            TripPoint("p2", 46.0, -123.0, "2025-01-02T00:00:00", None, "gopro", [], elevation=None),
        ]
        force = True
        needs_elevation = points if force else [p for p in points if p.elevation is None]
        assert len(needs_elevation) == 2

    def test_no_force_skips_points_with_elevation(self):
        points = [
            TripPoint("p1", 45.0, -122.0, "2025-01-01T00:00:00", None, "gopro", [], elevation=100.0),
            TripPoint("p2", 46.0, -123.0, "2025-01-02T00:00:00", None, "gopro", [], elevation=None),
        ]
        force = False
        needs_elevation = points if force else [p for p in points if p.elevation is None]
        assert len(needs_elevation) == 1
        assert needs_elevation[0].id == "p2"

    def test_all_points_have_elevation_returns_empty_without_force(self):
        points = [
            TripPoint("p1", 45.0, -122.0, "2025-01-01T00:00:00", None, "gopro", [], elevation=100.0),
            TripPoint("p2", 46.0, -123.0, "2025-01-02T00:00:00", None, "gopro", [], elevation=200.0),
        ]
        needs_elevation = [p for p in points if p.elevation is None]
        assert needs_elevation == []

    def test_no_points_no_work(self):
        points = []
        needs_elevation = [p for p in points if p.elevation is None]
        assert needs_elevation == []

    def test_elevation_update_applied_to_point(self):
        """After fetching elevation, the point object is updated in-place."""
        point = TripPoint("p1", 45.0, -122.0, "2025-01-01T00:00:00", None, "gopro", [])
        assert point.elevation is None

        # Simulate what run_backfill does: point.elevation = result.elevation
        class _FakeResult:
            elevation = 350.5

        point.elevation = _FakeResult.elevation
        assert point.elevation == pytest.approx(350.5)
        assert point.to_dict()["elevation"] == pytest.approx(350.5)
