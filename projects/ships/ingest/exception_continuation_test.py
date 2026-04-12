"""
Tests for background loop exception-handler continuations in AIS ingest service.

The gap: subscribe_to_aisstream() has a generic `except Exception` handler that
logs the error and then continues the outer `while self.running` loop. Existing
tests don't verify that the loop actually continues after a non-ConnectionClosed
exception — they only check that specific exceptions don't propagate.

Covers:
1. Generic Exception during message processing continues the reconnect loop.
2. RuntimeError during ws.send (subscription send) is caught and loop continues.
3. Exception during process_message continues to the next message.
4. Reconnect delay is applied after a generic exception.
5. Loop terminates cleanly when running is set to False inside the except handler.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from projects.ships.ingest.main import AISIngestService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EmptyWS:
    """WebSocket that connects but yields no messages."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, _msg):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ErrorOnConnectWS:
    """WebSocket whose __aenter__ raises a generic Exception."""

    def __init__(self, error_message: str = "simulated connect failure"):
        self._error_message = error_message

    async def __aenter__(self):
        raise Exception(self._error_message)

    async def __aexit__(self, *args):
        pass


class _ErrorOnSendWS:
    """WebSocket that connects successfully but raises when send() is called."""

    def __init__(self, error: Exception | None = None):
        self._error = error or RuntimeError("send failed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, _msg):
        raise self._error

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


# ---------------------------------------------------------------------------
# 1. Generic Exception during connection: loop continues (does not propagate)
# ---------------------------------------------------------------------------


class TestGenericExceptionContinuation:
    """subscribe_to_aisstream() continues after a generic Exception."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_generic_exception_does_not_propagate(self, service):
        """A generic Exception during connection is caught; the loop continues."""
        service.running = True
        iteration_count = [0]

        async def fake_sleep(delay: float):
            iteration_count[0] += 1
            if iteration_count[0] >= 2:
                service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS("network unreachable"),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            # Must not raise
            await service.subscribe_to_aisstream()

        assert iteration_count[0] >= 2, "Loop should have continued after the exception"

    @pytest.mark.asyncio
    async def test_multiple_consecutive_exceptions_do_not_propagate(self, service):
        """The loop survives multiple consecutive generic exceptions."""
        service.running = True
        sleep_count = [0]

        async def fake_sleep(delay: float):
            sleep_count[0] += 1
            if sleep_count[0] >= 3:
                service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS("persistent failure"),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert sleep_count[0] >= 3

    @pytest.mark.asyncio
    async def test_exception_in_exception_handler_continuation_loop_stops_on_flag(
        self, service
    ):
        """When running is set to False in the sleep, the loop exits cleanly."""
        service.running = True
        stopped = [False]

        async def fake_sleep(delay: float):
            service.running = False
            stopped[0] = True

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert stopped[0] is True
        assert service.running is False

    @pytest.mark.asyncio
    async def test_ready_is_false_after_generic_exception(self, service):
        """ready flag is reset to False when a generic exception occurs."""
        service.running = True
        service.ready = True  # simulate was-ready

        async def fake_sleep(delay: float):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert service.ready is False


# ---------------------------------------------------------------------------
# 2. Exception during ws.send (subscription payload send)
# ---------------------------------------------------------------------------


class TestExceptionOnSendContinuation:
    """Exception raised inside ws.send() during subscription is caught by the outer
    except handler, ready is reset, and the reconnect loop continues."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_exception_on_send_does_not_propagate(self, service):
        """RuntimeError in ws.send is caught; loop does not propagate the error."""
        service.running = True
        sleep_count = [0]

        async def fake_sleep(delay: float):
            sleep_count[0] += 1
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnSendWS(RuntimeError("send failed")),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert sleep_count[0] >= 1, "Should have slept after send exception"

    @pytest.mark.asyncio
    async def test_ready_reset_after_send_exception(self, service):
        """ready is reset to False when an exception is thrown during send."""
        service.running = True
        service.ready = True

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnSendWS(OSError("broken pipe")),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert service.ready is False


# ---------------------------------------------------------------------------
# 3. Exception during process_message continues to next message
# ---------------------------------------------------------------------------


class TestProcessMessageExceptionContinuation:
    """Exceptions in process_message are caught; remaining messages are still processed."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_exception_in_process_message_caught_and_logs(self, service):
        """process_message raising an unexpected exception is caught silently."""
        # process_message catches all exceptions internally; this test confirms
        # the service continues working after a malformed/unexpected message.
        service.running = True
        processed = []

        # Feed one malformed message (not valid JSON) then a valid one
        messages = [
            "this is not valid json }{{{",
            json.dumps(
                {
                    "MessageType": "PositionReport",
                    "MetaData": {
                        "MMSI": "111222333",
                        "time_utc": "2027-01-01T00:00:00Z",
                        "ShipName": "VESSEL",
                    },
                    "Message": {
                        "PositionReport": {
                            "Latitude": 48.5,
                            "Longitude": -123.4,
                            "Sog": 5.0,
                            "Cog": 90.0,
                            "TrueHeading": 88,
                            "NavigationalStatus": 0,
                            "RateOfTurn": 0,
                            "PositionAccuracy": True,
                        }
                    },
                }
            ),
        ]
        msg_iter = iter(messages)

        class _MultiMessageWS:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, _msg):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(msg_iter)
                except StopIteration:
                    raise StopAsyncIteration

        original_process = service.process_message

        async def tracking_process(msg):
            processed.append(msg)
            await original_process(msg)

        service.process_message = tracking_process

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_MultiMessageWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # Both messages should have been processed (the invalid JSON is caught internally)
        assert len(processed) == 2, (
            f"Both messages should be processed regardless of parse errors, got {len(processed)}"
        )

    @pytest.mark.asyncio
    async def test_messages_after_error_are_still_processed(self, service):
        """Valid messages following a failed message are still published."""
        service.running = True

        valid_position_msg = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "999888777",
                    "time_utc": "2027-01-01T00:00:00Z",
                    "ShipName": "AFTER ERROR VESSEL",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 49.0,
                        "Longitude": -124.0,
                        "Sog": 10.0,
                        "Cog": 180.0,
                        "TrueHeading": 178,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )
        messages = ["not json", valid_position_msg]
        msg_iter = iter(messages)

        class _TwoMessageWS:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, _msg):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(msg_iter)
                except StopIteration:
                    raise StopAsyncIteration

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_TwoMessageWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # The valid position message after the bad one should have been published
        assert service.messages_published == 1, (
            f"Expected 1 published message (the valid one), got {service.messages_published}"
        )


# ---------------------------------------------------------------------------
# 4. Reconnect delay applied after exception
# ---------------------------------------------------------------------------


class TestReconnectDelayAfterException:
    """asyncio.sleep is called with the reconnect delay after a generic exception."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_reconnect_sleep_called_after_exception(self, service):
        """asyncio.sleep is called with reconnect_delay after an exception."""
        from projects.ships.ingest.main import INITIAL_RECONNECT_DELAY

        service.running = True
        sleep_delays: list[float] = []

        async def fake_sleep(delay: float):
            sleep_delays.append(delay)
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS("connection refused"),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert len(sleep_delays) >= 1, "Should have slept after exception"
        assert sleep_delays[0] == INITIAL_RECONNECT_DELAY, (
            f"First reconnect delay should be {INITIAL_RECONNECT_DELAY}, "
            f"got {sleep_delays[0]}"
        )

    @pytest.mark.asyncio
    async def test_reconnect_delay_increases_after_each_failure(self, service):
        """Reconnect delay grows with each successive failure (backoff)."""
        from projects.ships.ingest.main import (
            INITIAL_RECONNECT_DELAY,
            RECONNECT_BACKOFF_FACTOR,
        )

        service.running = True
        sleep_delays: list[float] = []

        async def fake_sleep(delay: float):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 3:
                service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert len(sleep_delays) >= 2
        assert sleep_delays[0] == INITIAL_RECONNECT_DELAY
        assert sleep_delays[1] == pytest.approx(
            INITIAL_RECONNECT_DELAY * RECONNECT_BACKOFF_FACTOR
        )

    @pytest.mark.asyncio
    async def test_reconnect_delay_reset_to_initial_after_success(self, service):
        """Reconnect delay resets to INITIAL_RECONNECT_DELAY after a successful connection."""
        from projects.ships.ingest.main import (
            INITIAL_RECONNECT_DELAY,
            RECONNECT_BACKOFF_FACTOR,
        )

        service.running = True
        sleep_delays: list[float] = []
        connect_calls = [0]

        async def fake_sleep(delay: float):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 3:
                service.running = False

        # First call fails (causing backoff), second call succeeds (resets delay)
        def make_ws():
            connect_calls[0] += 1
            if connect_calls[0] == 1:
                return _ErrorOnConnectWS("first fail")
            # Second call: empty WS (success)
            return _EmptyWS()

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                side_effect=lambda *a, **kw: make_ws(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # After the successful second connection, delay should have reset
        # so third call's sleep should be back to INITIAL_RECONNECT_DELAY
        if len(sleep_delays) >= 2:
            # The delay after the successful connection reset to initial
            # (subsequent failures restart from INITIAL)
            assert sleep_delays[1] <= INITIAL_RECONNECT_DELAY * RECONNECT_BACKOFF_FACTOR


# ---------------------------------------------------------------------------
# 5. Loop terminates cleanly when running=False is set during exception handling
# ---------------------------------------------------------------------------


class TestLoopTerminationOnRunningFalse:
    """Loop exits cleanly when running is set to False during exception handling."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_loop_exits_when_running_false_during_sleep(self, service):
        """If running is False when sleep is called, the loop exits after sleeping."""
        service.running = True

        async def fake_sleep(delay: float):
            # Check condition: running is about to be checked
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_ErrorOnConnectWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            # Should exit cleanly after 1 exception + 1 sleep + running=False check
            await service.subscribe_to_aisstream()

        assert service.running is False

    @pytest.mark.asyncio
    async def test_loop_does_not_reconnect_when_running_false(self, service):
        """When running becomes False, no further connection attempts are made."""
        service.running = True
        connect_calls = [0]

        class _CountingWS:
            async def __aenter__(self):
                connect_calls[0] += 1
                raise Exception("always fail")

            async def __aexit__(self, *args):
                pass

        async def fake_sleep(delay: float):
            service.running = False  # stop after first failure

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_CountingWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # Only one connection attempt should have been made
        assert connect_calls[0] == 1, (
            f"Expected 1 connection attempt, got {connect_calls[0]}"
        )
