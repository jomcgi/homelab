"""
Unit tests for projects/ships/backend/main.py.

Covers the five core components with mocked external dependencies:
- haversine_distance() pure function with known geodesic coordinates
- CachedPosition dataclass field access and equality
- Database class methods (cache operations, deduplication, async CRUD)
- WebSocketManager lifecycle (connect, disconnect, broadcast, client_count)
- ShipsAPIService initialisation, message processing, and stop()
"""

import asyncio
import json
import math
import os
from dataclasses import fields as dataclass_fields
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# haversine_distance
# ---------------------------------------------------------------------------


class TestHaversineDistanceKnownCoordinates:
    """Validate haversine_distance against independently verifiable geodesic values."""

    def setup_method(self):
        from projects.ships.backend.main import haversine_distance

        self.h = haversine_distance

    def test_same_point_is_exactly_zero(self):
        """Distance from a point to itself must be 0."""
        assert self.h(0.0, 0.0, 0.0, 0.0) == 0.0

    def test_pole_to_itself(self):
        """North Pole to North Pole must be 0."""
        assert self.h(90.0, 0.0, 90.0, 0.0) == 0.0

    def test_london_to_paris_approx_343km(self):
        """London (51.5074, -0.1278) → Paris (48.8566, 2.3522) ≈ 343 km."""
        d = self.h(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330_000 < d < 360_000, f"Expected ~343 km, got {d:.0f} m"

    def test_new_york_to_london_approx_5570km(self):
        """New York (40.7128, -74.0060) → London (51.5074, -0.1278) ≈ 5570 km."""
        d = self.h(40.7128, -74.0060, 51.5074, -0.1278)
        assert 5_400_000 < d < 5_700_000, f"Expected ~5570 km, got {d:.0f} m"

    def test_equatorial_one_degree_longitude_approx_111km(self):
        """One degree of longitude on the equator ≈ 111 km."""
        d = self.h(0.0, 0.0, 0.0, 1.0)
        assert 110_000 < d < 112_000, f"Expected ~111 km, got {d:.0f} m"

    def test_one_degree_latitude_approx_111km(self):
        """One degree of latitude ≈ 111 km regardless of longitude."""
        d = self.h(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000, f"Expected ~111 km, got {d:.0f} m"

    def test_symmetry_ab_equals_ba(self):
        """Distance A→B must equal B→A."""
        a = self.h(51.5074, -0.1278, 48.8566, 2.3522)
        b = self.h(48.8566, 2.3522, 51.5074, -0.1278)
        assert abs(a - b) < 1e-6, f"Asymmetry: {a} vs {b}"

    def test_antipodal_points_near_maximum(self):
        """Antipodal points on the equator give ~half Earth circumference (~20 Mm)."""
        d = self.h(0.0, 0.0, 0.0, 180.0)
        assert d > 19_000_000

    def test_crosses_international_date_line(self):
        """Crossing the date line (170°E to 170°W) produces a short distance."""
        # Points are 20° of longitude apart via the date line
        d = self.h(0.0, 170.0, 0.0, -170.0)
        # Straight equatorial distance: ~2222 km
        assert 2_100_000 < d < 2_350_000

    def test_short_distance_100m(self):
        """Two points ~100 m apart (0.001° latitude at equator)."""
        d = self.h(0.0, 0.0, 0.001, 0.0)
        # 0.001° latitude ≈ 111 m
        assert 100 < d < 125

    def test_return_type_is_float(self):
        """haversine_distance must return a float, not int."""
        result = self.h(0.0, 0.0, 1.0, 1.0)
        assert isinstance(result, float)

    def test_uses_earth_radius_6371km(self):
        """Result is consistent with Earth radius R = 6 371 000 m."""
        # Quarter-circle: 90° latitude change ≈ π/2 * R = 10,007,543 m
        d = self.h(0.0, 0.0, 90.0, 0.0)
        expected = math.pi / 2 * 6_371_000
        assert abs(d - expected) < 1000, f"Expected ~{expected:.0f} m, got {d:.0f} m"


# ---------------------------------------------------------------------------
# CachedPosition
# ---------------------------------------------------------------------------


class TestCachedPosition:
    """Unit tests for the CachedPosition dataclass."""

    def _make(self, lat=1.0, lon=2.0, speed=3.0, ts="2024-01-01T00:00:00Z", fs=None):
        from projects.ships.backend.main import CachedPosition

        return CachedPosition(
            lat=lat, lon=lon, speed=speed, timestamp=ts, first_seen_at_location=fs
        )

    def test_field_names_are_correct(self):
        """CachedPosition exposes the five documented fields."""
        from projects.ships.backend.main import CachedPosition

        names = {f.name for f in dataclass_fields(CachedPosition)}
        assert names == {"lat", "lon", "speed", "timestamp", "first_seen_at_location"}

    def test_lat_field_accessible(self):
        cp = self._make(lat=48.5)
        assert cp.lat == 48.5

    def test_lon_field_accessible(self):
        cp = self._make(lon=-123.4)
        assert cp.lon == -123.4

    def test_speed_field_accessible(self):
        cp = self._make(speed=12.5)
        assert cp.speed == 12.5

    def test_speed_can_be_none(self):
        """speed is typed as float | None; None must be accepted."""
        cp = self._make(speed=None)
        assert cp.speed is None

    def test_timestamp_field_accessible(self):
        cp = self._make(ts="2024-06-15T10:30:00Z")
        assert cp.timestamp == "2024-06-15T10:30:00Z"

    def test_first_seen_at_location_defaults_to_none(self):
        cp = self._make(fs=None)
        assert cp.first_seen_at_location is None

    def test_first_seen_at_location_set(self):
        cp = self._make(fs="2024-01-01T08:00:00Z")
        assert cp.first_seen_at_location == "2024-01-01T08:00:00Z"

    def test_equality_same_values(self):
        """Two CachedPosition instances with identical values must be equal."""
        a = self._make(lat=1.0, lon=2.0, speed=3.0)
        b = self._make(lat=1.0, lon=2.0, speed=3.0)
        assert a == b

    def test_inequality_different_lat(self):
        a = self._make(lat=1.0)
        b = self._make(lat=2.0)
        assert a != b


# ---------------------------------------------------------------------------
# Database class methods
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    """Tests for Database.__init__ setup state."""

    def test_db_path_stored(self):
        from projects.ships.backend.main import Database

        db = Database("/tmp/test.db")
        assert db.db_path == "/tmp/test.db"

    def test_position_cache_empty_on_init(self):
        from projects.ships.backend.main import Database

        db = Database(":memory:")
        assert db._position_cache == {}

    def test_position_count_zero_on_init(self):
        from projects.ships.backend.main import Database

        db = Database(":memory:")
        assert db._position_count == 0

    def test_db_connection_none_on_init(self):
        from projects.ships.backend.main import Database

        db = Database(":memory:")
        assert db.db is None

    def test_read_db_none_on_init(self):
        from projects.ships.backend.main import Database

        db = Database(":memory:")
        assert db._read_db is None


class TestDatabaseCacheOperations:
    """Tests for in-memory cache helpers (no SQLite required)."""

    def _bare(self):
        from projects.ships.backend.main import Database

        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 0
        return db

    def test_get_cached_position_returns_none_for_unknown_mmsi(self):
        db = self._bare()
        assert db.get_cached_position("999999999") is None

    def test_get_cached_position_returns_entry_after_update(self):
        from projects.ships.backend.main import CachedPosition

        db = self._bare()
        data = {
            "lat": 51.5,
            "lon": -0.1,
            "speed": 5.0,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        db.update_cache("123456789", data, "2024-01-01T00:00:00Z")
        cached = db.get_cached_position("123456789")
        assert isinstance(cached, CachedPosition)
        assert cached.lat == 51.5
        assert cached.lon == -0.1

    def test_update_cache_stores_first_seen(self):
        db = self._bare()
        data = {
            "lat": 0.0,
            "lon": 0.0,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        db.update_cache("111", data, "2024-01-01T08:00:00Z")
        assert (
            db.get_cached_position("111").first_seen_at_location
            == "2024-01-01T08:00:00Z"
        )

    def test_update_cache_overwrites_existing_entry(self):
        db = self._bare()
        data1 = {
            "lat": 1.0,
            "lon": 1.0,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        data2 = {
            "lat": 2.0,
            "lon": 2.0,
            "speed": 5.0,
            "timestamp": "2024-01-01T10:05:00Z",
        }
        db.update_cache("111", data1, None)
        db.update_cache("111", data2, None)
        cached = db.get_cached_position("111")
        assert cached.lat == 2.0

    def test_get_cache_size_zero_initially(self):
        db = self._bare()
        assert db.get_cache_size() == 0

    def test_get_cache_size_increases_after_update(self):
        db = self._bare()
        for i in range(3):
            db.update_cache(
                str(i),
                {
                    "lat": float(i),
                    "lon": 0.0,
                    "speed": 0.0,
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                None,
            )
        assert db.get_cache_size() == 3

    def test_get_vessel_count_equals_cache_size(self):
        db = self._bare()
        for i in range(5):
            db.update_cache(
                str(i),
                {
                    "lat": float(i),
                    "lon": 0.0,
                    "speed": 0.0,
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                None,
            )
        assert db.get_vessel_count() == db.get_cache_size()

    def test_get_position_count_returns_zero_initially(self):
        db = self._bare()
        assert db.get_position_count() == 0

    def test_get_position_count_reflects_manual_increment(self):
        db = self._bare()
        db._position_count = 42
        assert db.get_position_count() == 42


class TestDatabaseShouldInsertPosition:
    """Unit tests for deduplication logic in should_insert_position()."""

    def _bare(self):
        from projects.ships.backend.main import Database

        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 0
        return db

    def _cache(self, lat, lon, speed=0.0, ts="2024-01-01T10:00:00Z", first_seen=None):
        from projects.ships.backend.main import CachedPosition

        return CachedPosition(
            lat=lat,
            lon=lon,
            speed=speed,
            timestamp=ts,
            first_seen_at_location=first_seen or ts,
        )

    def test_no_mmsi_returns_false(self):
        db = self._bare()
        ok, fs = db.should_insert_position({"lat": 0.0, "lon": 0.0})
        assert ok is False
        assert fs is None

    def test_empty_mmsi_returns_false(self):
        db = self._bare()
        ok, fs = db.should_insert_position({"mmsi": "", "lat": 0.0, "lon": 0.0})
        assert ok is False

    def test_first_position_always_inserted(self):
        db = self._bare()
        data = {
            "mmsi": "123456789",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        ok, fs = db.should_insert_position(data)
        assert ok is True
        assert fs == "2024-01-01T10:00:00Z"

    def test_moving_vessel_always_inserted(self):
        """Speed > 0.5 knots → always insert."""
        db = self._bare()
        db._position_cache["123"] = self._cache(lat=51.5, lon=-0.1, speed=0.0)
        data = {
            "mmsi": "123",
            "lat": 51.5001,
            "lon": -0.1,
            "speed": 5.0,
            "timestamp": "2024-01-01T10:01:00Z",
        }
        ok, _ = db.should_insert_position(data)
        assert ok is True

    def test_stationary_same_spot_within_time_threshold_deduplicated(self):
        """Stationary vessel, same spot, <300 s → skip."""
        db = self._bare()
        db._position_cache["123"] = self._cache(
            lat=51.5, lon=-0.1, speed=0.0, ts="2024-01-01T10:00:00Z"
        )
        data = {
            "mmsi": "123",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:01:00Z",  # 60 s later
        }
        ok, _ = db.should_insert_position(data)
        assert ok is False

    def test_stationary_same_spot_beyond_time_threshold_inserted(self):
        """Stationary vessel, same spot, >300 s → insert."""
        db = self._bare()
        db._position_cache["123"] = self._cache(
            lat=51.5, lon=-0.1, speed=0.0, ts="2024-01-01T10:00:00Z"
        )
        data = {
            "mmsi": "123",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:06:00Z",  # 360 s later
        }
        ok, _ = db.should_insert_position(data)
        assert ok is True

    def test_vessel_moved_beyond_100m_inserted(self):
        """Movement > 100 m → insert regardless of speed."""
        db = self._bare()
        db._position_cache["123"] = self._cache(lat=51.5, lon=-0.1)
        data = {
            "mmsi": "123",
            "lat": 51.509,  # ~1 km north
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:01:00Z",
        }
        ok, _ = db.should_insert_position(data)
        assert ok is True

    def test_invalid_timestamp_causes_insert(self):
        """Unparseable timestamp → conservative insert."""
        db = self._bare()
        db._position_cache["123"] = self._cache(
            lat=51.5, lon=-0.1, ts="not-a-timestamp"
        )
        data = {
            "mmsi": "123",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "also-invalid",
        }
        ok, _ = db.should_insert_position(data)
        assert ok is True

    def test_none_speed_treated_as_zero(self):
        """speed=None is coerced to 0 and not treated as moving vessel."""
        db = self._bare()
        db._position_cache["123"] = self._cache(lat=51.5, lon=-0.1, speed=None)
        data = {
            "mmsi": "123",
            "lat": 51.5,
            "lon": -0.1,
            "speed": None,
            "timestamp": "2024-01-01T10:01:00Z",
        }
        ok, _ = db.should_insert_position(data)
        # Within 100 m and 60 s → deduplicated
        assert ok is False


@pytest_asyncio.fixture
async def mem_db():
    """In-memory Database with schema created."""
    from projects.ships.backend.main import Database

    db = Database(":memory:")
    await db.connect()
    yield db
    await db.close()


class TestDatabaseAsyncMethods:
    """Async tests for Database CRUD operations against an in-memory SQLite."""

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, mem_db):
        """connect() creates vessels, positions, latest_positions tables."""
        cursor = await mem_db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
        assert {"vessels", "positions", "latest_positions"}.issubset(tables)

    @pytest.mark.asyncio
    async def test_connect_populates_position_count(self, mem_db):
        """_position_count is initialised from the DB after connect()."""
        assert mem_db._position_count == 0

    @pytest.mark.asyncio
    async def test_insert_positions_batch_returns_count(self, mem_db):
        data = {
            "mmsi": "123456789",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 5.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        inserted = await mem_db.insert_positions_batch([(data, "2024-01-01T10:00:00Z")])
        assert inserted == 1

    @pytest.mark.asyncio
    async def test_insert_positions_batch_empty_returns_zero(self, mem_db):
        result = await mem_db.insert_positions_batch([])
        assert result == 0

    @pytest.mark.asyncio
    async def test_insert_positions_batch_updates_position_count(self, mem_db):
        data = {
            "mmsi": "111",
            "lat": 1.0,
            "lon": 1.0,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        await mem_db.insert_positions_batch([(data, None)])
        assert mem_db._position_count == 1

    @pytest.mark.asyncio
    async def test_insert_positions_batch_updates_cache(self, mem_db):
        data = {
            "mmsi": "222",
            "lat": 2.0,
            "lon": 2.0,
            "speed": 1.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        await mem_db.insert_positions_batch([(data, None)])
        assert mem_db.get_cached_position("222") is not None

    @pytest.mark.asyncio
    async def test_upsert_vessels_batch_empty_no_error(self, mem_db):
        """Empty batch must not raise."""
        await mem_db.upsert_vessels_batch([])  # no exception

    @pytest.mark.asyncio
    async def test_upsert_vessels_batch_inserts_vessel(self, mem_db):
        vessel = {
            "mmsi": "123456789",
            "name": "MV Test",
            "ship_type": 70,
            "imo": "IMO1234567",
            "call_sign": "CALL1",
        }
        await mem_db.upsert_vessels_batch([vessel])
        await mem_db.commit()
        cursor = await mem_db.db.execute(
            "SELECT name FROM vessels WHERE mmsi=?", ("123456789",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "MV Test"

    @pytest.mark.asyncio
    async def test_upsert_vessels_batch_coalesce_null_name(self, mem_db):
        """A null name in a second upsert must NOT overwrite an existing name."""
        vessel = {"mmsi": "111", "name": "Original Name"}
        await mem_db.upsert_vessels_batch([vessel])
        await mem_db.commit()
        # Upsert again with name=None — COALESCE should preserve "Original Name"
        await mem_db.upsert_vessels_batch([{"mmsi": "111", "name": None}])
        await mem_db.commit()
        cursor = await mem_db.db.execute(
            "SELECT name FROM vessels WHERE mmsi=?", ("111",)
        )
        row = await cursor.fetchone()
        assert row[0] == "Original Name"

    @pytest.mark.asyncio
    async def test_get_vessel_returns_none_for_unknown(self, mem_db):
        result = await mem_db.get_vessel("000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_vessel_returns_dict_with_position(self, mem_db):
        data = {
            "mmsi": "999",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 5.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        await mem_db.insert_positions_batch([(data, "2024-01-01T10:00:00Z")])
        await mem_db.commit()
        result = await mem_db.get_vessel("999")
        assert result is not None
        assert result["mmsi"] == "999"
        assert result["lat"] == pytest.approx(51.5)

    @pytest.mark.asyncio
    async def test_get_vessel_track_empty(self, mem_db):
        track = await mem_db.get_vessel_track("000000000")
        assert track == []

    @pytest.mark.asyncio
    async def test_get_vessel_track_returns_sorted_positions(self, mem_db):
        """Positions are returned in ascending timestamp order."""
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        positions = []
        for i in range(3):
            ts = (base + timedelta(minutes=i * 10)).isoformat()
            positions.append(
                (
                    {
                        "mmsi": "555",
                        "lat": 51.0 + i * 0.01,
                        "lon": -0.1,
                        "speed": 5.0,
                        "timestamp": ts,
                    },
                    ts,
                )
            )
        await mem_db.insert_positions_batch(positions)
        await mem_db.commit()
        track = await mem_db.get_vessel_track("555")
        assert len(track) == 3
        timestamps = [t["timestamp"] for t in track]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_get_vessel_track_limit_respected(self, mem_db):
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        positions = []
        for i in range(10):
            ts = (base + timedelta(minutes=i)).isoformat()
            positions.append(
                (
                    {
                        "mmsi": "666",
                        "lat": 51.0,
                        "lon": -0.1,
                        "speed": 5.0,
                        "timestamp": ts,
                    },
                    ts,
                )
            )
        await mem_db.insert_positions_batch(positions)
        await mem_db.commit()
        track = await mem_db.get_vessel_track("666", limit=3)
        assert len(track) == 3

    @pytest.mark.asyncio
    async def test_get_latest_positions_returns_list(self, mem_db):
        result = await mem_db.get_latest_positions()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_latest_positions_one_per_vessel(self, mem_db):
        """Only the latest (upserted) position per MMSI appears."""
        for mmsi in ("100", "200", "300"):
            data = {
                "mmsi": mmsi,
                "lat": 51.5,
                "lon": -0.1,
                "speed": 0.0,
                "timestamp": "2024-01-01T10:00:00Z",
            }
            await mem_db.insert_positions_batch([(data, None)])
        await mem_db.commit()
        result = await mem_db.get_latest_positions()
        mmsis = {r["mmsi"] for r in result}
        assert mmsis == {"100", "200", "300"}

    @pytest.mark.asyncio
    async def test_commit_does_not_raise(self, mem_db):
        """commit() is a simple wrapper and must not raise."""
        await mem_db.commit()

    @pytest.mark.asyncio
    async def test_drop_and_create_indexes_idempotent(self, mem_db):
        """drop_indexes() + create_indexes() can be called repeatedly without error."""
        await mem_db.drop_indexes()
        await mem_db.create_indexes()
        await mem_db.drop_indexes()
        await mem_db.create_indexes()

    @pytest.mark.asyncio
    async def test_cleanup_old_positions_returns_zero_for_fresh_db(self, mem_db):
        """No positions → cleanup returns 0."""
        deleted = await mem_db.cleanup_old_positions()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_positions_deletes_old_records(self, mem_db):
        """Positions older than retention window are removed."""
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        data = {
            "mmsi": "777",
            "lat": 0.0,
            "lon": 0.0,
            "speed": 0.0,
            "timestamp": old_ts,
        }
        await mem_db.insert_positions_batch([(data, old_ts)])
        await mem_db.commit()
        deleted = await mem_db.cleanup_old_positions()
        assert deleted >= 1


# ---------------------------------------------------------------------------
# WebSocketManager lifecycle
# ---------------------------------------------------------------------------


class TestWebSocketManagerLifecycle:
    """Unit tests for WebSocketManager connect/disconnect/broadcast/client_count."""

    @pytest.fixture
    def manager(self):
        from projects.ships.backend.main import WebSocketManager

        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_initial_state_empty(self, manager):
        """Fresh manager has no active connections."""
        assert manager.active_connections == []

    @pytest.mark.asyncio
    async def test_initial_client_count_is_zero(self, manager):
        count = await manager.client_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_connect_calls_accept(self, manager):
        ws = AsyncMock()
        await manager.connect(ws)
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_adds_to_active_connections(self, manager):
        ws = AsyncMock()
        await manager.connect(ws)
        assert ws in manager.active_connections

    @pytest.mark.asyncio
    async def test_connect_multiple_clients(self, manager):
        ws1, ws2, ws3 = AsyncMock(), AsyncMock(), AsyncMock()
        for ws in (ws1, ws2, ws3):
            await manager.connect(ws)
        assert len(manager.active_connections) == 3

    @pytest.mark.asyncio
    async def test_client_count_after_connect(self, manager):
        ws1, ws2 = AsyncMock(), AsyncMock()
        await manager.connect(ws1)
        await manager.connect(ws2)
        assert await manager.client_count() == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager):
        ws = AsyncMock()
        await manager.connect(ws)
        await manager.disconnect(ws)
        assert ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_absent_client_no_error(self, manager):
        """Disconnecting a never-connected client must not raise."""
        ws = AsyncMock()
        await manager.disconnect(ws)  # should not raise

    @pytest.mark.asyncio
    async def test_client_count_after_disconnect(self, manager):
        ws = AsyncMock()
        await manager.connect(ws)
        await manager.disconnect(ws)
        assert await manager.client_count() == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, manager):
        ws1, ws2 = AsyncMock(), AsyncMock()
        manager.active_connections = [ws1, ws2]
        msg = {"type": "update", "data": []}
        await manager.broadcast(msg)
        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_client(self, manager):
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_json.side_effect = Exception("disconnected")
        manager.active_connections = [ws_good, ws_bad]
        await manager.broadcast({"type": "test"})
        assert ws_good in manager.active_connections
        assert ws_bad not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections_no_error(self, manager):
        """Broadcast with no connected clients must not raise."""
        await manager.broadcast({"type": "test"})

    @pytest.mark.asyncio
    async def test_broadcast_all_fail_connections_cleared(self, manager):
        """If all clients fail, all are removed."""
        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.send_json.side_effect = Exception("closed")
        ws2.send_json.side_effect = Exception("closed")
        manager.active_connections = [ws1, ws2]
        await manager.broadcast({"type": "test"})
        assert manager.active_connections == []

    @pytest.mark.asyncio
    async def test_manager_has_asyncio_lock(self, manager):
        """The lock attribute must be an asyncio.Lock."""
        assert isinstance(manager.lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# ShipsAPIService
# ---------------------------------------------------------------------------


class TestShipsAPIServiceInit:
    """Tests for ShipsAPIService.__init__ defaults."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    def test_nc_is_none(self, service):
        assert service.nc is None

    def test_js_is_none(self, service):
        assert service.js is None

    def test_running_false(self, service):
        assert service.running is False

    def test_ready_false(self, service):
        assert service.ready is False

    def test_replay_complete_false(self, service):
        assert service.replay_complete is False

    def test_messages_received_zero(self, service):
        assert service.messages_received == 0

    def test_messages_deduplicated_zero(self, service):
        assert service.messages_deduplicated == 0

    def test_subscription_task_none(self, service):
        assert service.subscription_task is None

    def test_cleanup_task_none(self, service):
        assert service.cleanup_task is None

    def test_db_is_database_instance(self, service):
        from projects.ships.backend.main import Database

        assert isinstance(service.db, Database)

    def test_ws_manager_is_websocket_manager(self, service):
        from projects.ships.backend.main import WebSocketManager

        assert isinstance(service.ws_manager, WebSocketManager)


class TestShipsAPIServiceProcessMessageSync:
    """Unit tests for _process_message_sync (synchronous, no I/O)."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    def _pos(
        self, mmsi="123456789", lat=51.5, lon=-0.1, speed=5.0, ts="2024-01-01T10:00:00Z"
    ):
        return {
            "mmsi": mmsi,
            "lat": lat,
            "lon": lon,
            "speed": speed,
            "timestamp": ts,
        }

    def test_position_subject_returns_position_tuple(self, service):
        data = self._pos()
        result = service._process_message_sync(
            "ais.position.123456789", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, payload, first_seen = result
        assert msg_type == "position"
        assert payload["mmsi"] == "123456789"
        assert first_seen is not None

    def test_static_subject_returns_vessel_tuple(self, service):
        data = {
            "mmsi": "123456789",
            "name": "MV Test",
            "timestamp": "2024-01-01T10:00:00Z",
        }
        result = service._process_message_sync(
            "ais.static.123456789", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, payload, first_seen = result
        assert msg_type == "vessel"
        assert payload["name"] == "MV Test"
        assert first_seen is None

    def test_invalid_json_returns_none(self, service):
        result = service._process_message_sync("ais.position.111", b"{bad json}")
        assert result is None

    def test_empty_bytes_returns_none(self, service):
        result = service._process_message_sync("ais.position.111", b"")
        assert result is None

    def test_missing_mmsi_returns_none(self, service):
        data = {"lat": 51.5, "lon": -0.1}
        result = service._process_message_sync(
            "ais.position.111", json.dumps(data).encode()
        )
        assert result is None

    def test_unknown_subject_returns_none(self, service):
        data = {"mmsi": "111", "lat": 51.5, "lon": -0.1}
        result = service._process_message_sync(
            "unknown.subject.111", json.dumps(data).encode()
        )
        assert result is None

    def test_second_identical_position_deduplicated(self, service):
        """First call inserts; identical second call within dedup window is skipped."""
        data = {
            "mmsi": "999",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": "2024-01-01T10:00:00Z",
        }
        # First call → position
        r1 = service._process_message_sync(
            "ais.position.999", json.dumps(data).encode()
        )
        assert r1 is not None
        _, _, first_seen = r1
        service.db.update_cache("999", data, first_seen)

        # Second call 1 min later — same spot, stationary
        data2 = {**data, "timestamp": "2024-01-01T10:01:00Z"}
        r2 = service._process_message_sync(
            "ais.position.999", json.dumps(data2).encode()
        )
        assert r2 is not None
        assert r2[0] == "deduplicated"

    def test_position_message_increments_no_counters_directly(self, service):
        """_process_message_sync itself does not modify messages_received."""
        data = self._pos()
        before = service.messages_received
        service._process_message_sync("ais.position.123", json.dumps(data).encode())
        assert service.messages_received == before


class TestShipsAPIServiceStop:
    """Unit tests for ShipsAPIService.stop()."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, service):
        service.running = True
        service.nc = AsyncMock()
        await service.stop()
        assert service.running is False

    @pytest.mark.asyncio
    async def test_stop_sets_ready_false(self, service):
        service.ready = True
        service.nc = AsyncMock()
        await service.stop()
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_stop_closes_nats_connection(self, service):
        service.running = True
        nc = AsyncMock()
        service.nc = nc
        await service.stop()
        nc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_with_none_nc_no_error(self, service):
        """stop() when nc is None must not raise."""
        service.running = True
        service.nc = None
        await service.stop()
        assert service.running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_subscription_task(self, service):
        service.running = True
        service.nc = AsyncMock()

        async def _sleep():
            await asyncio.sleep(100)

        task = asyncio.create_task(_sleep())
        service.subscription_task = task
        await service.stop()
        assert task.done()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self, service):
        service.running = True
        service.nc = AsyncMock()

        async def _sleep():
            await asyncio.sleep(100)

        task = asyncio.create_task(_sleep())
        service.cleanup_task = task
        await service.stop()
        assert task.done()

    @pytest.mark.asyncio
    async def test_stop_none_tasks_no_error(self, service):
        """stop() with no background tasks must not raise."""
        service.running = True
        service.nc = AsyncMock()
        # tasks default to None
        await service.stop()


class TestShipsAPIServiceConnectNats:
    """Tests for connect_nats() with mocked nats.connect."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_connect_nats_sets_nc(self, service):
        import nats as nats_module

        mock_nc = MagicMock()
        mock_nc.jetstream.return_value = MagicMock()
        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()
        assert service.nc is mock_nc

    @pytest.mark.asyncio
    async def test_connect_nats_sets_js(self, service):
        import nats as nats_module

        mock_nc = MagicMock()
        mock_js = MagicMock()
        mock_nc.jetstream.return_value = mock_js
        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()
        assert service.js is mock_js

    @pytest.mark.asyncio
    async def test_connect_nats_uses_nats_url(self, service):
        """connect_nats() passes NATS_URL to nats.connect."""
        import nats as nats_module
        from projects.ships.backend.main import NATS_URL

        mock_nc = MagicMock()
        mock_nc.jetstream.return_value = MagicMock()
        mock_connect = AsyncMock(return_value=mock_nc)
        with patch.object(nats_module, "connect", mock_connect):
            await service.connect_nats()
        mock_connect.assert_called_once_with(NATS_URL)


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------


class TestConfigurationConstants:
    """Verify module-level configuration defaults are sensible."""

    def test_dedup_distance_meters_default(self):
        from projects.ships.backend.main import DEDUP_DISTANCE_METERS

        assert DEDUP_DISTANCE_METERS == pytest.approx(100.0)

    def test_dedup_speed_threshold_default(self):
        from projects.ships.backend.main import DEDUP_SPEED_THRESHOLD

        assert DEDUP_SPEED_THRESHOLD == pytest.approx(0.5)

    def test_dedup_time_threshold_default(self):
        from projects.ships.backend.main import DEDUP_TIME_THRESHOLD

        assert DEDUP_TIME_THRESHOLD == 300

    def test_moored_radius_meters_default(self):
        from projects.ships.backend.main import MOORED_RADIUS_METERS

        assert MOORED_RADIUS_METERS == pytest.approx(500.0)

    def test_moored_min_duration_hours_default(self):
        from projects.ships.backend.main import MOORED_MIN_DURATION_HOURS

        assert MOORED_MIN_DURATION_HOURS == pytest.approx(1.0)

    def test_position_retention_days_default(self):
        from projects.ships.backend.main import POSITION_RETENTION_DAYS

        assert POSITION_RETENTION_DAYS == 7

    def test_catchup_pending_threshold_default(self):
        from projects.ships.backend.main import CATCHUP_PENDING_THRESHOLD

        assert CATCHUP_PENDING_THRESHOLD == 10_000

    def test_db_path_default(self):
        """DB_PATH defaults to /tmp/ships.db when env var not set."""
        # The env var may be overridden by conftest; test the module attribute type
        from projects.ships.backend.main import DB_PATH

        assert isinstance(DB_PATH, str)
        assert len(DB_PATH) > 0

    def test_cors_origins_is_list(self):
        from projects.ships.backend.main import CORS_ORIGINS

        assert isinstance(CORS_ORIGINS, list)
        assert len(CORS_ORIGINS) >= 1

    def test_indexes_list_has_two_entries(self):
        """INDEXES must define exactly the two required position indexes."""
        from projects.ships.backend.main import INDEXES

        assert len(INDEXES) == 2
        combined = " ".join(INDEXES)
        assert "idx_positions_mmsi_timestamp" in combined
        assert "idx_positions_timestamp" in combined


# ---------------------------------------------------------------------------
# Database._load_position_cache with non-empty DB
# ---------------------------------------------------------------------------


class TestDatabaseLoadPositionCacheNonEmpty:
    """Tests for _load_position_cache() when the DB already has rows."""

    @pytest.mark.asyncio
    async def test_cache_rebuilt_from_existing_rows_on_reconnect(self, mem_db):
        """Inserting rows, closing, and reconnecting repopulates the in-memory cache.

        Uses the in-memory DB fixture (same connection for read/write) to verify
        that _load_position_cache reads all rows from latest_positions.
        """
        now = "2024-03-01T10:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        positions = [
            (
                {
                    "mmsi": "111111111",
                    "lat": 51.5,
                    "lon": -0.1,
                    "speed": 5.0,
                    "timestamp": now,
                },
                now,
            ),
            (
                {
                    "mmsi": "222222222",
                    "lat": 52.0,
                    "lon": 1.0,
                    "speed": 0.0,
                    "timestamp": now,
                },
                now,
            ),
        ]
        await mem_db.insert_positions_batch(positions)
        await mem_db.commit()

        # Manually clear the cache and reload it to simulate a reconnect
        mem_db._position_cache.clear()
        assert mem_db.get_cache_size() == 0

        await mem_db._load_position_cache()

        assert mem_db.get_cache_size() == 2
        cached = mem_db.get_cached_position("111111111")
        assert cached is not None
        assert cached.lat == pytest.approx(51.5)
        assert cached.lon == pytest.approx(-0.1)

    @pytest.mark.asyncio
    async def test_cache_preserves_first_seen_at_location(self, mem_db):
        """_load_position_cache copies first_seen_at_location from the DB row."""
        first_seen = (
            "2024-01-01T08:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        )
        now = "2024-01-01T10:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        await mem_db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "999888777",
                        "lat": 48.5,
                        "lon": -123.4,
                        "speed": 0.0,
                        "timestamp": now,
                    },
                    first_seen,
                )
            ]
        )
        await mem_db.commit()

        mem_db._position_cache.clear()
        await mem_db._load_position_cache()

        cached = mem_db.get_cached_position("999888777")
        assert cached is not None
        assert cached.first_seen_at_location == first_seen

    @pytest.mark.asyncio
    async def test_cache_empty_on_empty_latest_positions_table(self, mem_db):
        """_load_position_cache on an empty latest_positions table leaves cache empty."""
        mem_db._position_cache.clear()
        await mem_db._load_position_cache()
        assert mem_db.get_cache_size() == 0


# ---------------------------------------------------------------------------
# Database.cleanup_old_positions multi-batch loop
# ---------------------------------------------------------------------------


class TestDatabaseCleanupOldPositionsMultiBatch:
    """Tests for the batched while-True loop in cleanup_old_positions()."""

    def _bare_db_with_mock_conn(self, rowcounts: list[int]):
        """Return a Database with a mock connection that returns rowcounts in order."""
        from projects.ships.backend.main import Database

        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = sum(rowcounts)

        call_count = [0]

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            idx = min(call_count[0], len(rowcounts) - 1)
            cursor.rowcount = rowcounts[idx]
            call_count[0] += 1
            return cursor

        async def fake_commit():
            pass

        mock_conn = MagicMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = fake_commit
        db.db = mock_conn
        db._call_count = call_count
        return db

    @pytest.mark.asyncio
    async def test_loop_continues_when_full_batch_deleted(self):
        """Loop iterates twice when first batch fills 10000 rows, second is partial."""
        db = self._bare_db_with_mock_conn([10000, 5])

        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            total_deleted = await db.cleanup_old_positions()

        assert total_deleted == 10005
        assert db._call_count[0] == 2

    @pytest.mark.asyncio
    async def test_loop_exits_on_partial_first_batch(self):
        """Loop exits after first iteration when deleted < batch_size."""
        db = self._bare_db_with_mock_conn([42])

        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            total_deleted = await db.cleanup_old_positions()

        assert total_deleted == 42
        assert db._call_count[0] == 1

    @pytest.mark.asyncio
    async def test_position_count_decremented_by_total_deleted(self):
        """_position_count is reduced by the total number of deleted rows."""
        initial_count = 10050
        db = self._bare_db_with_mock_conn([10000, 50])
        db._position_count = initial_count

        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            await db.cleanup_old_positions()

        assert db._position_count == initial_count - 10050

    @pytest.mark.asyncio
    async def test_zero_deleted_returns_zero_and_no_position_count_change(self, mem_db):
        """When nothing is old enough to delete, return 0 and leave count unchanged."""
        # Insert a fresh position — timestamp is within the last minute, well inside
        # the retention window regardless of POSITION_RETENTION_DAYS setting.
        now = datetime.now(timezone.utc).isoformat()
        await mem_db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "123",
                        "lat": 0.0,
                        "lon": 0.0,
                        "speed": 0.0,
                        "timestamp": now,
                    },
                    now,
                )
            ]
        )
        await mem_db.commit()
        count_before = mem_db.get_position_count()

        deleted = await mem_db.cleanup_old_positions()

        assert deleted == 0
        assert mem_db.get_position_count() == count_before


# ---------------------------------------------------------------------------
# get_vessel error branches
# ---------------------------------------------------------------------------


class TestGetVesselErrorBranches:
    """Tests for Database.get_vessel() analytics error branches."""

    @pytest.mark.asyncio
    async def test_get_vessel_returns_none_when_no_latest_position(self, mem_db):
        """get_vessel returns None when MMSI has no entry in latest_positions."""
        result = await mem_db.get_vessel("000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_vessel_sets_time_at_location_when_first_seen_valid(self, mem_db):
        """get_vessel populates time_at_location_seconds when first_seen is valid ISO."""
        first_seen = "2000-01-01T00:00:00+00:00"  # very old, so duration is large  # nosemgrep: test-hardcoded-past-timestamp
        now_ts = "2000-01-01T01:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        await mem_db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "111",
                        "lat": 0.0,
                        "lon": 0.0,
                        "speed": 0.0,
                        "timestamp": now_ts,
                    },
                    first_seen,
                )
            ]
        )
        await mem_db.commit()
        result = await mem_db.get_vessel("111")
        assert result is not None
        assert result.get("time_at_location_seconds") is not None
        assert isinstance(result["time_at_location_seconds"], int)
        assert result.get("time_at_location_hours") is not None
        assert "is_moored" in result

    @pytest.mark.asyncio
    async def test_get_vessel_handles_invalid_first_seen_timestamp(self, mem_db):
        """get_vessel sets time fields to None when first_seen_at_location is malformed."""
        # Insert position then manually corrupt first_seen in latest_positions
        now_ts = "2024-06-01T10:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        await mem_db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "222",
                        "lat": 1.0,
                        "lon": 1.0,
                        "speed": 0.0,
                        "timestamp": now_ts,
                    },
                    "not-a-valid-timestamp",
                )
            ]
        )
        await mem_db.commit()

        result = await mem_db.get_vessel("222")
        assert result is not None
        # ValueError path: time fields should be None
        assert result.get("time_at_location_seconds") is None
        assert result.get("time_at_location_hours") is None
        assert result.get("is_moored") is None

    @pytest.mark.asyncio
    async def test_get_vessel_no_first_seen_skips_time_calculation(self, mem_db):
        """get_vessel skips time_at_location fields when first_seen_at_location is NULL."""
        now_ts = "2024-06-01T10:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        await mem_db.insert_positions_batch(
            [
                (
                    {
                        "mmsi": "333",
                        "lat": 2.0,
                        "lon": 2.0,
                        "speed": 0.0,
                        "timestamp": now_ts,
                    },
                    None,  # no first_seen
                )
            ]
        )
        await mem_db.commit()

        result = await mem_db.get_vessel("333")
        assert result is not None
        # time_at_location keys should not be present when first_seen is None
        assert "time_at_location_seconds" not in result
        assert "time_at_location_hours" not in result
        assert "is_moored" not in result


# ---------------------------------------------------------------------------
# subscribe_ais_stream unit tests
# ---------------------------------------------------------------------------


def _make_mock_msg(subject: str, data_dict: dict) -> MagicMock:
    """Return a mock NATS message with .subject, .data, and async .ack()."""
    msg = MagicMock()
    msg.subject = subject
    msg.data = json.dumps(data_dict).encode()
    msg.ack = AsyncMock()
    return msg


def _make_consumer_info(num_pending: int = 0) -> MagicMock:
    """Return a mock consumer_info object with num_pending set."""
    info = MagicMock()
    info.num_pending = num_pending
    return info


def _make_service_for_stream(replay_complete: bool = True):
    """Create a ShipsAPIService with DB and ws_manager mocked out."""
    from projects.ships.backend.main import ShipsAPIService

    svc = ShipsAPIService()
    svc.running = True
    svc.replay_complete = replay_complete
    svc.ready = replay_complete

    svc.db = MagicMock()
    svc.db.should_insert_position = MagicMock(
        return_value=(True, "2024-01-15T10:00:00Z")
    )
    svc.db.insert_positions_batch = AsyncMock()
    svc.db.upsert_vessels_batch = AsyncMock()
    svc.db.commit = AsyncMock()
    svc.db.get_vessel_count = MagicMock(return_value=100)
    svc.db.get_position_count = MagicMock(return_value=1000)

    svc.ws_manager = MagicMock()
    svc.ws_manager.broadcast = AsyncMock()

    return svc


def _attach_js(svc, mock_psub: AsyncMock) -> None:
    """Wire a mock JetStream + pull subscriber onto the service."""
    svc.js = MagicMock()
    svc.js.pull_subscribe = AsyncMock(return_value=mock_psub)


class TestSubscribeAisStreamUnit:
    """Unit tests for ShipsAPIService.subscribe_ais_stream().

    All external I/O is mocked — no real NATS or SQLite required.
    """

    def _one_shot_psub(self, service, msgs: list) -> AsyncMock:
        """Return a mock psub that delivers msgs once then stops the loop."""

        async def fake_fetch(batch, timeout):
            service.running = False
            return msgs

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)
        return mock_psub

    @pytest.mark.asyncio
    async def test_running_false_skips_fetch(self):
        """With running=False before the loop, fetch is never called."""
        service = _make_service_for_stream()
        service.running = False

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(return_value=[])
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        mock_psub.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_pending_sets_replay_complete_and_ready(self):
        """num_pending==0 before the loop sets replay_complete=True and ready=True."""
        service = _make_service_for_stream(replay_complete=False)
        service.running = False

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_position_message_calls_insert_positions_batch(self):
        """A position message triggers insert_positions_batch with the payload."""
        service = _make_service_for_stream(replay_complete=True)
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.insert_positions_batch.assert_called_once()
        batch_arg = service.db.insert_positions_batch.call_args[0][0]
        assert len(batch_arg) == 1
        assert batch_arg[0][0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_vessel_message_calls_upsert_vessels_batch(self):
        """A static AIS message triggers upsert_vessels_batch with the payload."""
        service = _make_service_for_stream(replay_complete=True)
        msg = _make_mock_msg(
            "ais.static.123456789",
            {"mmsi": "123456789", "name": "MV Test"},
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.upsert_vessels_batch.assert_called_once()
        batch_arg = service.db.upsert_vessels_batch.call_args[0][0]
        assert batch_arg[0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_deduplicated_message_increments_counter(self):
        """Positions filtered by dedup logic increment messages_deduplicated."""
        service = _make_service_for_stream(replay_complete=True)
        service.db.should_insert_position = MagicMock(return_value=(False, None))
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.messages_deduplicated == 1

    @pytest.mark.asyncio
    async def test_messages_received_incremented_per_message(self):
        """messages_received is incremented once for each message in the batch."""
        service = _make_service_for_stream(replay_complete=True)
        msgs = [
            _make_mock_msg(
                "ais.position.111",
                {
                    "mmsi": "111",
                    "lat": 0.0,
                    "lon": 0.0,
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.static.222",
                {"mmsi": "222", "name": "Ship B"},
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.messages_received == 2

    @pytest.mark.asyncio
    async def test_commit_called_after_batch(self):
        """db.commit() is called after processing each batch."""
        service = _make_service_for_stream(replay_complete=True)
        msg = _make_mock_msg("ais.static.123", {"mmsi": "123", "name": "T"})
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_messages_acked_after_commit(self):
        """Every message in a batch receives an ack after the DB commit."""
        service = _make_service_for_stream(replay_complete=True)
        msg1 = _make_mock_msg(
            "ais.position.111",
            {
                "mmsi": "111",
                "lat": 0.0,
                "lon": 0.0,
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )
        msg2 = _make_mock_msg("ais.static.222", {"mmsi": "222", "name": "Ship"})
        self._one_shot_psub(service, [msg1, msg2])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        msg1.ack.assert_called_once()
        msg2.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_sent_in_live_mode(self):
        """Position messages are broadcast to WebSocket clients when replay_complete."""
        service = _make_service_for_stream(replay_complete=True)
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        self._one_shot_psub(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_called_once()
        payload = service.ws_manager.broadcast.call_args[0][0]
        assert payload["type"] == "positions"
        assert payload["positions"][0]["mmsi"] == "123456789"

    @pytest.mark.asyncio
    async def test_broadcast_not_sent_during_catchup(self):
        """Position messages are NOT broadcast when replay_complete=False."""
        service = _make_service_for_stream(replay_complete=False)
        msg = _make_mock_msg(
            "ais.position.123456789",
            {
                "mmsi": "123456789",
                "lat": 48.5,
                "lon": -123.4,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial — still catching up
                _make_consumer_info(49_000),  # post-batch — still above threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            return [msg]

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_catchup_complete_after_batch_below_threshold(self):
        """replay_complete and ready are set after a batch brings pending below threshold."""
        service = _make_service_for_stream(replay_complete=False)

        mock_psub = AsyncMock()
        # consumer_info: initial(50k), progress-log(5k, 0%10000==0), post-batch(5k)
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),
                _make_consumer_info(5_000),
                _make_consumer_info(5_000),
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            return []

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_timeout_during_catchup_marks_complete_below_threshold(self):
        """TimeoutError during catchup sets replay_complete when pending is low."""
        service = _make_service_for_stream(replay_complete=False)

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(100),  # timeout check — below threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is True
        assert service.ready is True

    @pytest.mark.asyncio
    async def test_transient_exception_inside_loop_swallowed(self):
        """A transient exception inside the main loop is swallowed and the loop retries."""
        service = _make_service_for_stream(replay_complete=True)
        call_count = 0

        async def fake_fetch(batch, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient NATS error")
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()  # must not raise

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_subscription_failure_propagates(self):
        """pull_subscribe failure propagates out of subscribe_ais_stream."""
        service = _make_service_for_stream(replay_complete=True)
        service.js = MagicMock()
        service.js.pull_subscribe = AsyncMock(
            side_effect=RuntimeError("stream not found")
        )

        with pytest.raises(RuntimeError, match="stream not found"):
            await service.subscribe_ais_stream()

    @pytest.mark.asyncio
    async def test_catchup_mode_uses_large_batch_size(self):
        """During catchup, fetch is called with batch=10000."""
        service = _make_service_for_stream(replay_complete=False)
        captured: list[int] = []

        async def fake_fetch(batch, timeout):
            captured.append(batch)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),
                _make_consumer_info(50_000),
            ]
        )
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured == [10_000]

    @pytest.mark.asyncio
    async def test_live_mode_uses_small_batch_size(self):
        """During live mode, fetch is called with batch=100."""
        service = _make_service_for_stream(replay_complete=True)
        captured: list[int] = []

        async def fake_fetch(batch, timeout):
            captured.append(batch)
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert captured == [100]

    @pytest.mark.asyncio
    async def test_broadcast_deduplicates_by_mmsi_keeps_latest(self):
        """Multiple positions for same MMSI: only the last one is broadcast."""
        service = _make_service_for_stream(replay_complete=True)
        msgs = [
            _make_mock_msg(
                "ais.position.123456789",
                {
                    "mmsi": "123456789",
                    "lat": 48.5,
                    "lon": -123.4,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_mock_msg(
                "ais.position.123456789",
                {
                    "mmsi": "123456789",
                    "lat": 48.6,
                    "lon": -123.5,
                    "timestamp": "2024-01-15T10:01:00Z",
                },
            ),
        ]
        self._one_shot_psub(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        service.ws_manager.broadcast.assert_called_once()
        payload = service.ws_manager.broadcast.call_args[0][0]
        assert len(payload["positions"]) == 1
        assert payload["positions"][0]["lat"] == 48.6
