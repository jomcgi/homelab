"""
Tests for Ships API database operations.

Tests cover:
- Database initialization and schema
- Position insertion and deduplication
- Vessel metadata upsert
- Track retrieval
- Position cleanup
- In-memory cache operations
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from projects.ships.backend.main import (
    CachedPosition,
    Database,
    DEDUP_DISTANCE_METERS,
    DEDUP_SPEED_THRESHOLD,
    DEDUP_TIME_THRESHOLD,
    haversine_distance,
)


class TestHaversineDistance:
    """Tests for haversine distance calculation."""

    def test_same_point_returns_zero(self):
        """Same coordinates return zero distance."""
        distance = haversine_distance(51.5074, -0.1278, 51.5074, -0.1278)
        assert distance == pytest.approx(0, abs=0.01)

    def test_known_distance(self):
        """Test with known distance between points."""
        # London to Paris is approximately 343 km
        london_lat, london_lon = 51.5074, -0.1278
        paris_lat, paris_lon = 48.8566, 2.3522
        distance = haversine_distance(london_lat, london_lon, paris_lat, paris_lon)
        # Allow 5% tolerance
        assert distance == pytest.approx(343_000, rel=0.05)

    def test_short_distance(self):
        """Test short distances (meters)."""
        # Two points approximately 100 meters apart
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.5083, -0.1278  # About 100m north
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        assert 90 < distance < 110  # Allow some tolerance

    def test_crossing_prime_meridian(self):
        """Test distance calculation crossing prime meridian."""
        # Points on either side of prime meridian
        distance = haversine_distance(51.5, -0.1, 51.5, 0.1)
        assert distance > 0

    def test_crossing_equator(self):
        """Test distance calculation crossing equator."""
        distance = haversine_distance(-1.0, 0.0, 1.0, 0.0)
        assert distance > 0


class TestDatabaseConnection:
    """Tests for database connection and initialization."""

    @pytest.mark.asyncio
    async def test_database_creates_tables(self, test_db: Database):
        """Database creates required tables on connect."""
        # Query sqlite_master to verify tables exist
        cursor = await test_db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        assert "vessels" in tables
        assert "positions" in tables
        assert "latest_positions" in tables

    @pytest.mark.asyncio
    async def test_database_creates_indexes(self, test_db: Database):
        """Database creates required indexes."""
        cursor = await test_db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

        assert "idx_positions_mmsi_timestamp" in indexes
        assert "idx_positions_timestamp" in indexes

    @pytest.mark.asyncio
    async def test_database_wal_mode(self, test_db: Database):
        """Database uses WAL journal mode."""
        cursor = await test_db.db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        # In-memory databases may not support WAL, so accept memory or wal
        assert row[0] in ("wal", "memory")


class TestPositionCache:
    """Tests for in-memory position cache."""

    @pytest.mark.asyncio
    async def test_cache_initially_empty(self, test_db: Database):
        """Cache starts empty with fresh database."""
        assert test_db.get_cache_size() == 0

    @pytest.mark.asyncio
    async def test_get_cached_position_not_found(self, test_db: Database):
        """Returns None for unknown MMSI."""
        result = test_db.get_cached_position("999999999")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_cache(self, test_db: Database, sample_position_data: dict):
        """update_cache stores position in memory."""
        mmsi = sample_position_data["mmsi"]
        first_seen = sample_position_data["timestamp"]

        test_db.update_cache(mmsi, sample_position_data, first_seen)

        cached = test_db.get_cached_position(mmsi)
        assert cached is not None
        assert cached.lat == sample_position_data["lat"]
        assert cached.lon == sample_position_data["lon"]
        assert cached.speed == sample_position_data["speed"]
        assert cached.first_seen_at_location == first_seen


class TestDeduplication:
    """Tests for position deduplication logic."""

    @pytest.mark.asyncio
    async def test_first_position_always_inserted(
        self, test_db: Database, sample_position_data: dict
    ):
        """First position for a vessel is always inserted."""
        should_insert, first_seen = test_db.should_insert_position(sample_position_data)
        assert should_insert is True
        assert first_seen == sample_position_data["timestamp"]

    @pytest.mark.asyncio
    async def test_moving_vessel_inserted(self, test_db: Database):
        """Position is inserted when vessel is moving above threshold."""
        mmsi = "123456789"
        timestamp1 = datetime.now(timezone.utc).isoformat()
        timestamp2 = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()

        # First position
        pos1 = {
            "mmsi": mmsi,
            "lat": 51.5,
            "lon": -0.1,
            "speed": 15.0,  # Above threshold
            "timestamp": timestamp1,
        }
        should_insert, first_seen = test_db.should_insert_position(pos1)
        assert should_insert is True
        test_db.update_cache(mmsi, pos1, first_seen)

        # Second position nearby, vessel moving
        pos2 = {
            "mmsi": mmsi,
            "lat": 51.5001,  # Very close
            "lon": -0.1001,
            "speed": 15.0,  # Still moving
            "timestamp": timestamp2,
        }
        should_insert, _ = test_db.should_insert_position(pos2)
        assert should_insert is True

    @pytest.mark.asyncio
    async def test_stationary_vessel_nearby_deduplicated(self, test_db: Database):
        """Nearby position is deduplicated for stationary vessel."""
        mmsi = "123456789"
        timestamp1 = datetime.now(timezone.utc).isoformat()
        timestamp2 = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()

        # First position
        pos1 = {
            "mmsi": mmsi,
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,  # Stationary
            "timestamp": timestamp1,
        }
        should_insert, first_seen = test_db.should_insert_position(pos1)
        test_db.update_cache(mmsi, pos1, first_seen)

        # Second position very close, still stationary, within time threshold
        pos2 = {
            "mmsi": mmsi,
            "lat": 51.500001,  # Within DEDUP_DISTANCE_METERS
            "lon": -0.100001,
            "speed": 0.1,  # Below DEDUP_SPEED_THRESHOLD
            "timestamp": timestamp2,
        }
        should_insert, _ = test_db.should_insert_position(pos2)
        assert should_insert is False

    @pytest.mark.asyncio
    async def test_position_inserted_after_time_threshold(self, test_db: Database):
        """Position is inserted after time threshold even if stationary."""
        mmsi = "123456789"
        now = datetime.now(timezone.utc)
        timestamp1 = now.isoformat()
        # Exceed DEDUP_TIME_THRESHOLD (default 300 seconds)
        timestamp2 = (now + timedelta(seconds=DEDUP_TIME_THRESHOLD + 10)).isoformat()

        # First position
        pos1 = {
            "mmsi": mmsi,
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": timestamp1,
        }
        should_insert, first_seen = test_db.should_insert_position(pos1)
        test_db.update_cache(mmsi, pos1, first_seen)

        # Second position at same location but after time threshold
        pos2 = {
            "mmsi": mmsi,
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": timestamp2,
        }
        should_insert, _ = test_db.should_insert_position(pos2)
        assert should_insert is True

    @pytest.mark.asyncio
    async def test_position_inserted_after_distance_threshold(self, test_db: Database):
        """Position is inserted after moving beyond distance threshold."""
        mmsi = "123456789"
        timestamp1 = datetime.now(timezone.utc).isoformat()
        timestamp2 = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()

        # First position
        pos1 = {
            "mmsi": mmsi,
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": timestamp1,
        }
        should_insert, first_seen = test_db.should_insert_position(pos1)
        test_db.update_cache(mmsi, pos1, first_seen)

        # Second position significantly moved (more than DEDUP_DISTANCE_METERS)
        pos2 = {
            "mmsi": mmsi,
            "lat": 51.6,  # ~11km away
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": timestamp2,
        }
        should_insert, _ = test_db.should_insert_position(pos2)
        assert should_insert is True


class TestPositionInsertion:
    """Tests for position batch insertion."""

    @pytest.mark.asyncio
    async def test_insert_positions_batch(
        self, test_db: Database, sample_position_data: dict
    ):
        """Batch insert positions into database."""
        positions = [(sample_position_data, sample_position_data["timestamp"])]
        count = await test_db.insert_positions_batch(positions)
        await test_db.commit()

        assert count == 1

        # Verify in positions table
        cursor = await test_db.db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        assert row[0] == 1

        # Verify in latest_positions table
        cursor = await test_db.db.execute("SELECT COUNT(*) FROM latest_positions")
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_insert_updates_cache(
        self, test_db: Database, sample_position_data: dict
    ):
        """Insert updates in-memory cache."""
        mmsi = sample_position_data["mmsi"]
        positions = [(sample_position_data, sample_position_data["timestamp"])]

        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        cached = test_db.get_cached_position(mmsi)
        assert cached is not None
        assert cached.lat == sample_position_data["lat"]

    @pytest.mark.asyncio
    async def test_insert_multiple_positions(
        self, test_db: Database, multiple_vessels_data: list[dict]
    ):
        """Insert multiple positions in one batch."""
        positions = [(v, v["timestamp"]) for v in multiple_vessels_data]
        count = await test_db.insert_positions_batch(positions)
        await test_db.commit()

        assert count == len(multiple_vessels_data)
        assert test_db.get_cache_size() == len(multiple_vessels_data)


class TestVesselUpsert:
    """Tests for vessel metadata upsert."""

    @pytest.mark.asyncio
    async def test_upsert_vessel(self, test_db: Database, sample_vessel_data: dict):
        """Insert new vessel metadata."""
        await test_db.upsert_vessels_batch([sample_vessel_data])
        await test_db.commit()

        cursor = await test_db.db.execute(
            "SELECT * FROM vessels WHERE mmsi = ?", (sample_vessel_data["mmsi"],)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == sample_vessel_data["name"]
        assert row["imo"] == sample_vessel_data["imo"]

    @pytest.mark.asyncio
    async def test_upsert_vessel_update(
        self, test_db: Database, sample_vessel_data: dict
    ):
        """Update existing vessel metadata."""
        await test_db.upsert_vessels_batch([sample_vessel_data])
        await test_db.commit()

        # Update with new destination
        updated = sample_vessel_data.copy()
        updated["destination"] = "ROTTERDAM"
        await test_db.upsert_vessels_batch([updated])
        await test_db.commit()

        cursor = await test_db.db.execute(
            "SELECT destination FROM vessels WHERE mmsi = ?",
            (sample_vessel_data["mmsi"],),
        )
        row = await cursor.fetchone()
        assert row["destination"] == "ROTTERDAM"

    @pytest.mark.asyncio
    async def test_upsert_preserves_existing_values(
        self, test_db: Database, sample_vessel_data: dict
    ):
        """Upsert with NULL values preserves existing data."""
        await test_db.upsert_vessels_batch([sample_vessel_data])
        await test_db.commit()

        # Update with partial data (name is None)
        partial_update = {
            "mmsi": sample_vessel_data["mmsi"],
            "destination": "AMSTERDAM",
            "name": None,  # Should preserve existing name
        }
        await test_db.upsert_vessels_batch([partial_update])
        await test_db.commit()

        cursor = await test_db.db.execute(
            "SELECT name, destination FROM vessels WHERE mmsi = ?",
            (sample_vessel_data["mmsi"],),
        )
        row = await cursor.fetchone()
        assert row["name"] == sample_vessel_data["name"]  # Preserved
        assert row["destination"] == "AMSTERDAM"  # Updated


class TestTrackRetrieval:
    """Tests for vessel track retrieval."""

    @pytest.mark.asyncio
    async def test_get_vessel_track_empty(self, test_db: Database):
        """Get track for unknown vessel returns empty list."""
        track = await test_db.get_vessel_track("999999999")
        assert track == []

    @pytest.mark.asyncio
    async def test_get_vessel_track(self, test_db: Database, track_data: list[dict]):
        """Get track returns position history in order."""
        positions = [(p, p["timestamp"]) for p in track_data]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        mmsi = track_data[0]["mmsi"]
        track = await test_db.get_vessel_track(mmsi)

        assert len(track) == len(track_data)
        # Verify ordered by timestamp ascending
        for i in range(1, len(track)):
            assert track[i]["timestamp"] >= track[i - 1]["timestamp"]

    @pytest.mark.asyncio
    async def test_get_vessel_track_with_limit(
        self, test_db: Database, track_data: list[dict]
    ):
        """Get track respects limit parameter."""
        positions = [(p, p["timestamp"]) for p in track_data]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        mmsi = track_data[0]["mmsi"]
        track = await test_db.get_vessel_track(mmsi, limit=3)

        assert len(track) == 3

    @pytest.mark.asyncio
    async def test_get_vessel_track_with_since(self, test_db: Database):
        """Get track filters by since parameter."""
        mmsi = "123456789"
        now = datetime.now(timezone.utc)

        # Create positions spanning multiple hours
        positions = []
        for i in range(10):
            ts = (now - timedelta(hours=i)).isoformat()
            positions.append(
                (
                    {
                        "mmsi": mmsi,
                        "lat": 51.5 + i * 0.01,
                        "lon": -0.1,
                        "speed": 10.0,
                        "timestamp": ts,
                    },
                    ts,
                )
            )

        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        # Get only last 3 hours
        track = await test_db.get_vessel_track(mmsi, since=timedelta(hours=3))

        # Should have positions from 0, 1, 2, 3 hours ago
        assert len(track) <= 4


class TestPositionCleanup:
    """Tests for old position cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_old_positions(self, test_db: Database):
        """Cleanup removes positions older than retention period."""
        mmsi = "123456789"
        now = datetime.now(timezone.utc)

        # Create old and recent positions
        positions = [
            # Recent position (should be kept)
            (
                {
                    "mmsi": mmsi,
                    "lat": 51.5,
                    "lon": -0.1,
                    "speed": 10.0,
                    "timestamp": now.isoformat(),
                },
                now.isoformat(),
            ),
            # Old position (should be deleted - default retention is 7 days)
            (
                {
                    "mmsi": mmsi,
                    "lat": 51.6,
                    "lon": -0.2,
                    "speed": 10.0,
                    "timestamp": (now - timedelta(days=10)).isoformat(),
                },
                (now - timedelta(days=10)).isoformat(),
            ),
        ]

        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        # Verify both inserted
        cursor = await test_db.db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        assert row[0] == 2

        # Run cleanup
        deleted = await test_db.cleanup_old_positions()

        assert deleted == 1

        # Verify only recent position remains
        cursor = await test_db.db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        assert row[0] == 1


class TestLatestPositions:
    """Tests for latest positions retrieval."""

    @pytest.mark.asyncio
    async def test_get_latest_positions(
        self, test_db: Database, multiple_vessels_data: list[dict]
    ):
        """Get latest positions returns all vessels."""
        positions = [(v, v["timestamp"]) for v in multiple_vessels_data]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        latest = await test_db.get_latest_positions()

        assert len(latest) == len(multiple_vessels_data)

    @pytest.mark.asyncio
    async def test_get_vessel_with_analytics(
        self, test_db: Database, sample_position_data: dict, sample_vessel_data: dict
    ):
        """Get vessel includes analytics like time at location."""
        # Insert vessel metadata
        await test_db.upsert_vessels_batch([sample_vessel_data])

        # Insert position with first_seen_at_location in the past
        past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        positions = [(sample_position_data, past_time)]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        vessel = await test_db.get_vessel(sample_position_data["mmsi"])

        assert vessel is not None
        assert "time_at_location_seconds" in vessel
        assert "time_at_location_hours" in vessel
        assert "is_moored" in vessel
        # Should show ~2 hours at location
        assert vessel["time_at_location_hours"] >= 1.5


class TestIndexManagement:
    """Tests for index drop/create during catchup."""

    @pytest.mark.asyncio
    async def test_drop_indexes(self, test_db: Database):
        """Drop indexes removes position indexes."""
        await test_db.drop_indexes()

        cursor = await test_db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_positions%'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

        assert len(indexes) == 0

    @pytest.mark.asyncio
    async def test_create_indexes(self, test_db: Database):
        """Create indexes after catchup."""
        await test_db.drop_indexes()
        await test_db.create_indexes()

        cursor = await test_db.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_positions%'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

        assert "idx_positions_mmsi_timestamp" in indexes
        assert "idx_positions_timestamp" in indexes


class TestCounts:
    """Tests for count queries."""

    @pytest.mark.asyncio
    async def test_get_vessel_count(
        self, test_db: Database, multiple_vessels_data: list[dict]
    ):
        """Get vessel count returns correct number."""
        positions = [(v, v["timestamp"]) for v in multiple_vessels_data]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        count = test_db.get_vessel_count()
        assert count == len(multiple_vessels_data)

    @pytest.mark.asyncio
    async def test_get_position_count(
        self, test_db: Database, multiple_vessels_data: list[dict]
    ):
        """Get position count returns correct number."""
        positions = [(v, v["timestamp"]) for v in multiple_vessels_data]
        await test_db.insert_positions_batch(positions)
        await test_db.commit()

        count = test_db.get_position_count()
        assert count == len(multiple_vessels_data)
