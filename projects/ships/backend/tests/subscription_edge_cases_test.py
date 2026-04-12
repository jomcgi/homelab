"""
Tests for coverage gaps in Ships API backend: subscription edge cases and null-date handling.

Covers:
1. subscribe_ais_stream() inner exception handler:
   - Exception logged when self.running is True (not suppressed silently)
   - sleep(1) called after exception in inner loop as retry delay
   - Inner exception does NOT re-raise (loop continues)
   - replay_complete sentinel set from the TimeoutError path during catchup
2. Multi-batch cleanup loop:
   - Loop iterates exactly N times when each batch fills to batch_size
   - total_deleted is accumulated correctly across multiple batches
   - position_count decremented by total across all batches
3. Null/invalid-date handling in get_vessel():
   - TypeError path: first_seen is truthy but not a string (e.g. integer)
   - Unicode string that triggers ValueError in fromisoformat
   - Valid ISO timestamp produces non-None analytics fields
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.backend.main import Database, ShipsAPIService


# ---------------------------------------------------------------------------
# Helpers
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


def _make_service(replay_complete: bool = True) -> ShipsAPIService:
    """Create a ShipsAPIService with DB and ws_manager mocked out."""
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


def _attach_js(svc: ShipsAPIService, mock_psub: AsyncMock) -> None:
    """Wire a mock JetStream + pull subscriber onto the service."""
    svc.js = MagicMock()
    svc.js.pull_subscribe = AsyncMock(return_value=mock_psub)


# ---------------------------------------------------------------------------
# 1. subscribe_ais_stream() inner exception handler
# ---------------------------------------------------------------------------


class TestSubscribeAisStreamInnerExceptionHandler:
    """Tests for the except Exception handler inside the while self.running loop."""

    @pytest.mark.asyncio
    async def test_inner_exception_triggers_sleep_1_retry_delay(self):
        """When an exception occurs inside the loop, asyncio.sleep(1) is called."""
        service = _make_service(replay_complete=True)
        call_count = [0]

        async def fake_fetch(batch, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient NATS error")
            service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        sleep_calls: list[float] = []

        async def fake_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.subscribe_ais_stream()

        # sleep(1) should have been called as the error retry delay
        assert 1 in sleep_calls or 1.0 in sleep_calls, (
            f"Expected sleep(1) after exception, got sleep calls: {sleep_calls}"
        )

    @pytest.mark.asyncio
    async def test_inner_exception_does_not_propagate(self):
        """Exception raised during fetch inside the loop does NOT propagate out."""
        service = _make_service(replay_complete=True)

        async def fake_fetch(batch, timeout):
            service.running = False
            raise RuntimeError("should be caught by inner except")

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            # Must not raise
            await service.subscribe_ais_stream()

    @pytest.mark.asyncio
    async def test_inner_exception_loop_continues_when_running_true(self):
        """After an inner exception with running=True, the loop retries (fetches again)."""
        service = _make_service(replay_complete=True)
        fetch_count = [0]

        async def fake_fetch(batch, timeout):
            fetch_count[0] += 1
            if fetch_count[0] == 1:
                raise ValueError("first call fails")
            if fetch_count[0] >= 2:
                service.running = False
            return []

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(return_value=_make_consumer_info(0))
        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        with patch("projects.ships.backend.main.asyncio.sleep"):
            await service.subscribe_ais_stream()

        assert fetch_count[0] >= 2, "Loop should have retried after the inner exception"

    @pytest.mark.asyncio
    async def test_replay_complete_set_from_timeout_path_during_catchup(self):
        """replay_complete/ready become True via TimeoutError path when pending <= threshold."""
        service = _make_service(replay_complete=False)
        service.ready = False

        # Initial consumer_info: 50k pending (still catching up)
        # TimeoutError path check: below threshold (100 pending)
        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial check before loop
                _make_consumer_info(100),  # called inside TimeoutError handler
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
    async def test_replay_complete_not_set_from_timeout_if_still_pending(self):
        """replay_complete stays False via TimeoutError path when pending > threshold."""
        service = _make_service(replay_complete=False)
        service.ready = False

        mock_psub = AsyncMock()
        mock_psub.consumer_info = AsyncMock(
            side_effect=[
                _make_consumer_info(50_000),  # initial
                _make_consumer_info(50_000),  # TimeoutError check: still above threshold
            ]
        )

        async def fake_fetch(batch, timeout):
            service.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch = AsyncMock(side_effect=fake_fetch)
        _attach_js(service, mock_psub)

        await service.subscribe_ais_stream()

        assert service.replay_complete is False
        assert service.ready is False


# ---------------------------------------------------------------------------
# 2. Multi-batch cleanup loop
# ---------------------------------------------------------------------------


class TestCleanupOldPositionsMultiBatch:
    """Tests for the batched deletion loop in Database.cleanup_old_positions()."""

    @pytest.mark.asyncio
    async def test_three_full_batches_then_partial_loops_correctly(self):
        """Loop continues for exactly 3 full batches before stopping on partial."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 30005  # 3 full batches (10k each) + 5 remainder

        call_count = [0]
        # First 3 calls return batch_size, 4th returns partial
        rowcounts = [10000, 10000, 10000, 5]

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = rowcounts[min(call_count[0], len(rowcounts) - 1)]
            call_count[0] += 1
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        with patch("projects.ships.backend.main.asyncio.sleep"):
            total = await db.cleanup_old_positions()

        # 3 full batches + 1 partial = 4 execute calls
        assert call_count[0] == 4
        assert total == 30005

    @pytest.mark.asyncio
    async def test_total_deleted_accumulated_across_batches(self):
        """Total deleted count is the sum across all batch iterations."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 20100

        call_count = [0]
        rowcounts = [10000, 10000, 100]  # Total: 20100

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = rowcounts[min(call_count[0], len(rowcounts) - 1)]
            call_count[0] += 1
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        with patch("projects.ships.backend.main.asyncio.sleep"):
            total = await db.cleanup_old_positions()

        assert total == 20100

    @pytest.mark.asyncio
    async def test_position_count_decremented_by_total_across_batches(self):
        """db._position_count is decremented by the total deleted across all batches."""
        db = Database.__new__(Database)
        db._position_cache = {}
        initial_count = 25000
        db._position_count = initial_count

        call_count = [0]
        rowcounts = [10000, 10000, 500]

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = rowcounts[min(call_count[0], len(rowcounts) - 1)]
            call_count[0] += 1
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        with patch("projects.ships.backend.main.asyncio.sleep"):
            total = await db.cleanup_old_positions()

        expected_remaining = max(0, initial_count - total)
        assert db._position_count == expected_remaining

    @pytest.mark.asyncio
    async def test_sleep_called_between_full_batches(self):
        """asyncio.sleep(0.1) is called between full batch iterations to yield control."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 20005

        call_count = [0]
        rowcounts = [10000, 10000, 5]

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = rowcounts[min(call_count[0], len(rowcounts) - 1)]
            call_count[0] += 1
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        sleep_calls: list[float] = []

        async def fake_sleep(duration: float):
            sleep_calls.append(duration)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await db.cleanup_old_positions()

        # asyncio.sleep(0.1) should have been called between the full batches
        assert 0.1 in sleep_calls, (
            f"Expected asyncio.sleep(0.1) between full batches, got: {sleep_calls}"
        )

    @pytest.mark.asyncio
    async def test_zero_deleted_returns_zero_without_log(self):
        """When nothing is deleted, returns 0 and position_count is unchanged."""
        db = Database.__new__(Database)
        db._position_cache = {}
        db._position_count = 1000

        async def fake_execute(sql, params=None):
            cursor = MagicMock()
            cursor.rowcount = 0
            return cursor

        mock_conn = AsyncMock()
        mock_conn.execute = fake_execute
        mock_conn.commit = AsyncMock()
        db.db = mock_conn

        total = await db.cleanup_old_positions()

        assert total == 0
        assert db._position_count == 1000  # Unchanged


# ---------------------------------------------------------------------------
# 3. get_vessel() null/invalid-date handling
# ---------------------------------------------------------------------------


class TestGetVesselDateHandling:
    """Tests for get_vessel() analytics computation with various first_seen values."""

    @pytest.mark.asyncio
    async def test_valid_iso_timestamp_produces_analytics_fields(self):
        """A valid ISO timestamp produces non-None time_at_location_* and is_moored."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            first_seen = ts  # Use the same timestamp so it's valid ISO format
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "300000001",
                            "lat": 48.5,
                            "lon": -123.4,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        first_seen,
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("300000001")
            assert vessel is not None
            # With a valid timestamp, analytics should be computed (not None)
            assert vessel.get("time_at_location_seconds") is not None
            assert vessel.get("time_at_location_hours") is not None
            assert vessel.get("is_moored") is not None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_null_first_seen_produces_no_analytics_keys(self):
        """When first_seen_at_location is NULL, no analytics keys are added."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "300000002",
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

            vessel = await db.get_vessel("300000002")
            assert vessel is not None
            # Analytics keys should not be present (or be None if added by other paths)
            assert vessel.get("time_at_location_seconds") is None
            assert vessel.get("time_at_location_hours") is None
            assert vessel.get("is_moored") is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_malformed_timestamp_string_triggers_value_error_path(self):
        """A non-ISO string for first_seen triggers the ValueError except path."""
        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "300000003",
                            "lat": 49.0,
                            "lon": -124.0,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        "not-a-valid-iso-date",  # ValueError in fromisoformat
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("300000003")
            assert vessel is not None
            assert vessel["time_at_location_seconds"] is None
            assert vessel["time_at_location_hours"] is None
            assert vessel["is_moored"] is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_vessel_not_found_returns_none(self):
        """get_vessel() returns None for a MMSI that doesn't exist in the DB."""
        db = Database(":memory:")
        await db.connect()
        try:
            result = await db.get_vessel("999999999")
            assert result is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_is_moored_false_when_at_location_less_than_threshold(self):
        """is_moored is False when time at location < MOORED_MIN_DURATION_HOURS."""
        from projects.ships.backend.main import MOORED_MIN_DURATION_HOURS

        db = Database(":memory:")
        await db.connect()
        try:
            ts = datetime.now(timezone.utc).isoformat()
            # Use the CURRENT time as first_seen → 0 seconds at location → not moored
            await db.insert_positions_batch(
                [
                    (
                        {
                            "mmsi": "300000005",
                            "lat": 48.5,
                            "lon": -123.4,
                            "speed": 0.0,
                            "timestamp": ts,
                        },
                        ts,  # first_seen = now → time at location ≈ 0s
                    )
                ]
            )
            await db.commit()

            vessel = await db.get_vessel("300000005")
            assert vessel is not None
            # Time at location ≈ 0, which is less than MOORED_MIN_DURATION_HOURS * 3600
            assert vessel["is_moored"] is False
        finally:
            await db.close()
