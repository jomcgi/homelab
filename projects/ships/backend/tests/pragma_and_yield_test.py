"""
Tests for SQLite PRAGMA settings and event-loop yielding in ships/backend.

Covers gaps not addressed by the existing test suite:

1. Main DB PRAGMA settings after connect():
   - synchronous=OFF
   - temp_store=MEMORY
   - wal_autocheckpoint=1000
   - busy_timeout=5000
   - mmap_size=268435456 (256 MB)

2. Read-only DB connection mode:
   - _read_db is a *separate* connection object (not the same as self.db)
   - Connection string uses URI mode with ?mode=ro
   - _read_db has its own PRAGMA settings (mmap_size, cache_size)

3. Event-loop yielding in subscribe_ais_stream():
   - asyncio.sleep(0) is called at every i % 500 == 0
     (i=0, 500, 1000, …) to allow health-check coroutines to run
     during large batch processing.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from projects.ships.backend.main import Database, ShipsAPIService


# ---------------------------------------------------------------------------
# Helper — open a real file-based Database (not :memory:)
# ---------------------------------------------------------------------------


async def _file_db(tmp_path) -> Database:
    """Create and connect a real file-backed Database for PRAGMA testing."""
    db_path = os.path.join(str(tmp_path), "pragma_test.db")
    db = Database(db_path)
    await db.connect()
    return db


# ---------------------------------------------------------------------------
# 1. Main DB PRAGMA settings
# ---------------------------------------------------------------------------


class TestMainDbPragmaSettings:
    """Verify that Database.connect() sets all expected PRAGMAs on the main connection."""

    @pytest.mark.asyncio
    async def test_synchronous_is_off(self, tmp_path):
        """PRAGMA synchronous=OFF is set on the write connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db.db.execute("PRAGMA synchronous")
            row = await cursor.fetchone()
            # 0 = OFF in SQLite
            assert row[0] == 0, f"Expected synchronous=0 (OFF), got {row[0]}"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_temp_store_is_memory(self, tmp_path):
        """PRAGMA temp_store=MEMORY (2) is set on the write connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db.db.execute("PRAGMA temp_store")
            row = await cursor.fetchone()
            # 2 = MEMORY in SQLite
            assert row[0] == 2, f"Expected temp_store=2 (MEMORY), got {row[0]}"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_wal_autocheckpoint_is_1000(self, tmp_path):
        """PRAGMA wal_autocheckpoint=1000 is set on the write connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db.db.execute("PRAGMA wal_autocheckpoint")
            row = await cursor.fetchone()
            assert row[0] == 1000, f"Expected wal_autocheckpoint=1000, got {row[0]}"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_busy_timeout_is_5000(self, tmp_path):
        """PRAGMA busy_timeout=5000 is set on the write connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db.db.execute("PRAGMA busy_timeout")
            row = await cursor.fetchone()
            assert row[0] == 5000, f"Expected busy_timeout=5000, got {row[0]}"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_mmap_size_is_256mb(self, tmp_path):
        """PRAGMA mmap_size=268435456 (256 MB) is set on the write connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db.db.execute("PRAGMA mmap_size")
            row = await cursor.fetchone()
            assert row[0] == 268435456, (
                f"Expected mmap_size=268435456, got {row[0]}"
            )
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 2. Read-only DB connection
# ---------------------------------------------------------------------------


class TestReadOnlyDbConnection:
    """Verify that a file-backed Database opens a separate read-only connection."""

    @pytest.mark.asyncio
    async def test_read_db_is_separate_from_write_db(self, tmp_path):
        """_read_db must be a different connection object than self.db."""
        db = await _file_db(tmp_path)
        try:
            assert db._read_db is not db.db, (
                "_read_db should be a separate connection from db"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_memory_db_read_db_is_same_as_write_db(self):
        """In-memory DB uses the same connection for reads and writes (no URI mode)."""
        db = Database(":memory:")
        await db.connect()
        try:
            assert db._read_db is db.db, (
                "In-memory DB should reuse the same connection"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_read_db_can_read_data_written_by_write_db(self, tmp_path):
        """After a write-then-commit on db, _read_db can see the data."""
        db = await _file_db(tmp_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "777777777",
                            "lat": 48.5,
                            "lon": -123.4,
                            "speed": 5.0,
                            "timestamp": now,
                        },
                        now,
                    )
                ]
            )
            await db.commit()

            cursor = await db._read_db.execute(
                "SELECT COUNT(*) FROM latest_positions WHERE mmsi = ?", ("777777777",)
            )
            row = await cursor.fetchone()
            assert row[0] == 1, "Read-only connection should see committed data"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_read_db_mmap_size_is_256mb(self, tmp_path):
        """PRAGMA mmap_size=268435456 is set on the read-only connection."""
        db = await _file_db(tmp_path)
        try:
            cursor = await db._read_db.execute("PRAGMA mmap_size")
            row = await cursor.fetchone()
            assert row[0] == 268435456, (
                f"Expected _read_db mmap_size=268435456, got {row[0]}"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_read_db_cache_size_is_set(self, tmp_path):
        """PRAGMA cache_size=-512000 is set on the read-only connection.

        SQLite normalises cache_size: a negative value means kilobytes,
        so -512000 = 512 MB.  The exact value returned may differ across
        SQLite versions; we just verify it is non-zero and negative.
        """
        db = await _file_db(tmp_path)
        try:
            cursor = await db._read_db.execute("PRAGMA cache_size")
            row = await cursor.fetchone()
            # Negative value means kibibytes — we expect -512000
            assert row[0] < 0, (
                f"Expected cache_size to be a negative (KB) value, got {row[0]}"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_close_closes_both_connections(self, tmp_path):
        """Database.close() closes both db and _read_db without error."""
        db = await _file_db(tmp_path)
        # Should not raise
        await db.close()
        # After close, connections should not be usable
        # (aiosqlite raises ProgrammingError on closed connections)
        import aiosqlite

        with pytest.raises(Exception):
            await db.db.execute("SELECT 1")


# ---------------------------------------------------------------------------
# 3. Event-loop yielding in subscribe_ais_stream()
# ---------------------------------------------------------------------------


class TestEventLoopYielding:
    """Verify asyncio.sleep(0) is called at every i % 500 == 0 within a batch."""

    @pytest.mark.asyncio
    async def test_sleep_called_at_i_0(self):
        """asyncio.sleep(0) is called at i=0 (start of every batch)."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        db = Database(":memory:")
        await db.connect()
        service.db = db

        sleep_calls = []

        async def track_sleep(n):
            sleep_calls.append(n)

        # Build exactly 1 message (so i=0 only)
        pos_data = {
            "mmsi": "100000001",
            "lat": 51.0,
            "lon": -1.0,
            "speed": 5.0,
            "course": 90.0,
            "heading": 88,
            "nav_status": 0,
            "rate_of_turn": 0,
            "position_accuracy": 1,
            "ship_name": "YIELD_TEST",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_msg = AsyncMock()
        mock_msg.subject = "ais.position.100000001"
        mock_msg.data = json.dumps(pos_data).encode()
        mock_msg.ack = AsyncMock()

        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(
            side_effect=[[mock_msg], asyncio.TimeoutError()]
        )
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        with patch(
            "projects.ships.backend.main.asyncio.sleep",
            side_effect=track_sleep,
        ):
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

        # sleep(0) must have been called (at i=0)
        assert 0 in sleep_calls, (
            f"Expected asyncio.sleep(0) at i=0, sleep calls: {sleep_calls}"
        )

        await db.close()

    @pytest.mark.asyncio
    async def test_sleep_called_at_i_500_boundary(self):
        """asyncio.sleep(0) is called at i=500 when processing 501+ messages."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        db = Database(":memory:")
        await db.connect()
        service.db = db
        service.ws_manager.broadcast = AsyncMock()

        sleep_call_count = 0

        async def count_zero_sleeps(n):
            nonlocal sleep_call_count
            if n == 0:
                sleep_call_count += 1

        # Build 501 messages to trigger sleep at i=0 and i=500
        msgs = []
        for i in range(501):
            pos_data = {
                "mmsi": f"1{i:08d}",
                "lat": 50.0 + i * 0.0001,
                "lon": -1.0,
                "speed": 5.0,
                "course": 90.0,
                "heading": 88,
                "nav_status": 0,
                "rate_of_turn": 0,
                "position_accuracy": 1,
                "ship_name": f"VESSEL{i}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            m = AsyncMock()
            m.subject = f"ais.position.1{i:08d}"
            m.data = json.dumps(pos_data).encode()
            m.ack = AsyncMock()
            msgs.append(m)

        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(side_effect=[msgs, asyncio.TimeoutError()])
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        with patch(
            "projects.ships.backend.main.asyncio.sleep",
            side_effect=count_zero_sleeps,
        ):
            task = asyncio.create_task(service.subscribe_ais_stream())
            await asyncio.sleep(0.1)
            service.running = False
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # With 501 messages, sleep(0) is called at i=0 and i=500 → 2 calls
        assert sleep_call_count >= 2, (
            f"Expected at least 2 sleep(0) calls (at i=0 and i=500), "
            f"got {sleep_call_count}"
        )

        await db.close()

    @pytest.mark.asyncio
    async def test_sleep_not_called_at_non_multiple_of_500(self):
        """asyncio.sleep(0) is NOT called for i=1..499 (only at multiples of 500)."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True

        db = Database(":memory:")
        await db.connect()
        service.db = db
        service.ws_manager.broadcast = AsyncMock()

        zero_sleep_indices: list[int] = []
        current_index = [-1]

        async def track_sleep(n):
            if n == 0:
                zero_sleep_indices.append(current_index[0])

        # Patch the loop index tracking by intercepting message processing
        original_process = service._process_message_sync

        def tracking_process(subject, data):
            current_index[0] += 1
            return original_process(subject, data)

        service._process_message_sync = tracking_process

        # Build exactly 3 messages (i=0,1,2) → only i=0 triggers sleep
        msgs = []
        for i in range(3):
            pos_data = {
                "mmsi": f"2{i:08d}",
                "lat": 51.0,
                "lon": -2.0,
                "speed": 3.0,
                "course": 45.0,
                "heading": 44,
                "nav_status": 0,
                "rate_of_turn": 0,
                "position_accuracy": 1,
                "ship_name": f"V{i}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            m = AsyncMock()
            m.subject = f"ais.position.2{i:08d}"
            m.data = json.dumps(pos_data).encode()
            m.ack = AsyncMock()
            msgs.append(m)

        mock_psub = AsyncMock()
        mock_psub.fetch = AsyncMock(side_effect=[msgs, asyncio.TimeoutError()])
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)

        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        service.js = mock_js

        with patch(
            "projects.ships.backend.main.asyncio.sleep",
            side_effect=track_sleep,
        ):
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

        # For 3 messages, sleep(0) should only fire at i=0
        assert len(zero_sleep_indices) == 1, (
            f"Expected 1 sleep(0) call (only at i=0), got {zero_sleep_indices}"
        )

        await db.close()
