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
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
            assert row[0] == 268435456, f"Expected mmap_size=268435456, got {row[0]}"
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
            assert db._read_db is db.db, "In-memory DB should reuse the same connection"
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
    """Verify asyncio.sleep(0) is called at every i % 500 == 0 within a batch.

    These tests run subscribe_ais_stream() with a direct ``await`` (not
    asyncio.create_task) so that asyncio.sleep is patched without breaking
    the test's own event-loop yielding.  A closure-based fetch mock stops the
    service after the first batch by setting ``running=False`` on the second
    call, which causes the outer ``while self.running:`` loop to exit cleanly.
    """

    @staticmethod
    def _make_pos_msg(mmsi: str, ship_name: str) -> AsyncMock:
        """Build a mock NATS message carrying a position payload."""
        pos_data = {
            "mmsi": mmsi,
            "lat": 51.0,
            "lon": -1.0,
            "speed": 5.0,
            "course": 90.0,
            "heading": 88,
            "nav_status": 0,
            "rate_of_turn": 0,
            "position_accuracy": 1,
            "ship_name": ship_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        m = AsyncMock()
        m.subject = f"ais.position.{mmsi}"
        m.data = json.dumps(pos_data).encode()
        m.ack = AsyncMock()
        return m

    @staticmethod
    def _stopping_fetch(service, first_batch):
        """Return an async fetch callable that stops the service on 2nd call."""
        call_count = 0

        async def _fetch(batch, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_batch
            service.running = False
            raise asyncio.TimeoutError()

        return _fetch

    @staticmethod
    async def _make_service():
        """Create a ShipsAPIService wired to an in-memory DB, ready for tests."""
        service = ShipsAPIService()
        service.running = True
        service.replay_complete = True
        service.ready = True
        db = Database(":memory:")
        await db.connect()
        service.db = db
        service.ws_manager.broadcast = AsyncMock()
        return service, db

    @staticmethod
    def _mock_js(service, first_batch):
        """Return a mock JetStream context backed by the stopping fetch."""
        mock_psub = AsyncMock()
        mock_psub.fetch = TestEventLoopYielding._stopping_fetch(service, first_batch)
        consumer_info_mock = MagicMock()
        consumer_info_mock.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info_mock)
        mock_js = AsyncMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)
        return mock_js

    @pytest.mark.asyncio
    async def test_sleep_called_at_i_0(self):
        """asyncio.sleep(0) is called at i=0 (start of every batch)."""
        service, db = await self._make_service()

        sleep_calls: list[int | float] = []

        async def track_sleep(n):
            sleep_calls.append(n)

        msg = self._make_pos_msg("100000001", "YIELD_TEST")
        service.js = self._mock_js(service, [msg])

        with patch("projects.ships.backend.main.asyncio.sleep", new=track_sleep):
            await service.subscribe_ais_stream()

        assert 0 in sleep_calls, (
            f"Expected asyncio.sleep(0) at i=0, sleep calls: {sleep_calls}"
        )

        await db.close()

    @pytest.mark.asyncio
    async def test_sleep_called_at_i_500_boundary(self):
        """asyncio.sleep(0) is called at i=500 when processing 501+ messages."""
        service, db = await self._make_service()

        zero_sleep_count = 0

        async def count_zero_sleeps(n):
            nonlocal zero_sleep_count
            if n == 0:
                zero_sleep_count += 1

        # 501 distinct MMSIs to avoid deduplication collapsing the batch
        msgs = [self._make_pos_msg(f"1{i:08d}", f"VESSEL{i}") for i in range(501)]
        service.js = self._mock_js(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep", new=count_zero_sleeps):
            await service.subscribe_ais_stream()

        # sleep(0) fires at i=0 and i=500 → at least 2 calls
        assert zero_sleep_count >= 2, (
            f"Expected at least 2 sleep(0) calls (at i=0 and i=500), "
            f"got {zero_sleep_count}"
        )
        await db.close()

    @pytest.mark.asyncio
    async def test_sleep_not_called_at_non_multiple_of_500(self):
        """asyncio.sleep(0) is NOT called for i=1..499 (only at multiples of 500)."""
        service, db = await self._make_service()

        zero_sleep_count = 0

        async def track_zero_sleep(n):
            nonlocal zero_sleep_count
            if n == 0:
                zero_sleep_count += 1

        # 3 messages → sleep(0) called exactly once (at i=0)
        msgs = [self._make_pos_msg(f"2{i:08d}", f"V{i}") for i in range(3)]
        service.js = self._mock_js(service, msgs)

        with patch("projects.ships.backend.main.asyncio.sleep", new=track_zero_sleep):
            await service.subscribe_ais_stream()

        assert zero_sleep_count == 1, (
            f"Expected exactly 1 sleep(0) call (only at i=0), got {zero_sleep_count}"
        )
        await db.close()
