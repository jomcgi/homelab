"""Tests for Ships API service."""

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
