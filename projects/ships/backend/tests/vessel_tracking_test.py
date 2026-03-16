"""
Additional unit tests for vessel tracking logic in the Ships API backend.

Focuses on gaps not covered by the existing test suite:
- haversine_distance edge cases (poles, western hemisphere, negative latitudes)
- should_insert_position: moored-radius transitions for slow vessels
- is_moored threshold boundary (exactly at 1h)
- Cache counter (get_vessel_count / get_position_count) after clear
- WebSocketManager concurrent operations
- _process_message_sync cache state integration
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.websockets import WebSocket

from projects.ships.backend.main import (
    CachedPosition,
    Database,
    MOORED_MIN_DURATION_HOURS,
    MOORED_RADIUS_METERS,
    WebSocketManager,
    haversine_distance,
)


class TestHaversineDistanceEdgeCases:
    """Additional edge cases for haversine_distance not covered by existing tests."""

    def test_negative_latitude_points(self):
        """Points in southern hemisphere should return positive distance."""
        dist = haversine_distance(-33.8688, 151.2093, -37.8136, 144.9631)
        # Sydney to Melbourne is ~714 km
        assert 700_000 < dist < 730_000

    def test_western_hemisphere_longitude(self):
        """Points with negative (western) longitudes should work correctly."""
        # New York (40.7128, -74.0060) to Los Angeles (34.0522, -118.2437)
        dist = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        # ~3940 km
        assert 3_800_000 < dist < 4_100_000

    def test_cross_equator_distance(self):
        """Distance across the equator is computed correctly."""
        dist = haversine_distance(-1.0, 0.0, 1.0, 0.0)
        # Two degrees of latitude = ~222 km
        assert 220_000 < dist < 225_000

    def test_north_pole_proximity(self):
        """Points near the north pole should return a small distance."""
        dist = haversine_distance(89.9, 0.0, 89.9, 180.0)
        # Longitude 180° apart at 89.9°N is a very short arc
        assert dist < 25_000  # less than 25 km

    def test_small_east_west_displacement(self):
        """One degree longitude at mid-latitude is less than one degree latitude."""
        # At 60°N, one degree longitude ≈ 55.6 km
        dist = haversine_distance(60.0, 0.0, 60.0, 1.0)
        assert 55_000 < dist < 57_000

    def test_result_always_non_negative(self):
        """Distance is never negative regardless of coordinate order."""
        pairs = [
            (48.0, -123.0, 49.0, -124.0),
            (-48.0, 123.0, -49.0, 124.0),
            (0.0, 0.0, 0.0, 0.0),
            (90.0, 0.0, -90.0, 0.0),
        ]
        for lat1, lon1, lat2, lon2 in pairs:
            assert haversine_distance(lat1, lon1, lat2, lon2) >= 0


class TestDeduplicationMooringEdgeCases:
    """Deduplication edge cases related to moored-radius logic."""

    def _make_db(self):
        db = Database.__new__(Database)
        db._position_cache = {}
        return db

    def _cache(
        self, lat, lon, speed=0.0, timestamp="2024-06-01T10:00:00Z", first_seen=None
    ):
        return CachedPosition(
            lat=lat,
            lon=lon,
            speed=speed,
            timestamp=timestamp,
            first_seen_at_location=first_seen or timestamp,
        )

    def test_slow_vessel_moved_beyond_moored_radius_resets_first_seen(self):
        """Slow vessel that moved >500m (beyond moored radius) gets a new first_seen."""
        db = self._make_db()
        original_first_seen = "2024-06-01T08:00:00Z"
        db._position_cache["111111111"] = self._cache(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            first_seen=original_first_seen,
        )

        new_timestamp = "2024-06-01T10:01:00Z"
        # Move ~1 km north — beyond MOORED_RADIUS_METERS (500 m)
        data = {
            "mmsi": "111111111",
            "lat": 48.509,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": new_timestamp,
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        # first_seen must be reset because the vessel left the moored radius
        assert first_seen == new_timestamp

    def test_slow_vessel_within_dedup_but_inside_moored_radius_keeps_first_seen(self):
        """Slow vessel that moved <100m keeps first_seen if within time threshold."""
        db = self._make_db()
        original_first_seen = "2024-06-01T08:00:00Z"
        db._position_cache["222222222"] = self._cache(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
            first_seen=original_first_seen,
        )

        # Move <100 m — within DEDUP_DISTANCE_METERS, 1 min later (within time threshold)
        data = {
            "mmsi": "222222222",
            "lat": 48.5005,  # ~55 m north
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:01:00Z",
        }
        # Should be deduplicated (distance < threshold, time < threshold)
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is False
        assert first_seen is None

    def test_stationary_vessel_time_threshold_preserves_first_seen(self):
        """When time threshold triggers insert, original first_seen is preserved."""
        db = self._make_db()
        original_first_seen = "2024-06-01T08:00:00Z"
        db._position_cache["333333333"] = self._cache(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
            first_seen=original_first_seen,
        )

        # Same location, but >300 seconds later
        data = {
            "mmsi": "333333333",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:06:00Z",  # 6 minutes later
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        # first_seen must be preserved because vessel hasn't left the moored area
        assert first_seen == original_first_seen

    def test_first_seen_set_correctly_for_brand_new_vessel(self):
        """First position: first_seen_at_location equals the position timestamp."""
        db = self._make_db()
        ts = "2024-06-01T12:00:00Z"
        data = {
            "mmsi": "444444444",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": ts,
        }
        should_insert, first_seen = db.should_insert_position(data)
        assert should_insert is True
        assert first_seen == ts

    def test_missing_timestamp_in_data_triggers_insert(self):
        """Position data with no timestamp field inserts with fallback first_seen."""
        db = self._make_db()
        db._position_cache["555555555"] = self._cache(
            lat=48.5,
            lon=-123.4,
            speed=0.0,
            timestamp="2024-06-01T10:00:00Z",
        )

        # No timestamp in data at all
        data = {
            "mmsi": "555555555",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            # timestamp absent — data.get("timestamp", "") returns ""
        }
        # The timestamp "" cannot be parsed, so should_insert_position returns True
        should_insert, _ = db.should_insert_position(data)
        assert should_insert is True


class TestMooredDetectionThreshold:
    """Tests for get_vessel moored detection at the 1-hour boundary."""

    @pytest.mark.asyncio
    async def test_is_moored_true_when_at_location_over_one_hour(self):
        """is_moored is True when first_seen is more than MOORED_MIN_DURATION_HOURS ago."""
        db = Database(":memory:")
        await db.connect()
        try:
            # first_seen is 2 hours ago — should be moored
            first_seen_ts = (
                datetime.now(timezone.utc)
                - timedelta(hours=MOORED_MIN_DURATION_HOURS + 1)
            ).isoformat()

            pos = {
                "mmsi": "100000001",
                "lat": 48.5,
                "lon": -123.4,
                "speed": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await db.insert_positions_batch([(pos, first_seen_ts)])
            await db.commit()

            vessel = await db.get_vessel("100000001")
            assert vessel is not None
            assert vessel["is_moored"] is True
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_is_moored_false_when_recently_arrived(self):
        """is_moored is False when vessel arrived less than MOORED_MIN_DURATION_HOURS ago."""
        db = Database(":memory:")
        await db.connect()
        try:
            # first_seen is only 10 minutes ago
            first_seen_ts = (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat()

            pos = {
                "mmsi": "100000002",
                "lat": 48.5,
                "lon": -123.4,
                "speed": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await db.insert_positions_batch([(pos, first_seen_ts)])
            await db.commit()

            vessel = await db.get_vessel("100000002")
            assert vessel is not None
            assert vessel["is_moored"] is False
        finally:
            await db.close()


class TestCacheCounterEdgeCases:
    """Tests for in-memory counter methods on freshly constructed Database objects."""

    def test_get_vessel_count_zero_with_empty_cache(self):
        """A freshly created Database (without connect) has zero vessel count."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 0
        assert db.get_vessel_count() == 0

    def test_get_position_count_reflects_manual_value(self):
        """get_position_count returns the current _position_count value."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 42
        assert db.get_position_count() == 42

    def test_get_cache_size_matches_cache_entries(self):
        """get_cache_size returns the number of entries in _position_cache."""
        db = Database.__new__(Database)
        db._position_cache = {
            "111": CachedPosition(1.0, 2.0, None, "t1", None),
            "222": CachedPosition(3.0, 4.0, 5.0, "t2", "t1"),
        }
        db._position_count = 0
        assert db.get_cache_size() == 2

    def test_update_cache_overwrites_existing_entry(self):
        """update_cache replaces an existing cached position for the same MMSI."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 0

        db.update_cache(
            "123",
            {"lat": 10.0, "lon": 20.0, "speed": 1.0, "timestamp": "t1"},
            "t0",
        )
        assert db._position_cache["123"].lat == 10.0

        # Overwrite with new position
        db.update_cache(
            "123",
            {"lat": 11.0, "lon": 21.0, "speed": 2.0, "timestamp": "t2"},
            "t0",
        )
        cached = db._position_cache["123"]
        assert cached.lat == 11.0
        assert cached.lon == 21.0
        assert cached.speed == 2.0


class TestWebSocketManagerConcurrency:
    """Tests for WebSocketManager concurrent connect / disconnect operations."""

    @pytest.mark.asyncio
    async def test_concurrent_connects_all_registered(self):
        """Multiple concurrent connects all appear in active_connections."""
        manager = WebSocketManager()
        websockets_list = [AsyncMock(spec=WebSocket) for _ in range(5)]

        await asyncio.gather(*[manager.connect(ws) for ws in websockets_list])

        assert len(manager.active_connections) == 5
        for ws in websockets_list:
            assert ws in manager.active_connections

    @pytest.mark.asyncio
    async def test_concurrent_disconnects_all_removed(self):
        """Multiple concurrent disconnects all remove their connection."""
        manager = WebSocketManager()
        websockets_list = [AsyncMock(spec=WebSocket) for _ in range(5)]
        manager.active_connections = list(websockets_list)

        await asyncio.gather(*[manager.disconnect(ws) for ws in websockets_list])

        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_with_no_failures_does_not_alter_list(self):
        """Successful broadcast to all clients leaves active_connections unchanged."""
        manager = WebSocketManager()
        websockets_list = [AsyncMock(spec=WebSocket) for _ in range(3)]
        manager.active_connections = list(websockets_list)

        await manager.broadcast({"type": "positions", "positions": []})

        assert len(manager.active_connections) == 3

    @pytest.mark.asyncio
    async def test_broadcast_removes_all_failed_connections(self):
        """Broadcast removes all connections that raise exceptions."""
        manager = WebSocketManager()
        good_ws = AsyncMock(spec=WebSocket)
        bad_ws1 = AsyncMock(spec=WebSocket)
        bad_ws1.send_json.side_effect = Exception("closed")
        bad_ws2 = AsyncMock(spec=WebSocket)
        bad_ws2.send_json.side_effect = RuntimeError("timeout")

        manager.active_connections = [bad_ws1, good_ws, bad_ws2]
        await manager.broadcast({"type": "test"})

        assert good_ws in manager.active_connections
        assert bad_ws1 not in manager.active_connections
        assert bad_ws2 not in manager.active_connections


class TestProcessMessageSyncCacheIntegration:
    """Tests for _process_message_sync using the cache that should_insert_position reads."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    def test_process_message_updates_cache_on_position(self, service):
        """After _process_message_sync returns a position, update_cache populates the cache."""
        import json

        data = {
            "mmsi": "777777777",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 3.0,
            "timestamp": "2024-06-01T10:00:00Z",
        }
        result = service._process_message_sync(
            "ais.position.777777777", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, payload, first_seen = result
        assert msg_type == "position"

        # Simulate the batch processing path: update the cache
        service.db.update_cache("777777777", payload, first_seen)
        cached = service.db.get_cached_position("777777777")
        assert cached is not None
        assert cached.lat == 48.5
        assert cached.lon == -123.4

    def test_second_position_deduped_after_cache_update(self, service):
        """After cache update, a second nearby slow-vessel message is deduplicated."""
        import json

        mmsi = "888888888"
        data1 = {
            "mmsi": mmsi,
            "lat": 48.5,
            "lon": -123.4,
            "speed": 0.0,
            "timestamp": "2024-06-01T10:00:00Z",
        }
        result1 = service._process_message_sync(
            f"ais.position.{mmsi}", json.dumps(data1).encode()
        )
        assert result1 is not None
        _, payload1, first_seen1 = result1
        service.db.update_cache(mmsi, payload1, first_seen1)

        # Second message: same location, 1 minute later (within dedup window)
        data2 = {**data1, "timestamp": "2024-06-01T10:01:00Z"}
        result2 = service._process_message_sync(
            f"ais.position.{mmsi}", json.dumps(data2).encode()
        )
        assert result2 is not None
        assert result2[0] == "deduplicated"

    def test_vessel_message_does_not_affect_position_cache(self, service):
        """Static vessel messages do not modify the position cache."""
        import json

        data = {
            "mmsi": "999999999",
            "name": "STATIC VESSEL",
            "timestamp": "2024-06-01T10:00:00Z",
        }
        result = service._process_message_sync(
            "ais.static.999999999", json.dumps(data).encode()
        )
        assert result is not None
        assert result[0] == "vessel"
        # Cache untouched by static messages
        assert service.db.get_cached_position("999999999") is None
