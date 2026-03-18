"""Tests for backfill-elevation main.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import TripPoint, replay_stream, publish_point


# ---------------------------------------------------------------------------
# TestTripPoint
# ---------------------------------------------------------------------------


class TestTripPoint:
    def test_from_dict_all_fields(self):
        data = {
            "id": "abc123",
            "lat": 49.2827,
            "lng": -123.1207,
            "timestamp": "2025-07-01T12:00:00",
            "image": "img_abc.jpg",
            "source": "gopro",
            "tags": ["wildlife"],
            "elevation": 55.5,
            "deleted": False,
        }
        point = TripPoint.from_dict(data)
        assert point.id == "abc123"
        assert point.lat == 49.2827
        assert point.lng == -123.1207
        assert point.timestamp == "2025-07-01T12:00:00"
        assert point.image == "img_abc.jpg"
        assert point.source == "gopro"
        assert point.tags == ["wildlife"]
        assert point.elevation == 55.5
        assert point.deleted is False

    def test_from_dict_defaults(self):
        point = TripPoint.from_dict({})
        assert point.id == ""
        assert point.lat == 0.0
        assert point.lng == 0.0
        assert point.timestamp == ""
        assert point.image is None
        assert point.source == "unknown"
        assert point.tags == []
        assert point.elevation is None
        assert point.deleted is False

    def test_from_dict_tombstone(self):
        data = {"id": "abc123", "deleted": True}
        point = TripPoint.from_dict(data)
        assert point.deleted is True
        assert point.id == "abc123"

    def test_to_dict_with_elevation(self):
        point = TripPoint(
            id="abc123",
            lat=49.0,
            lng=-123.0,
            timestamp="2025-07-01T12:00:00",
            image="img.jpg",
            source="gopro",
            tags=["wildlife"],
            elevation=42.0,
        )
        d = point.to_dict()
        assert d["id"] == "abc123"
        assert d["lat"] == 49.0
        assert d["lng"] == -123.0
        assert d["timestamp"] == "2025-07-01T12:00:00"
        assert d["image"] == "img.jpg"
        assert d["source"] == "gopro"
        assert d["tags"] == ["wildlife"]
        assert d["elevation"] == 42.0

    def test_to_dict_without_elevation_omits_field(self):
        point = TripPoint(
            id="abc123",
            lat=49.0,
            lng=-123.0,
            timestamp="2025-07-01T12:00:00",
            image=None,
            source="gopro",
            tags=[],
            elevation=None,
        )
        d = point.to_dict()
        assert "elevation" not in d

    def test_to_dict_does_not_include_deleted(self):
        point = TripPoint(
            id="abc123",
            lat=49.0,
            lng=-123.0,
            timestamp="2025-07-01T12:00:00",
            image=None,
            source="gopro",
            tags=[],
        )
        d = point.to_dict()
        assert "deleted" not in d

    def test_to_dict_roundtrip_with_from_dict(self):
        data = {
            "id": "abc123",
            "lat": 49.0,
            "lng": -123.0,
            "timestamp": "2025-07-01T12:00:00",
            "image": "img.jpg",
            "source": "gopro",
            "tags": ["gap"],
            "elevation": 77.0,
        }
        point = TripPoint.from_dict(data)
        result = point.to_dict()
        assert result == data


# ---------------------------------------------------------------------------
# TestReplayStream
# ---------------------------------------------------------------------------


def _make_nats_timeout_error():
    """Build a mock nats TimeoutError class."""
    import nats.errors

    return nats.errors.TimeoutError


def _make_stream_not_found_error():
    """Build a mock nats StreamNotFoundError class."""
    import nats.js.errors

    return nats.js.errors.NotFoundError


def _make_msg(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.data = json.dumps(data).encode()
    return msg


class TestReplayStream:
    def _make_consumer(self, batches):
        """Build a mock consumer that returns message batches then raises TimeoutError."""
        import nats.errors

        consumer = AsyncMock()
        fetch_side_effects = list(batches) + [nats.errors.TimeoutError()]
        consumer.fetch = AsyncMock(side_effect=fetch_side_effects)
        consumer.unsubscribe = AsyncMock()
        return consumer

    @pytest.mark.asyncio
    async def test_replays_single_point(self):
        msg = _make_msg(
            {
                "id": "abc",
                "lat": 49.0,
                "lng": -123.0,
                "timestamp": "2025-07-01T12:00:00",
                "source": "gopro",
                "tags": [],
            }
        )
        consumer = self._make_consumer([[msg]])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        points = await replay_stream(js)
        assert len(points) == 1
        assert points[0].id == "abc"

    @pytest.mark.asyncio
    async def test_tombstone_removes_point(self):
        msg1 = _make_msg(
            {
                "id": "abc",
                "lat": 49.0,
                "lng": -123.0,
                "timestamp": "t",
                "source": "gopro",
                "tags": [],
            }
        )
        msg2 = _make_msg({"id": "abc", "deleted": True})
        consumer = self._make_consumer([[msg1, msg2]])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        points = await replay_stream(js)
        assert points == []

    @pytest.mark.asyncio
    async def test_tombstone_for_unknown_id_is_ignored(self):
        msg = _make_msg({"id": "unknown_id", "deleted": True})
        consumer = self._make_consumer([[msg]])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        # Should not raise
        points = await replay_stream(js)
        assert points == []

    @pytest.mark.asyncio
    async def test_stream_not_found_returns_empty(self):
        import nats.js.errors

        js = AsyncMock()
        js.pull_subscribe = AsyncMock(side_effect=nats.js.errors.NotFoundError)

        points = await replay_stream(js)
        assert points == []

    @pytest.mark.asyncio
    async def test_malformed_message_is_skipped(self):
        bad_msg = MagicMock()
        bad_msg.data = b"not valid json{{{"
        consumer = self._make_consumer([[bad_msg]])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        # Should not raise; just skip bad message
        points = await replay_stream(js)
        assert points == []

    @pytest.mark.asyncio
    async def test_multiple_batches_accumulated(self):
        msgs_1 = [
            _make_msg(
                {
                    "id": "a",
                    "lat": 49.0,
                    "lng": -123.0,
                    "timestamp": "t1",
                    "source": "gopro",
                    "tags": [],
                }
            )
        ]
        msgs_2 = [
            _make_msg(
                {
                    "id": "b",
                    "lat": 50.0,
                    "lng": -124.0,
                    "timestamp": "t2",
                    "source": "gopro",
                    "tags": [],
                }
            )
        ]
        consumer = self._make_consumer([msgs_1, msgs_2])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        points = await replay_stream(js)
        assert len(points) == 2
        ids = {p.id for p in points}
        assert ids == {"a", "b"}

    @pytest.mark.asyncio
    async def test_duplicate_id_latest_wins(self):
        """Later messages for the same ID should overwrite earlier ones."""
        msg1 = _make_msg(
            {
                "id": "abc",
                "lat": 49.0,
                "lng": -123.0,
                "timestamp": "t1",
                "source": "gopro",
                "tags": [],
            }
        )
        msg2 = _make_msg(
            {
                "id": "abc",
                "lat": 50.0,
                "lng": -124.0,
                "timestamp": "t2",
                "source": "gopro",
                "tags": [],
            }
        )
        consumer = self._make_consumer([[msg1, msg2]])
        js = AsyncMock()
        js.pull_subscribe = AsyncMock(return_value=consumer)

        points = await replay_stream(js)
        assert len(points) == 1
        assert points[0].lat == 50.0


# ---------------------------------------------------------------------------
# TestPublishPoint
# ---------------------------------------------------------------------------


class TestPublishPoint:
    @pytest.mark.asyncio
    async def test_publishes_to_trips_point_subject(self):
        js = AsyncMock()
        point = TripPoint(
            id="abc123",
            lat=49.0,
            lng=-123.0,
            timestamp="2025-07-01T12:00:00",
            image="img.jpg",
            source="gopro",
            tags=[],
            elevation=42.0,
        )
        await publish_point(js, point)

        js.publish.assert_called_once()
        subject, payload = js.publish.call_args[0]
        assert subject == "trips.point"

    @pytest.mark.asyncio
    async def test_publishes_valid_json(self):
        js = AsyncMock()
        point = TripPoint(
            id="abc123",
            lat=49.0,
            lng=-123.0,
            timestamp="2025-07-01T12:00:00",
            image=None,
            source="gopro",
            tags=["wildlife"],
            elevation=None,
        )
        await publish_point(js, point)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["id"] == "abc123"
        assert msg["lat"] == 49.0
        assert msg["source"] == "gopro"

    @pytest.mark.asyncio
    async def test_elevation_included_when_present(self):
        js = AsyncMock()
        point = TripPoint(
            id="abc",
            lat=49.0,
            lng=-123.0,
            timestamp="t",
            image=None,
            source="gopro",
            tags=[],
            elevation=55.5,
        )
        await publish_point(js, point)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["elevation"] == 55.5

    @pytest.mark.asyncio
    async def test_elevation_omitted_when_none(self):
        js = AsyncMock()
        point = TripPoint(
            id="abc",
            lat=49.0,
            lng=-123.0,
            timestamp="t",
            image=None,
            source="gopro",
            tags=[],
            elevation=None,
        )
        await publish_point(js, point)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert "elevation" not in msg
