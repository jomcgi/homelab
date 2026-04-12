"""
Targeted tests for three specific coverage gaps in Ships API backend.

Covers:
1. lifespan teardown under exception — service.stop() raising during shutdown
   propagates from the lifespan context manager (the finally/cleanup path).
2. Partial broadcast failure — specifically the case where the first and last
   clients succeed but a middle client fails; verifies that only the failing
   client is removed and the survivors still receive the message.
3. Cleanup-loop yielding for large datasets — verifies that asyncio.sleep(0.1)
   is called exactly N-1 times when N full batches are deleted (one yield per
   full batch continuation, not on the final partial batch).
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.backend.main import Database, WebSocketManager


# ---------------------------------------------------------------------------
# 1. lifespan teardown — stop() raises during shutdown
# ---------------------------------------------------------------------------


class TestLifespanTeardownUnderException:
    """Tests for the lifespan function's teardown path when an exception occurs.

    The lifespan implementation is:

        @asynccontextmanager
        async def lifespan(app):
            try:
                await service.start()
            except Exception as e:
                logger.error(...)
            yield
            await service.stop()   # <-- NOT in a try/except

    If service.stop() raises, the exception propagates out of the lifespan
    context manager to FastAPI, which will surface it as a server error.
    """

    @pytest.mark.asyncio
    async def test_lifespan_stop_exception_propagates(self):
        """When service.stop() raises during teardown, the exception propagates."""
        import projects.ships.backend.main as main_module

        stop_error = RuntimeError("forced stop failure")

        with patch.object(main_module.service, "start", new_callable=AsyncMock):
            with patch.object(
                main_module.service, "stop", side_effect=stop_error
            ) as mock_stop:
                with pytest.raises(RuntimeError, match="forced stop failure"):
                    async with main_module.lifespan(main_module.app):
                        pass  # startup succeeds; on exit, stop() raises

        mock_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_stop_called_even_after_startup_exception(self):
        """service.stop() is still called during teardown even when startup raised."""
        import projects.ships.backend.main as main_module

        stop_mock = AsyncMock()

        with patch.object(
            main_module.service,
            "start",
            side_effect=RuntimeError("NATS unavailable"),
        ):
            with patch.object(main_module.service, "stop", stop_mock):
                # The lifespan catches the startup exception, yields, then calls stop
                async with main_module.lifespan(main_module.app):
                    pass

        # stop() must always be called (it's outside the try/except for start)
        stop_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_stop_called_once_on_normal_exit(self):
        """service.stop() is called exactly once on a clean lifespan exit."""
        import projects.ships.backend.main as main_module

        stop_mock = AsyncMock()

        with patch.object(main_module.service, "start", new_callable=AsyncMock):
            with patch.object(main_module.service, "stop", stop_mock):
                async with main_module.lifespan(main_module.app):
                    pass

        stop_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_start_exception_caught_not_propagated(self):
        """startup exceptions are caught and swallowed by the lifespan try/except."""
        import projects.ships.backend.main as main_module

        with patch.object(
            main_module.service,
            "start",
            side_effect=Exception("connection refused"),
        ):
            with patch.object(main_module.service, "stop", new_callable=AsyncMock):
                # Should NOT raise — the startup exception is caught internally
                try:
                    async with main_module.lifespan(main_module.app):
                        pass
                except Exception as exc:
                    pytest.fail(
                        f"Startup exception should be caught, but got: {exc}"
                    )


# ---------------------------------------------------------------------------
# 2. Partial broadcast failure — first/last succeed, middle fails
# ---------------------------------------------------------------------------


class TestBroadcastPartialFailureMiddleClient:
    """Tests for WebSocketManager.broadcast() with a middle client that fails.

    The existing tests cover the case of one failing client mixed with one
    healthy client.  These tests specifically exercise the ordering: when the
    *middle* client fails, only that client is removed and the remaining clients
    (first, last) both still receive the message.
    """

    @pytest.mark.asyncio
    async def test_middle_client_fails_first_and_last_receive(self):
        """First and last clients receive the message; middle failing client is removed."""
        manager = WebSocketManager()

        first_ws = AsyncMock()
        first_ws.accept = AsyncMock()
        first_received = []
        first_ws.send_json = AsyncMock(side_effect=lambda msg: first_received.append(msg))

        middle_ws = AsyncMock()
        middle_ws.accept = AsyncMock()
        middle_ws.send_json = AsyncMock(side_effect=Exception("middle client reset"))

        last_ws = AsyncMock()
        last_ws.accept = AsyncMock()
        last_received = []
        last_ws.send_json = AsyncMock(side_effect=lambda msg: last_received.append(msg))

        await manager.connect(first_ws)
        await manager.connect(middle_ws)
        await manager.connect(last_ws)
        assert await manager.client_count() == 3

        msg = {"type": "positions", "positions": [{"mmsi": "111111111"}]}
        await manager.broadcast(msg)

        # Middle client must be removed
        assert middle_ws not in manager.active_connections
        # First and last must remain
        assert first_ws in manager.active_connections
        assert last_ws in manager.active_connections
        assert await manager.client_count() == 2

        # Both healthy clients received the message
        assert len(first_received) == 1
        assert first_received[0] == msg
        assert len(last_received) == 1
        assert last_received[0] == msg

    @pytest.mark.asyncio
    async def test_first_client_fails_remaining_receive(self):
        """When only the first client fails, all others still receive the message."""
        manager = WebSocketManager()

        failing_ws = AsyncMock()
        failing_ws.accept = AsyncMock()
        failing_ws.send_json = AsyncMock(side_effect=Exception("first gone"))

        survivors = []
        survivor_received = []
        for i in range(3):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock(
                side_effect=lambda msg, idx=i: survivor_received.append((idx, msg))
            )
            survivors.append(ws)

        await manager.connect(failing_ws)
        for ws in survivors:
            await manager.connect(ws)

        msg = {"type": "test", "data": "hello"}
        await manager.broadcast(msg)

        # Failing client removed
        assert failing_ws not in manager.active_connections
        # All survivors remain
        for ws in survivors:
            assert ws in manager.active_connections
        # All 3 survivors received the message
        assert len(survivor_received) == 3

    @pytest.mark.asyncio
    async def test_multiple_middle_clients_fail_endpoints_survive(self):
        """Multiple middle clients can fail while first and last survive."""
        manager = WebSocketManager()

        first_ws = AsyncMock()
        first_ws.accept = AsyncMock()
        first_ws.send_json = AsyncMock()

        last_ws = AsyncMock()
        last_ws.accept = AsyncMock()
        last_ws.send_json = AsyncMock()

        # Two failing middle clients
        middle_clients = []
        for _ in range(2):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock(side_effect=Exception("dead"))
            middle_clients.append(ws)

        await manager.connect(first_ws)
        for ws in middle_clients:
            await manager.connect(ws)
        await manager.connect(last_ws)

        assert await manager.client_count() == 4

        await manager.broadcast({"type": "batch"})

        assert await manager.client_count() == 2
        assert first_ws in manager.active_connections
        assert last_ws in manager.active_connections
        for ws in middle_clients:
            assert ws not in manager.active_connections

        # Both endpoints received the broadcast
        first_ws.send_json.assert_called_once()
        last_ws.send_json.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Cleanup-loop yielding for large datasets — exact sleep count
# ---------------------------------------------------------------------------


class TestCleanupLoopYieldingExactCount:
    """Tests that asyncio.sleep(0.1) is called the correct number of times.

    The cleanup loop calls asyncio.sleep(0.1) between every full-batch
    iteration (where deleted == batch_size).  On the final partial batch
    (deleted < batch_size) no sleep is called.  So for N full batches
    followed by a partial batch, asyncio.sleep(0.1) is called exactly N times.
    """

    @staticmethod
    def _make_bare_db(position_count: int) -> Database:
        """Return a Database instance without a real SQLite connection."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = position_count
        return db

    @staticmethod
    def _attach_mock_conn(db: Database, rowcounts: list[int]) -> None:
        """Attach a mock connection that returns successive rowcounts."""
        call_count = [0]

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            idx = min(call_count[0], len(rowcounts) - 1)
            cursor.rowcount = rowcounts[idx]
            call_count[0] += 1
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

    @pytest.mark.asyncio
    async def test_one_full_batch_then_partial_yields_exactly_once(self):
        """With 1 full batch + partial, asyncio.sleep(0.1) is called exactly once."""
        db = self._make_bare_db(10050)
        self._attach_mock_conn(db, rowcounts=[10000, 50])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            total = await db.cleanup_old_positions()

        assert total == 10050
        point_one_sleeps = [d for d in sleep_calls if d == 0.1]
        assert len(point_one_sleeps) == 1, (
            f"Expected exactly 1 sleep(0.1) for 1 full batch, got {point_one_sleeps}"
        )

    @pytest.mark.asyncio
    async def test_two_full_batches_then_partial_yields_exactly_twice(self):
        """With 2 full batches + partial, asyncio.sleep(0.1) is called exactly twice."""
        db = self._make_bare_db(20200)
        self._attach_mock_conn(db, rowcounts=[10000, 10000, 200])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            total = await db.cleanup_old_positions()

        assert total == 20200
        point_one_sleeps = [d for d in sleep_calls if d == 0.1]
        assert len(point_one_sleeps) == 2, (
            f"Expected exactly 2 sleep(0.1) calls for 2 full batches, "
            f"got {point_one_sleeps}"
        )

    @pytest.mark.asyncio
    async def test_no_sleep_when_only_partial_batch(self):
        """When only a partial batch is deleted (< batch_size), no sleep(0.1) occurs."""
        db = self._make_bare_db(500)
        self._attach_mock_conn(db, rowcounts=[500])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            total = await db.cleanup_old_positions()

        assert total == 500
        point_one_sleeps = [d for d in sleep_calls if d == 0.1]
        assert len(point_one_sleeps) == 0, (
            f"Expected no sleep(0.1) for partial-only batch, got {point_one_sleeps}"
        )

    @pytest.mark.asyncio
    async def test_no_sleep_when_zero_deletions(self):
        """When nothing is deleted, asyncio.sleep is never called."""
        db = self._make_bare_db(1000)
        self._attach_mock_conn(db, rowcounts=[0])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            total = await db.cleanup_old_positions()

        assert total == 0
        assert len(sleep_calls) == 0, (
            f"Expected no sleep calls when nothing deleted, got {sleep_calls}"
        )

    @pytest.mark.asyncio
    async def test_three_full_batches_then_partial_yields_exactly_three_times(self):
        """With 3 full batches + partial, asyncio.sleep(0.1) is called exactly 3 times."""
        db = self._make_bare_db(30300)
        self._attach_mock_conn(db, rowcounts=[10000, 10000, 10000, 300])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            total = await db.cleanup_old_positions()

        assert total == 30300
        point_one_sleeps = [d for d in sleep_calls if d == 0.1]
        assert len(point_one_sleeps) == 3, (
            f"Expected exactly 3 sleep(0.1) calls for 3 full batches, "
            f"got {point_one_sleeps}"
        )

    @pytest.mark.asyncio
    async def test_sleep_value_is_exactly_0_1_not_other_values(self):
        """Verify that the sleep value is exactly 0.1, not 0 or 1 or some other value."""
        db = self._make_bare_db(10005)
        self._attach_mock_conn(db, rowcounts=[10000, 5])

        sleep_calls: list[float] = []

        async def capture_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=capture_sleep):
            await db.cleanup_old_positions()

        assert 0.1 in sleep_calls, (
            f"asyncio.sleep(0.1) must be called, got sleep calls: {sleep_calls}"
        )
        # No sleep(0) or sleep(1) or sleep(3600) should be in the cleanup function
        other_sleeps = [d for d in sleep_calls if d != 0.1]
        assert len(other_sleeps) == 0, (
            f"Only sleep(0.1) expected from cleanup_old_positions, "
            f"got extra: {other_sleeps}"
        )
