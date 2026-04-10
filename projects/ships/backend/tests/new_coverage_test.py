"""
New coverage tests for Ships API backend.

Tests cover gaps not addressed by existing test files:

1. get_vessel() HTTP 404 bug — documents current (broken) behavior where
   FastAPI returns HTTP 200 with a list payload instead of 404, because the
   handler returns a bare tuple rather than raising HTTPException.

2. ShipsAPIService.start() — verifies it wires up DB, NATS, tasks, and flags.

3. cleanup_old_positions() multi-batch path — exercises the while-True loop
   continuation when deleted == batch_size.

4. _load_position_cache() with pre-populated DB — verifies cache is rebuilt
   from existing rows when connect() is called on a non-empty database.

5. connect_nats() failure path — verifies exception propagates when NATS is
   unavailable.

6. subscribe_ais_stream() batch processing — verifies DB writes, acks, and
   WS broadcast are all invoked for a replay-complete service receiving
   position messages.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.backend.main import Database, ShipsAPIService


# ---------------------------------------------------------------------------
# 1. get_vessel() HTTP 404 bug
# ---------------------------------------------------------------------------


class TestGetVesselHttp404Bug:
    """Documents the FastAPI tuple-return bug in the get_vessel endpoint.

    The handler currently does:
        return {"error": "Vessel not found"}, 404
    FastAPI ignores the integer status code and serialises the whole tuple as
    a JSON array with HTTP 200.  The correct fix is to raise HTTPException(404).
    """

    @pytest.mark.asyncio
    async def test_get_vessel_missing_mmsi_returns_http_200_with_list_body(
        self, test_client
    ):
        """BUG: 404 path returns HTTP 200 with a list body instead of 404.

        This test documents the current broken behavior.  When the bug is
        fixed (by raising HTTPException(status_code=404)), this test should
        be updated to assert response.status_code == 404.

        TODO: fix get_vessel() to raise HTTPException(status_code=404) instead
        of returning a bare tuple.
        """
        response = await test_client.get("/api/vessels/000000000")
        # BUG: should be 404 but FastAPI returns 200 for bare-tuple returns
        assert response.status_code == 200
        body = response.json()
        # FastAPI serialises the tuple (dict, int) as a JSON array
        assert isinstance(body, list), (
            "Expected FastAPI to serialise the bare tuple as a list"
        )
        assert body[0].get("error") == "Vessel not found"
        assert body[1] == 404

    @pytest.mark.asyncio
    async def test_get_vessel_existing_mmsi_returns_vessel_data(
        self, test_client_with_data, multiple_vessels_data
    ):
        """Sanity-check: a found vessel still returns HTTP 200 with vessel data."""
        mmsi = multiple_vessels_data[0]["mmsi"]
        response = await test_client_with_data.get(f"/api/vessels/{mmsi}")
        assert response.status_code == 200
        data = response.json()
        assert data["mmsi"] == mmsi


# ---------------------------------------------------------------------------
# 2. ShipsAPIService.start() wiring test
# ---------------------------------------------------------------------------


class TestShipsAPIServiceStart:
    """Tests for ShipsAPIService.start() method."""

    @pytest.fixture
    def service(self):
        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, service):
        """start() sets service.running = True."""
        mock_db = AsyncMock()
        mock_db.connect = AsyncMock()
        mock_db.close = AsyncMock()
        service.db = mock_db

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "_run_subscription", AsyncMock()):
                with patch.object(service, "cleanup_loop", AsyncMock()):
                    await service.start()

        assert service.running is True
        await service.stop()

    @pytest.mark.asyncio
    async def test_start_calls_db_connect(self, service):
        """start() calls db.connect() to initialise the database."""
        mock_db = AsyncMock()
        mock_db.connect = AsyncMock()
        mock_db.close = AsyncMock()
        service.db = mock_db

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "_run_subscription", AsyncMock()):
                with patch.object(service, "cleanup_loop", AsyncMock()):
                    await service.start()

        mock_db.connect.assert_called_once()
        await service.stop()

    @pytest.mark.asyncio
    async def test_start_calls_connect_nats(self, service):
        """start() calls connect_nats() to wire up the NATS connection."""
        mock_db = AsyncMock()
        mock_db.connect = AsyncMock()
        mock_db.close = AsyncMock()
        service.db = mock_db
        connect_nats_mock = AsyncMock()

        with patch.object(service, "connect_nats", connect_nats_mock):
            with patch.object(service, "_run_subscription", AsyncMock()):
                with patch.object(service, "cleanup_loop", AsyncMock()):
                    await service.start()

        connect_nats_mock.assert_called_once()
        await service.stop()

    @pytest.mark.asyncio
    async def test_start_creates_subscription_and_cleanup_tasks(self, service):
        """start() creates asyncio tasks for both the subscription and cleanup loops."""
        mock_db = AsyncMock()
        mock_db.connect = AsyncMock()
        mock_db.close = AsyncMock()
        service.db = mock_db

        # Use long-running coroutines so tasks are still alive after start()
        async def _long():
            await asyncio.sleep(100)

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "_run_subscription", _long):
                with patch.object(service, "cleanup_loop", _long):
                    await service.start()

        assert service.subscription_task is not None
        assert service.cleanup_task is not None
        assert not service.subscription_task.done()
        assert not service.cleanup_task.done()

        await service.stop()


# ---------------------------------------------------------------------------
# 3. cleanup_old_positions() multi-batch path
# ---------------------------------------------------------------------------


class TestCleanupOldPositionsMultiBatch:
    """Tests for the batched while-True loop in cleanup_old_positions()."""

    @pytest.mark.asyncio
    async def test_cleanup_continues_when_full_batch_deleted(self):
        """Loop continues if deleted == batch_size, then stops on partial batch.

        The mock cursor reports 10000 deleted on the first call (triggering the
        continuation branch) and 5 on the second (triggering the break).
        """
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 20005

        call_count = 0
        rowcounts = [10000, 5]

        async def fake_execute(sql, params=None):
            nonlocal call_count
            cursor = MagicMock()
            cursor.rowcount = rowcounts[min(call_count, len(rowcounts) - 1)]
            call_count += 1
            return cursor

        async def fake_commit():
            pass

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = fake_commit
        db.db = mock_conn

        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            total_deleted = await db.cleanup_old_positions()

        assert total_deleted == 10005
        assert call_count == 2
        # position count decremented by total deleted
        assert db._position_count == 20005 - 10005

    @pytest.mark.asyncio
    async def test_cleanup_single_batch_when_below_batch_size(self):
        """Loop exits immediately when deleted < batch_size on the first call."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 3

        call_count = 0

        async def fake_execute(sql, params=None):
            nonlocal call_count
            cursor = MagicMock()
            cursor.rowcount = 3
            call_count += 1
            return cursor

        async def fake_commit():
            pass

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = fake_commit
        db.db = mock_conn

        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            total_deleted = await db.cleanup_old_positions()

        assert total_deleted == 3
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_nothing_to_delete(self):
        """Returns 0 and does not log when there is nothing to delete."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 0

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = 0
            return cursor

        async def fake_commit():
            pass

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = fake_commit
        db.db = mock_conn

        total_deleted = await db.cleanup_old_positions()

        assert total_deleted == 0


# ---------------------------------------------------------------------------
# 4. _load_position_cache() with pre-populated DB
# ---------------------------------------------------------------------------


class TestLoadPositionCachePrePopulated:
    """Tests for Database._load_position_cache() with existing data."""

    @pytest.mark.asyncio
    async def test_cache_loaded_from_existing_rows_on_connect(self):
        """connect() on a non-empty latest_positions table populates the cache.

        This exercises the _load_position_cache() path that iterates over rows
        from the database and creates CachedPosition entries.
        """
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cache_test.db")
            db = Database(db_path)
            await db.connect()

            now = datetime.now(timezone.utc).isoformat()
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
                (
                    {
                        "mmsi": "333333333",
                        "lat": 53.0,
                        "lon": 2.0,
                        "speed": 10.0,
                        "timestamp": now,
                    },
                    now,
                ),
            ]
            await db.insert_positions_batch(positions)
            await db.commit()

            # Verify rows are in DB before close
            assert db.get_cache_size() == 3

            await db.close()

            # Reconnect — cache must be rebuilt from the 3 rows on disk
            db2 = Database(db_path)
            await db2.connect()
            try:
                assert db2.get_cache_size() == 3

                cached = db2.get_cached_position("111111111")
                assert cached is not None
                assert cached.lat == 51.5
                assert cached.lon == -0.1

                cached2 = db2.get_cached_position("222222222")
                assert cached2 is not None
                assert cached2.speed == 0.0

                cached3 = db2.get_cached_position("333333333")
                assert cached3 is not None
            finally:
                await db2.close()

    @pytest.mark.asyncio
    async def test_cache_empty_on_fresh_memory_db(self):
        """In-memory DB starts with an empty cache after connect()."""
        db = Database(":memory:")
        await db.connect()
        try:
            assert db.get_cache_size() == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_first_seen_at_location_preserved_in_cache(self):
        """Cache entries correctly store first_seen_at_location from DB."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "first_seen_test.db")
            db = Database(db_path)
            await db.connect()

            now = datetime.now(timezone.utc).isoformat()
            first_seen = "2024-01-01T08:00:00+00:00"
            await db.insert_positions_batch(
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
            await db.commit()
            await db.close()

            db2 = Database(db_path)
            await db2.connect()
            try:
                cached = db2.get_cached_position("999888777")
                assert cached is not None
                assert cached.first_seen_at_location == first_seen
            finally:
                await db2.close()


# ---------------------------------------------------------------------------
# 5. connect_nats() failure path
# ---------------------------------------------------------------------------


class TestConnectNatsFailure:
    """Tests for connect_nats() when NATS is unavailable."""

    @pytest.mark.asyncio
    async def test_connect_nats_raises_when_nats_unavailable(self):
        """connect_nats() propagates the exception when nats.connect() fails."""
        import nats as nats_module

        service = ShipsAPIService()

        with patch.object(
            nats_module,
            "connect",
            AsyncMock(side_effect=Exception("Connection refused")),
        ):
            with pytest.raises(Exception, match="Connection refused"):
                await service.connect_nats()

        # nc should remain None since connection failed
        assert service.nc is None

    @pytest.mark.asyncio
    async def test_connect_nats_raises_on_timeout(self):
        """connect_nats() propagates asyncio.TimeoutError from nats.connect()."""
        import nats as nats_module

        service = ShipsAPIService()

        with patch.object(
            nats_module,
            "connect",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            with pytest.raises(asyncio.TimeoutError):
                await service.connect_nats()

        assert service.nc is None

    @pytest.mark.asyncio
    async def test_start_propagates_nats_failure(self):
        """start() surfaces a NATS connection error to the caller."""
        import nats as nats_module

        service = ShipsAPIService()
        service.db = AsyncMock()
        service.db.connect = AsyncMock()
        service.db.close = AsyncMock()

        with patch.object(
            nats_module,
            "connect",
            AsyncMock(side_effect=Exception("NATS unavailable")),
        ):
            with pytest.raises(Exception, match="NATS unavailable"):
                await service.start()


# ---------------------------------------------------------------------------
# 6. subscribe_ais_stream() batch processing
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamBatchProcessing:
    """Tests for the data-processing loop inside subscribe_ais_stream()."""

    @pytest.mark.asyncio
    async def test_position_batch_written_to_db_and_acked(self):
        """Position messages are inserted into DB and all acked after a batch."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        # Real in-memory DB so insert_positions_batch / commit work
        db = Database(":memory:")
        await db.connect()
        service.db = db

        # Build one position message
        pos_data = {
            "mmsi": "123456789",
            "lat": 51.5,
            "lon": -0.1,
            "speed": 5.0,
            "course": 90.0,
            "heading": 88,
            "nav_status": 0,
            "rate_of_turn": 0,
            "position_accuracy": 1,
            "ship_name": "TEST",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Mock NATS message
        mock_msg = AsyncMock()
        mock_msg.subject = "ais.position.123456789"
        mock_msg.data = json.dumps(pos_data).encode()
        mock_msg.ack = AsyncMock()

        # Subscription: first fetch returns one message, second raises TimeoutError
        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(side_effect=[[mock_msg], asyncio.TimeoutError()])
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        # Run one pass through the loop then stop
        async def stop_after_timeout():
            service.running = False

        original_timeout_check = service.running

        # Run subscribe_ais_stream in a task, stop it after a brief moment
        task = asyncio.create_task(service.subscribe_ais_stream())
        # Let the task process one batch
        await asyncio.sleep(0.05)
        service.running = False
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Verify message was acked
        mock_msg.ack.assert_called_once()

        # Verify position was written to DB
        cursor = await db.db.execute("SELECT COUNT(*) FROM positions")
        row = await cursor.fetchone()
        assert row[0] >= 1

        await db.close()

    @pytest.mark.asyncio
    async def test_ws_broadcast_sent_after_replay_complete(self):
        """Positions are broadcast to WebSocket clients when replay_complete=True."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        db = Database(":memory:")
        await db.connect()
        service.db = db

        # Mock WS manager broadcast
        service.ws_manager.broadcast = AsyncMock()

        pos_data = {
            "mmsi": "777777777",
            "lat": 48.5,
            "lon": 2.3,
            "speed": 8.0,
            "course": 180.0,
            "heading": 178,
            "nav_status": 0,
            "rate_of_turn": 0,
            "position_accuracy": 1,
            "ship_name": "BROADCAST TEST",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        mock_msg = AsyncMock()
        mock_msg.subject = "ais.position.777777777"
        mock_msg.data = json.dumps(pos_data).encode()
        mock_msg.ack = AsyncMock()

        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(side_effect=[[mock_msg], asyncio.TimeoutError()])
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        task = asyncio.create_task(service.subscribe_ais_stream())
        await asyncio.sleep(0.05)
        service.running = False
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # broadcast should have been called at least once with a "positions" message
        assert service.ws_manager.broadcast.call_count >= 1
        call_args = service.ws_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "positions"
        assert any(p["mmsi"] == "777777777" for p in call_args["positions"])

        await db.close()

    @pytest.mark.asyncio
    async def test_vessel_static_message_upserted_to_db(self):
        """Static/vessel messages are upserted into the vessels table."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        db = Database(":memory:")
        await db.connect()
        service.db = db

        vessel_data = {
            "mmsi": "555444333",
            "imo": "IMO9999999",
            "call_sign": "TEST1",
            "name": "MY VESSEL",
            "ship_type": 70,
            "destination": "PORTSMOUTH",
            "eta": "2025-06-01T12:00:00Z",
            "draught": 6.5,
        }

        mock_msg = AsyncMock()
        mock_msg.subject = "ais.static.555444333"
        mock_msg.data = json.dumps(vessel_data).encode()
        mock_msg.ack = AsyncMock()

        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(side_effect=[[mock_msg], asyncio.TimeoutError()])
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        task = asyncio.create_task(service.subscribe_ais_stream())
        await asyncio.sleep(0.05)
        service.running = False
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        mock_msg.ack.assert_called_once()

        cursor = await db.db.execute(
            "SELECT name FROM vessels WHERE mmsi = ?", ("555444333",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "MY VESSEL"

        await db.close()
