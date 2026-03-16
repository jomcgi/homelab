"""Tests for Ships API service."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.websockets import WebSocket

from projects.ships.backend.main import (
    CachedPosition,
    Database,
    WebSocketManager,
    haversine_distance,
)


class TestHaversineDistance:
    """Tests for the haversine_distance pure function."""

    def test_same_point_is_zero(self):
        assert haversine_distance(48.5, -123.4, 48.5, -123.4) == 0.0

    def test_known_distance(self):
        # Vancouver (49.2827, -123.1207) to Seattle (47.6062, -122.3321)
        # Approximately 195 km great-circle distance
        dist = haversine_distance(49.2827, -123.1207, 47.6062, -122.3321)
        assert 185_000 < dist < 210_000

    def test_one_degree_latitude(self):
        # One degree of latitude is roughly 111 km
        dist = haversine_distance(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < dist < 112_000

    def test_short_distance(self):
        # Two points 100 m apart (approx 0.001 degrees latitude)
        dist = haversine_distance(48.5, -123.4, 48.5009, -123.4)
        assert 90 < dist < 110

    def test_antipodal_points(self):
        # Maximum possible distance is roughly half the Earth's circumference (~20 Mm)
        dist = haversine_distance(0.0, 0.0, 0.0, 180.0)
        assert dist > 19_000_000

    def test_symmetry(self):
        d1 = haversine_distance(48.5, -123.4, 49.0, -124.0)
        d2 = haversine_distance(49.0, -124.0, 48.5, -123.4)
        assert abs(d1 - d2) < 1e-6


class TestWebSocketManager:
    """Tests for the WebSocketManager class."""

    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_connect_accepts_and_adds(self, manager):
        mock_ws = AsyncMock(spec=WebSocket)
        await manager.connect(mock_ws)

        mock_ws.accept.assert_called_once()
        assert mock_ws in manager.active_connections

    @pytest.mark.asyncio
    async def test_connect_multiple_clients(self, manager):
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        await manager.connect(ws1)
        await manager.connect(ws2)

        assert len(manager.active_connections) == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, manager):
        mock_ws = AsyncMock(spec=WebSocket)
        manager.active_connections.append(mock_ws)

        await manager.disconnect(mock_ws)

        assert mock_ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_absent_client_does_not_raise(self, manager):
        mock_ws = AsyncMock(spec=WebSocket)
        await manager.disconnect(mock_ws)  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, manager):
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        manager.active_connections = [ws1, ws2]

        message = {"type": "positions", "positions": []}
        await manager.broadcast(message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self, manager):
        ws_good = AsyncMock(spec=WebSocket)
        ws_bad = AsyncMock(spec=WebSocket)
        ws_bad.send_json.side_effect = Exception("Connection closed")
        manager.active_connections = [ws_good, ws_bad]

        await manager.broadcast({"type": "test"})

        assert ws_good in manager.active_connections
        assert ws_bad not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections(self, manager):
        # Should not raise
        await manager.broadcast({"type": "test"})

    @pytest.mark.asyncio
    async def test_client_count(self, manager):
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        manager.active_connections = [ws1, ws2]

        count = await manager.client_count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_client_count_empty(self, manager):
        count = await manager.client_count()
        assert count == 0


class TestDatabaseDeduplication:
    """Tests for the Database.should_insert_position deduplication logic."""

    def _make_db(self):
        """Create a Database instance with no actual SQLite connection."""
        db = Database.__new__(Database)
        db._position_cache = {}
        return db

    def _make_cached(
        self, lat, lon, speed=None, timestamp="2024-01-15T10:00:00Z", first_seen=None
    ):
        return CachedPosition(
            lat=lat,
            lon=lon,
            speed=speed,
            timestamp=timestamp,
            first_seen_at_location=first_seen,
        )

    def test_first_position_for_vessel_always_inserted(self):
        db = self._make_db()
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == "2024-01-15T10:00:00Z"

    def test_missing_mmsi_not_inserted(self):
        db = self._make_db()
        data = {"lat": 48.5, "lon": -123.4, "timestamp": "2024-01-15T10:00:00Z"}
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is False
        assert first_seen is None

    def test_stationary_vessel_within_dedup_distance_skipped(self):
        """Position within 100m and no significant time elapsed should be deduplicated."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=0.0, timestamp="2024-01-15T10:00:00Z"
        )
        # Same position, still within 5-minute window
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is False

    def test_moving_vessel_always_inserted(self):
        """Vessel with speed above DEDUP_SPEED_THRESHOLD is always inserted."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=5.0, timestamp="2024-01-15T10:00:00Z"
        )
        data = {
            "mmsi": "123456789",
            "lat": 48.5001,
            "lon": -123.4001,
            "speed": 5.0,  # above 0.5 knot threshold
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_stationary_vessel_inserts_after_time_threshold(self):
        """Stationary vessel should be inserted if enough time (>300s) has elapsed."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=0.0, timestamp="2024-01-15T10:00:00Z"
        )
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-01-15T10:06:00Z",  # 6 minutes later — exceeds 300s
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_vessel_moved_beyond_distance_threshold_inserted(self):
        """Vessel that moved more than 100m is always inserted regardless of speed."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=0.0, timestamp="2024-01-15T10:00:00Z"
        )
        # Move ~1 km north
        data = {
            "mmsi": "123456789",
            "lat": 48.509,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_update_cache_stores_position(self):
        db = self._make_db()
        data = {
            "lat": 48.5,
            "lon": -123.4,
            "speed": 2.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        db.update_cache("123456789", data, "2024-01-15T09:00:00Z")

        cached = db._position_cache["123456789"]
        assert cached.lat == 48.5
        assert cached.lon == -123.4
        assert cached.speed == 2.0
        assert cached.first_seen_at_location == "2024-01-15T09:00:00Z"

    def test_get_cached_position_returns_none_for_unknown(self):
        db = self._make_db()
        result = db.get_cached_position("999999999")
        assert result is None

    def test_get_cached_position_returns_entry(self):
        db = self._make_db()
        cached = self._make_cached(lat=48.5, lon=-123.4)
        db._position_cache["123456789"] = cached

        result = db.get_cached_position("123456789")
        assert result is cached

    def test_get_cache_size(self):
        db = self._make_db()
        assert db.get_cache_size() == 0
        db._position_cache["111"] = self._make_cached(48.5, -123.4)
        db._position_cache["222"] = self._make_cached(49.0, -124.0)
        assert db.get_cache_size() == 2

    def test_invalid_timestamps_fall_through_to_insert(self):
        """Unparseable timestamps trigger insert rather than deduplication."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=0.0, timestamp="not-a-valid-ts"
        )
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "also-not-valid",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True

    def test_none_speed_treated_as_zero(self):
        """None speed is coerced to 0.0 and compared against the speed threshold."""
        db = self._make_db()
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5, lon=-123.4, speed=None, timestamp="2024-01-15T10:00:00Z"
        )
        # Same location, speed=None, 1 minute later — within time threshold
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": None,
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is False

    def test_moving_vessel_within_moored_radius_keeps_first_seen(self):
        """Moving vessel within 500m of original location preserves first_seen."""
        db = self._make_db()
        original_first_seen = "2024-01-15T08:00:00Z"
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5,
            lon=-123.4,
            speed=5.0,
            timestamp="2024-01-15T10:00:00Z",
            first_seen=original_first_seen,
        )
        # Move ~200m north — inside MOORED_RADIUS_METERS (500m)
        data = {
            "mmsi": "123456789",
            "lat": 48.5018,
            "lon": -123.4,
            "speed": 5.0,  # above threshold
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == original_first_seen

    def test_moving_vessel_beyond_moored_radius_resets_first_seen(self):
        """Moving vessel beyond 500m resets first_seen to current timestamp."""
        db = self._make_db()
        original_first_seen = "2024-01-15T08:00:00Z"
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5,
            lon=-123.4,
            speed=5.0,
            timestamp="2024-01-15T10:00:00Z",
            first_seen=original_first_seen,
        )
        # Move ~1 km north — outside MOORED_RADIUS_METERS (500m)
        new_timestamp = "2024-01-15T10:01:00Z"
        data = {
            "mmsi": "123456789",
            "lat": 48.509,
            "lon": -123.4,
            "speed": 5.0,
            "timestamp": new_timestamp,
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == new_timestamp

    def test_slow_vessel_moved_200m_within_moored_radius_keeps_first_seen(self):
        """Slow vessel that moved 200m (>100m dedup, <500m moored) keeps first_seen."""
        db = self._make_db()
        original_first_seen = "2024-01-15T08:00:00Z"
        db._position_cache["123456789"] = self._make_cached(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-01-15T10:00:00Z",
            first_seen=original_first_seen,
        )
        # Move ~200m north: beyond DEDUP_DISTANCE_METERS (100m) but inside 500m
        data = {
            "mmsi": "123456789",
            "lat": 48.5018,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-01-15T10:01:00Z",
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == original_first_seen


class TestShipsAPIService:
    """Tests for ShipsAPIService message processing and lifecycle."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    def test_initial_state(self, service):
        """ShipsAPIService starts with expected default values."""
        assert service.nc is None
        assert service.js is None
        assert service.running is False
        assert service.ready is False
        assert service.replay_complete is False
        assert service.messages_received == 0
        assert service.messages_deduplicated == 0
        assert service.subscription_task is None
        assert service.cleanup_task is None

    def test_process_message_sync_position_insert(self, service):
        """Position message on ais.position.* returns ('position', data, first_seen)."""
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 5.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = service._process_message_sync(
            "ais.position.123456789", json.dumps(data).encode()
        )

        assert result is not None
        msg_type, payload, first_seen = result
        assert msg_type == "position"
        assert payload["mmsi"] == "123456789"
        assert first_seen is not None

    def test_process_message_sync_position_deduplicated(self, service):
        """Identical nearby position for stationary vessel returns ('deduplicated', ...)."""
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        # First call always inserts
        result = service._process_message_sync(
            "ais.position.123456789", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, _, first_seen = result
        assert msg_type == "position"
        service.db.update_cache("123456789", data, first_seen)

        # Second call — same spot, 1 min later, within dedup window
        data2 = {**data, "timestamp": "2024-01-15T10:01:00Z"}
        result2 = service._process_message_sync(
            "ais.position.123456789", json.dumps(data2).encode()
        )
        assert result2 is not None
        assert result2[0] == "deduplicated"

    def test_process_message_sync_vessel(self, service):
        """Static message on ais.static.* returns ('vessel', data, None)."""
        data = {
            "mmsi": "123456789",
            "name": "Test Vessel",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = service._process_message_sync(
            "ais.static.123456789", json.dumps(data).encode()
        )

        assert result is not None
        msg_type, payload, first_seen = result
        assert msg_type == "vessel"
        assert payload["mmsi"] == "123456789"
        assert first_seen is None

    def test_process_message_sync_invalid_json_returns_none(self, service):
        """Invalid JSON payload returns None."""
        result = service._process_message_sync(
            "ais.position.123456789", b"not valid json"
        )
        assert result is None

    def test_process_message_sync_missing_mmsi_returns_none(self, service):
        """Message without mmsi field returns None."""
        data = {"lat": 48.5, "lon": -123.4}
        result = service._process_message_sync(
            "ais.position.123456789", json.dumps(data).encode()
        )
        assert result is None

    def test_process_message_sync_unknown_subject_returns_none(self, service):
        """Message on unrecognised subject prefix returns None."""
        data = {"mmsi": "123456789", "lat": 48.5}
        result = service._process_message_sync(
            "other.subject.123456789", json.dumps(data).encode()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_connect_nats_sets_nc_and_js(self, service):
        """connect_nats sets nc and js on the service."""
        import nats as nats_module

        mock_nc = MagicMock()
        mock_js = MagicMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        assert service.nc is mock_nc
        assert service.js is mock_js

    @pytest.mark.asyncio
    async def test_stop_sets_flags_and_closes_nats(self, service):
        """stop() sets running/ready to False and closes NATS connection."""
        service.running = True
        service.ready = True
        service.nc = AsyncMock()

        await service.stop()

        assert service.running is False
        assert service.ready is False
        service.nc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, service):
        """stop() cancels cleanup_task and subscription_task."""
        service.running = True
        service.nc = AsyncMock()

        async def _long_running():
            await asyncio.sleep(100)

        service.cleanup_task = asyncio.create_task(_long_running())
        service.subscription_task = asyncio.create_task(_long_running())

        await service.stop()

        assert service.cleanup_task.done()
        assert service.subscription_task.done()

    @pytest.mark.asyncio
    async def test_stop_handles_none_tasks_gracefully(self, service):
        """stop() with no tasks does not raise."""
        service.running = True
        service.nc = AsyncMock()
        # tasks are None by default

        await service.stop()  # Should not raise

        assert service.running is False
