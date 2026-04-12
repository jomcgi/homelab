"""
Final coverage tests for Ships API backend.

Targets genuine gaps not covered by the 12 existing test files:

1. _process_message_sync() — JSON decode error, missing mmsi, unknown subject,
   static message path, deduplicated path
2. upsert_vessels_batch() — direct batch vessel insert and COALESCE upsert
3. cleanup_old_positions() — zero-deletion path (nothing to clean)
4. get_vessel() — first_seen_at_location=None path (no analytics fields)
5. get_vessel_track() — with 'since' timedelta filtering
6. WebSocketManager.broadcast() — partial failure: one client fails, rest succeed
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from projects.ships.backend.main import Database, ShipsAPIService, WebSocketManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bare_db():
    """Return a Database instance without a real SQLite connection."""
    db = Database.__new__(Database)
    db._position_cache = {}
    db._position_count = 0
    return db


def _make_service_with_db():
    """Create a ShipsAPIService with a bare (no-SQL) db."""
    svc = ShipsAPIService()
    svc.db = _make_bare_db()
    return svc


# ---------------------------------------------------------------------------
# 1. _process_message_sync() — message routing and error paths
# ---------------------------------------------------------------------------


class TestProcessMessageSync:
    """Unit tests for ShipsAPIService._process_message_sync()."""

    def setup_method(self):
        self.svc = _make_service_with_db()

    def test_invalid_json_returns_none(self):
        """Malformed JSON payload returns None without raising."""
        result = self.svc._process_message_sync("ais.position.123", b"not-json{{{")
        assert result is None

    def test_missing_mmsi_returns_none(self):
        """Position message without 'mmsi' field is silently dropped."""
        payload = json.dumps({"lat": 48.5, "lon": -123.4, "speed": 5.0}).encode()
        result = self.svc._process_message_sync("ais.position.123", payload)
        assert result is None

    def test_unknown_subject_returns_none(self):
        """Messages on unrecognised subjects (not ais.position.* or ais.static.*) are dropped."""
        payload = json.dumps({"mmsi": "123456789", "lat": 1.0, "lon": 2.0}).encode()
        result = self.svc._process_message_sync("ais.unknown.123", payload)
        assert result is None

    def test_static_message_returns_vessel_tuple(self):
        """ais.static.* subject returns ('vessel', data, None)."""
        data = {
            "mmsi": "123456789",
            "name": "TEST SHIP",
            "ship_type": 70,
            "imo": "IMO1234567",
        }
        result = self.svc._process_message_sync(
            "ais.static.123456789", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, returned_data, first_seen = result
        assert msg_type == "vessel"
        assert returned_data["mmsi"] == "123456789"
        assert first_seen is None

    def test_position_message_first_time_returns_position_tuple(self):
        """First position for a vessel returns ('position', data, timestamp)."""
        ts = datetime.now(timezone.utc).isoformat()
        data = {
            "mmsi": "999000001",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 8.0,
            "timestamp": ts,
        }
        result = self.svc._process_message_sync(
            "ais.position.999000001", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, returned_data, first_seen = result
        assert msg_type == "position"
        assert returned_data["mmsi"] == "999000001"
        assert first_seen == ts  # first position, first_seen = timestamp

    def test_deduplicated_position_returns_deduplicated_tuple(self):
        """Second identical position returns ('deduplicated', {}, None)."""
        from projects.ships.backend.main import CachedPosition

        ts = "2024-06-01T10:00:00+00:00"  # nosemgrep: test-hardcoded-past-timestamp
        # Pre-populate cache so deduplication triggers
        self.svc.db._position_cache["777777777"] = CachedPosition(
            lat=51.5,
            lon=-0.1,
            speed=0.0,
            timestamp=ts,
            first_seen_at_location=ts,
        )
        # Same position within dedup thresholds (speed=0, distance=0, time=0)
        data = {
            "mmsi": "777777777",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 0.0,
            "timestamp": ts,
        }
        result = self.svc._process_message_sync(
            "ais.position.777777777", json.dumps(data).encode()
        )
        assert result is not None
        msg_type, _, _ = result
        assert msg_type == "deduplicated"


# ---------------------------------------------------------------------------
# 2. upsert_vessels_batch() — direct test on real in-memory DB
# ---------------------------------------------------------------------------


class TestUpsertVesselsBatch:
    """Tests for Database.upsert_vessels_batch() via a real in-memory DB."""

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self):
        """Calling with an empty list does nothing and does not raise."""
        db = Database(":memory:")
        await db.connect()
        try:
            await db.upsert_vessels_batch([])
            cursor = await db.db.execute("SELECT COUNT(*) FROM vessels")
            row = await cursor.fetchone()
            assert row[0] == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_inserts_vessel_metadata(self):
        """A vessel dict is inserted into the vessels table."""
        db = Database(":memory:")
        await db.connect()
        try:
            vessel = {
                "mmsi": "123456789",
                "imo": "IMO1234567",
                "call_sign": "CALL1",
                "name": "TEST SHIP",
                "ship_type": 70,
                "dimension_a": 100,
                "dimension_b": 20,
                "dimension_c": 10,
                "dimension_d": 5,
                "destination": "LONDON",
                "eta": "2025-03-01T12:00:00Z",
                "draught": 8.0,
            }
            await db.upsert_vessels_batch([vessel])
            await db.commit()
            cursor = await db.db.execute(
                "SELECT name, imo FROM vessels WHERE mmsi = ?", ("123456789",)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "TEST SHIP"
            assert row[1] == "IMO1234567"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_upsert_coalesces_existing_name(self):
        """Re-inserting with name=None does not overwrite existing name (COALESCE)."""
        db = Database(":memory:")
        await db.connect()
        try:
            # First insert sets the name
            await db.upsert_vessels_batch([{"mmsi": "111222333", "name": "ORIGINAL"}])
            await db.commit()
            # Second insert with name=None must preserve the original
            await db.upsert_vessels_batch([{"mmsi": "111222333", "name": None}])
            await db.commit()
            cursor = await db.db.execute(
                "SELECT name FROM vessels WHERE mmsi = ?", ("111222333",)
            )
            row = await cursor.fetchone()
            assert row[0] == "ORIGINAL"
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 3. cleanup_old_positions() — zero-deletion path
# ---------------------------------------------------------------------------


class TestCleanupOldPositionsZeroDeletion:
    """cleanup_old_positions() returns 0 when there is nothing to delete."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_old_positions(self):
        """With only recent positions, cleanup deletes nothing and returns 0."""
        db = Database(":memory:")
        await db.connect()
        try:
            # Insert a position with a current timestamp (within retention window)
            ts = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "123000001",
                            "lat": 51.5,
                            "lon": -0.1,
                            "speed": 5.0,
                            "timestamp": ts,
                        },
                        ts,
                    )
                ]
            )
            await db.commit()
            deleted = await db.cleanup_old_positions()
            assert deleted == 0
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 4. get_vessel() — first_seen_at_location=None skips analytics
# ---------------------------------------------------------------------------


class TestGetVesselNoFirstSeen:
    """get_vessel() omits mooring analytics when first_seen_at_location is NULL."""

    @pytest.mark.asyncio
    async def test_vessel_without_first_seen_has_no_analytics(self):
        """When first_seen_at_location is NULL, analytics fields are absent."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            # Insert with first_seen=None (passes NULL to DB)
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "555000001",
                            "lat": 51.0,
                            "lon": -1.0,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        None,  # first_seen_at_location = NULL
                    )
                ]
            )
            await db.commit()
            result = await db.get_vessel("555000001")
            assert result is not None
            # Analytics fields should not be present when first_seen is NULL
            assert "time_at_location_seconds" not in result
            assert "time_at_location_hours" not in result
            assert "is_moored" not in result
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 5. get_vessel_track() — with 'since' timedelta produces filtered results
# ---------------------------------------------------------------------------


class TestGetVesselTrackWithSince:
    """get_vessel_track() with a 'since' timedelta filters out old positions."""

    @pytest.mark.asyncio
    async def test_since_filters_old_positions(self):
        """Positions older than 'since' are excluded from the track."""
        db = Database(":memory:")
        await db.connect()
        try:
            now = datetime.now(timezone.utc)
            mmsi = "444000001"
            positions = [
                # Recent position (1 hour ago)
                (
                    {
                        "mmsi": mmsi,
                        "lat": 51.5,
                        "lon": -0.1,
                        "speed": 5.0,
                        "timestamp": (now - timedelta(hours=1)).isoformat(),
                    },
                    (now - timedelta(hours=1)).isoformat(),
                ),
                # Old position (48 hours ago — outside a 24h window)
                (
                    {
                        "mmsi": mmsi,
                        "lat": 51.6,
                        "lon": -0.2,
                        "speed": 5.0,
                        "timestamp": (now - timedelta(hours=48)).isoformat(),
                    },
                    (now - timedelta(hours=48)).isoformat(),
                ),
            ]
            await db.insert_positions_batch(positions)
            await db.commit()

            # Query with since=24h — should return only the recent position
            track = await db.get_vessel_track(mmsi, since=timedelta(hours=24))
            assert len(track) == 1
            # The remaining position should be the recent one
            assert track[0]["lat"] == pytest.approx(51.5)
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 6. WebSocketManager.broadcast() — partial failure: some clients fail
# ---------------------------------------------------------------------------


class TestWebSocketManagerBroadcastPartialFailure:
    """broadcast() removes only failing clients, keeps healthy ones."""

    @pytest.mark.asyncio
    async def test_healthy_client_still_receives_after_peer_fails(self):
        """When one client raises, the healthy client still receives the message."""
        manager = WebSocketManager()

        failing_ws = AsyncMock()
        failing_ws.accept = AsyncMock()
        failing_ws.send_json = AsyncMock(side_effect=Exception("peer reset"))

        healthy_ws = AsyncMock()
        healthy_ws.accept = AsyncMock()
        received = []
        healthy_ws.send_json = AsyncMock(side_effect=lambda msg: received.append(msg))

        await manager.connect(failing_ws)
        await manager.connect(healthy_ws)
        assert await manager.client_count() == 2

        msg = {"type": "positions", "positions": []}
        await manager.broadcast(msg)

        # Failing client should be removed
        assert failing_ws not in manager.active_connections
        # Healthy client should remain
        assert healthy_ws in manager.active_connections
        assert len(received) == 1
        assert received[0] == msg

    @pytest.mark.asyncio
    async def test_all_clients_removed_when_all_fail(self):
        """When every client raises, all are removed and the list is empty."""
        manager = WebSocketManager()

        for _ in range(3):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock(side_effect=Exception("gone"))
            await manager.connect(ws)

        assert await manager.client_count() == 3
        await manager.broadcast({"type": "test"})
        assert await manager.client_count() == 0
