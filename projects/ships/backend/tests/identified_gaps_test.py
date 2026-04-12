"""
Tests for identified coverage gaps in Ships API backend.

Covers:
1. Database.connect() _read_db path — file connection, URI mode, and PRAGMA settings
2. Database.get_vessel() error parse — ValueError/TypeError on malformed
   first_seen_at_location sets time_at_location_* and is_moored to None
3. /ready endpoint "starting" reason — 503 with reason="starting" when
   replay_complete=True but ready=False
4. upsert_vessels_batch() COALESCE — NULL-preserving behaviour for all 11
   COALESCE fields on re-upsert
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from projects.ships.backend.main import Database


# ---------------------------------------------------------------------------
# 1. Database.connect() _read_db file connection path (lines 206-214)
# ---------------------------------------------------------------------------


class TestDatabaseConnectReadDbFilePath:
    """Database.connect() opens a separate read-only file connection for
    file-backed databases (not :memory:)."""

    @pytest.mark.asyncio
    async def test_file_db_opens_separate_read_connection(self, tmp_path):
        """For a file-backed DB, _read_db is a distinct connection object."""
        db_path = str(tmp_path / "test_read_path.db")
        db = Database(db_path)
        await db.connect()
        try:
            assert db._read_db is not None
            assert db._read_db is not db.db
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_file_db_read_connection_has_mmap_pragma(self, tmp_path):
        """_read_db has PRAGMA mmap_size=268435456 (256 MB) set."""
        db_path = str(tmp_path / "test_pragma_read.db")
        db = Database(db_path)
        await db.connect()
        try:
            cursor = await db._read_db.execute("PRAGMA mmap_size")
            row = await cursor.fetchone()
            assert row[0] == 268435456
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_file_db_read_connection_has_cache_size_pragma(self, tmp_path):
        """_read_db has PRAGMA cache_size=-512000 set (negative = kibibytes)."""
        db_path = str(tmp_path / "test_pragma_cache.db")
        db = Database(db_path)
        await db.connect()
        try:
            cursor = await db._read_db.execute("PRAGMA cache_size")
            row = await cursor.fetchone()
            # Negative value means kibibytes — -512000 = 512 MB cache
            assert row[0] < 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_file_db_read_connection_row_factory_set(self, tmp_path):
        """_read_db has row_factory set so columns are accessible by name."""
        import aiosqlite

        db_path = str(tmp_path / "test_row_factory.db")
        db = Database(db_path)
        await db.connect()
        try:
            assert db._read_db.row_factory == aiosqlite.Row
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_memory_db_read_db_is_same_as_write_db(self):
        """For :memory: DB, _read_db must be the same object as self.db.

        SQLite :memory: databases are connection-scoped — a second connection
        would see a completely empty schema, so we reuse the write connection.
        """
        db = Database(":memory:")
        await db.connect()
        try:
            assert db._read_db is db.db
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_file_db_read_connection_can_see_committed_data(self, tmp_path):
        """After committing data on the write connection, _read_db can read it."""
        db_path = str(tmp_path / "test_read_sees_data.db")
        db = Database(db_path)
        await db.connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "888888888",
                            "lat": 49.0,
                            "lon": -124.0,
                            "speed": 5.0,
                            "timestamp": now,
                        },
                        now,
                    )
                ]
            )
            await db.commit()

            cursor = await db._read_db.execute(
                "SELECT COUNT(*) FROM latest_positions WHERE mmsi = ?", ("888888888",)
            )
            row = await cursor.fetchone()
            assert row[0] == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 2. Database.get_vessel() error parse (lines 570-573)
# ---------------------------------------------------------------------------


class TestGetVesselErrorParse:
    """get_vessel() sets time_at_location_* and is_moored to None when
    first_seen_at_location cannot be parsed (ValueError or TypeError)."""

    @pytest.mark.asyncio
    async def test_malformed_first_seen_returns_none_analytics(self):
        """A non-ISO-format first_seen string triggers ValueError → None fields."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            # Insert position with a malformed first_seen_at_location
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "100000001",
                            "lat": 48.5,
                            "lon": -123.4,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        "this-is-not-a-valid-timestamp",  # triggers ValueError
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("100000001")
            assert vessel is not None
            assert vessel.get("time_at_location_seconds") is None
            assert vessel.get("time_at_location_hours") is None
            assert vessel.get("is_moored") is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_none_first_seen_skips_analytics_block(self):
        """None first_seen_at_location causes the analytics block to be skipped
        entirely (no time_at_location_* keys added)."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "100000002",
                            "lat": 48.5,
                            "lon": -123.4,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        None,  # No first_seen → analytics block not entered
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("100000002")
            assert vessel is not None
            assert vessel.get("time_at_location_seconds") is None
            assert vessel.get("time_at_location_hours") is None
            assert vessel.get("is_moored") is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_garbage_string_first_seen_returns_none_analytics(self):
        """Completely garbage string triggers ValueError → None analytics fields."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "100000003",
                            "lat": 49.0,
                            "lon": -124.0,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        "not-a-date-at-all-!@#$%",
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("100000003")
            assert vessel is not None
            # All three fields must be None (ValueError path)
            assert vessel["time_at_location_seconds"] is None
            assert vessel["time_at_location_hours"] is None
            assert vessel["is_moored"] is None
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 3. /ready endpoint "starting" reason
# ---------------------------------------------------------------------------


class TestReadyEndpointStartingReason:
    """The /ready endpoint returns 503 with reason='starting' when
    replay_complete=True but ready=False simultaneously."""

    @pytest.mark.asyncio
    async def test_ready_starting_reason_503(self, test_client):
        """Returns 503 with reason='starting' when replay is done but service not ready."""
        from projects.ships.backend.main import service

        original_ready = service.ready
        original_replay = service.replay_complete

        service.ready = False
        service.replay_complete = True
        try:
            response = await test_client.get("/ready")
            assert response.status_code == 503
            body = response.json()
            assert body["status"] == "not_ready"
            assert body["reason"] == "starting"
        finally:
            service.ready = original_ready
            service.replay_complete = original_replay

    @pytest.mark.asyncio
    async def test_ready_catching_up_reason_503(self, test_client):
        """Returns 503 with reason='catching_up' when replay_complete=False."""
        from projects.ships.backend.main import service

        original_ready = service.ready
        original_replay = service.replay_complete

        service.ready = False
        service.replay_complete = False
        try:
            response = await test_client.get("/ready")
            assert response.status_code == 503
            body = response.json()
            assert body["reason"] == "catching_up"
        finally:
            service.ready = original_ready
            service.replay_complete = original_replay

    @pytest.mark.asyncio
    async def test_ready_200_when_ready(self, test_client):
        """Returns 200 with status='ready' when service is ready."""
        from projects.ships.backend.main import service

        original_ready = service.ready
        original_replay = service.replay_complete

        service.ready = True
        service.replay_complete = True
        try:
            response = await test_client.get("/ready")
            assert response.status_code == 200
            assert response.json()["status"] == "ready"
        finally:
            service.ready = original_ready
            service.replay_complete = original_replay


# ---------------------------------------------------------------------------
# 4. upsert_vessels_batch() COALESCE null-preservation for all 11 fields
# ---------------------------------------------------------------------------


class TestUpsertVesselsBatchCoalesceAllFields:
    """Verify that all 11 COALESCE fields in upsert_vessels_batch() preserve
    existing non-NULL values when the re-upsert provides NULL for each field."""

    @pytest.mark.asyncio
    async def test_all_11_coalesce_fields_preserved_on_null_reupsert(self):
        """Re-upserting with all 11 nullable fields set to None must NOT overwrite
        the values that were set in the first insert."""
        db = Database(":memory:")
        await db.connect()
        try:
            mmsi = "200000001"
            first = {
                "mmsi": mmsi,
                "imo": "IMO9999999",
                "call_sign": "CALLX",
                "name": "ORIGINAL NAME",
                "ship_type": 70,
                "dimension_a": 100,
                "dimension_b": 50,
                "dimension_c": 20,
                "dimension_d": 10,
                "destination": "ORIGINAL DEST",
                "eta": "2027-01-01T00:00:00Z",
                "draught": 9.5,
            }
            # First insert — establishes all values
            await db.upsert_vessels_batch([first])
            await db.commit()

            # Second insert — all 11 nullable fields are NULL
            null_update = {
                "mmsi": mmsi,
                "imo": None,
                "call_sign": None,
                "name": None,
                "ship_type": None,
                "dimension_a": None,
                "dimension_b": None,
                "dimension_c": None,
                "dimension_d": None,
                "destination": None,
                "eta": None,
                "draught": None,
            }
            await db.upsert_vessels_batch([null_update])
            await db.commit()

            cursor = await db.db.execute(
                """
                SELECT imo, call_sign, name, ship_type,
                       dimension_a, dimension_b, dimension_c, dimension_d,
                       destination, eta, draught
                FROM vessels WHERE mmsi = ?
                """,
                (mmsi,),
            )
            row = await cursor.fetchone()
            assert row is not None, "Vessel row must exist"

            # All 11 COALESCE fields must retain their original values
            assert row["imo"] == "IMO9999999", "imo must be preserved"
            assert row["call_sign"] == "CALLX", "call_sign must be preserved"
            assert row["name"] == "ORIGINAL NAME", "name must be preserved"
            assert row["ship_type"] == 70, "ship_type must be preserved"
            assert row["dimension_a"] == 100, "dimension_a must be preserved"
            assert row["dimension_b"] == 50, "dimension_b must be preserved"
            assert row["dimension_c"] == 20, "dimension_c must be preserved"
            assert row["dimension_d"] == 10, "dimension_d must be preserved"
            assert row["destination"] == "ORIGINAL DEST", (
                "destination must be preserved"
            )
            assert row["eta"] == "2027-01-01T00:00:00Z", "eta must be preserved"
            assert row["draught"] == pytest.approx(9.5), "draught must be preserved"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_coalesce_replaces_null_with_non_null_value(self):
        """COALESCE allows updating a previously-NULL field with a real value."""
        db = Database(":memory:")
        await db.connect()
        try:
            mmsi = "200000002"
            # First insert — all optional fields NULL
            await db.upsert_vessels_batch(
                [{"mmsi": mmsi, "name": None, "imo": None, "destination": None}]
            )
            await db.commit()

            # Second insert — provide values now
            await db.upsert_vessels_batch(
                [
                    {
                        "mmsi": mmsi,
                        "name": "NEW NAME",
                        "imo": "IMO1111111",
                        "destination": "NEW DEST",
                    }
                ]
            )
            await db.commit()

            cursor = await db.db.execute(
                "SELECT name, imo, destination FROM vessels WHERE mmsi = ?", (mmsi,)
            )
            row = await cursor.fetchone()
            assert row["name"] == "NEW NAME"
            assert row["imo"] == "IMO1111111"
            assert row["destination"] == "NEW DEST"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_coalesce_each_field_independently(self):
        """Each COALESCE field operates independently — updating one field does
        not reset others to NULL."""
        db = Database(":memory:")
        await db.connect()
        try:
            mmsi = "200000003"
            # First insert sets destination and eta
            await db.upsert_vessels_batch(
                [
                    {
                        "mmsi": mmsi,
                        "name": "ORIGINAL",
                        "destination": "PORT A",
                        "eta": "2027-06-01T12:00:00Z",
                        "draught": 8.0,
                    }
                ]
            )
            await db.commit()

            # Update only destination — name, eta, draught should be preserved
            await db.upsert_vessels_batch([{"mmsi": mmsi, "destination": "PORT B"}])
            await db.commit()

            cursor = await db.db.execute(
                "SELECT name, destination, eta, draught FROM vessels WHERE mmsi = ?",
                (mmsi,),
            )
            row = await cursor.fetchone()
            assert row["name"] == "ORIGINAL", "name preserved"
            assert row["destination"] == "PORT B", "destination updated"
            assert row["eta"] == "2027-06-01T12:00:00Z", "eta preserved"
            assert row["draught"] == pytest.approx(8.0), "draught preserved"
        finally:
            await db.close()
