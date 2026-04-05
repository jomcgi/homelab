"""Tests for AISIngestService.subscribe_to_aisstream() connection lifecycle."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets.exceptions

from projects.ships.ingest.main import (
    AISIngestService,
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    RECONNECT_BACKOFF_FACTOR,
)


class AsyncIter:
    """Async iterator over a fixed sequence of items."""

    def __init__(self, items):
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockWebSocket:
    """Minimal WebSocket context-manager mock."""

    def __init__(self, messages=None, raise_on_enter=None):
        self.messages = messages or []
        self.raise_on_enter = raise_on_enter
        self.sent_messages = []

    async def __aenter__(self):
        if self.raise_on_enter:
            raise self.raise_on_enter
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, msg):
        self.sent_messages.append(msg)

    def __aiter__(self):
        return AsyncIter(self.messages)


class TestSubscribeToAisstream:
    """Tests for AISIngestService.subscribe_to_aisstream()."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_subscribe_stops_when_running_false_before_connect(self, service):
        """If running is False at loop entry, no connection attempt is made."""
        service.running = False
        mock_connect = MagicMock()

        with patch("projects.ships.ingest.main.websockets.connect", mock_connect):
            await service.subscribe_to_aisstream()

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_sends_subscription_message_on_connect(self, service):
        """After connecting, the subscription JSON is sent to the WebSocket."""
        service.running = True
        mock_ws = MockWebSocket(messages=[])

        async def fake_sleep(_):
            service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        assert len(mock_ws.sent_messages) == 1
        sent = json.loads(mock_ws.sent_messages[0])
        assert "APIKey" in sent
        assert "BoundingBoxes" in sent
        assert "FilterMessageTypes" in sent
        assert "PositionReport" in sent["FilterMessageTypes"]
        assert "ShipStaticData" in sent["FilterMessageTypes"]

    @pytest.mark.asyncio
    async def test_subscribe_sets_ready_true_after_connect(self, service):
        """self.ready becomes True once the WebSocket connection is established."""
        service.running = True
        ready_during_connect = []
        mock_ws = MockWebSocket(messages=[])

        original_send = mock_ws.send

        async def spy_send(msg):
            ready_during_connect.append(service.ready)
            await original_send(msg)

        mock_ws.send = spy_send

        async def fake_sleep(_):
            service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        # ready is set before send is called
        assert True in ready_during_connect

    @pytest.mark.asyncio
    async def test_subscribe_sets_ready_false_after_disconnect(self, service):
        """self.ready is reset to False after the WebSocket connection closes."""
        service.running = True
        mock_ws = MockWebSocket(messages=[])

        async def fake_sleep(_):
            service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        # After the loop ends (running=False), ready should be False
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_subscribe_handles_connection_closed_gracefully(self, service):
        """ConnectionClosed exception is caught and does not propagate."""
        service.running = True
        mock_ws = MockWebSocket(
            raise_on_enter=websockets.exceptions.ConnectionClosed(
                rcvd=None, sent=None
            )
        )

        async def fake_sleep(_):
            service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            # Should not raise
            await service.subscribe_to_aisstream()

    @pytest.mark.asyncio
    async def test_subscribe_reconnect_delay_increases_on_failure(self, service):
        """Reconnect delay grows by RECONNECT_BACKOFF_FACTOR on each failed attempt."""
        service.running = True
        sleep_delays = []

        connect_calls = 0

        class FailingWS:
            async def __aenter__(self):
                nonlocal connect_calls
                connect_calls += 1
                raise Exception("connection refused")

            async def __aexit__(self, *args):
                pass

        async def fake_sleep(delay):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 3:
                service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=FailingWS()
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        # Verify that delays increase monotonically
        assert len(sleep_delays) >= 2
        assert sleep_delays[1] > sleep_delays[0]
        assert sleep_delays[1] == sleep_delays[0] * RECONNECT_BACKOFF_FACTOR

    @pytest.mark.asyncio
    async def test_subscribe_reconnect_delay_resets_on_success(self, service):
        """Reconnect delay resets to INITIAL_RECONNECT_DELAY after a successful connect."""
        service.running = True
        sleep_delays = []
        connection_count = 0

        # First connection: succeed (no messages, loop exits naturally)
        # Second connection: raise to trigger the sleep path with backoff check
        class SequencedWS:
            def __init__(self):
                self.entered = False

            async def __aenter__(self):
                nonlocal connection_count
                connection_count += 1
                if connection_count == 1:
                    # Succeed on first connect, return self with no messages
                    return self
                raise Exception("fail on second attempt")

            async def __aexit__(self, *args):
                pass

            async def send(self, _msg):
                pass  # subscription message

            def __aiter__(self):
                return AsyncIter([])  # no messages → exits inner loop immediately

        async def fake_sleep(delay):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 2:
                service.running = False

        with patch(
            "projects.ships.ingest.main.websockets.connect",
            return_value=SequencedWS(),
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        # After the first (successful) connection, delay should reset to INITIAL.
        # The second reconnect sleep should use INITIAL_RECONNECT_DELAY.
        assert sleep_delays[0] == INITIAL_RECONNECT_DELAY

    @pytest.mark.asyncio
    async def test_subscribe_stops_loop_when_running_set_false(self, service):
        """Setting running=False mid-loop breaks out of the inner message loop."""
        service.running = True

        # Provide one real message that also triggers running=False
        async def side_effect_process(msg):
            service.running = False

        service.process_message = side_effect_process

        mock_ws = MockWebSocket(messages=["msg1"])

        async def fake_sleep(_):
            pass  # never called because running becomes False before reconnect check

        with patch(
            "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
        ), patch(
            "projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep
        ):
            await service.subscribe_to_aisstream()

        # Loop exited cleanly
        assert service.running is False
