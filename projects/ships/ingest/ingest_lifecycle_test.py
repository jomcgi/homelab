"""
Tests for AISIngestService async lifecycle functions.

Covers:
1. AISIngestService.start() — full startup sequence
2. AISIngestService.subscribe_to_aisstream() — message handling and reconnection
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.ingest.main import AISIngestService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EmptyWebSocket:
    """WebSocket context manager that immediately returns an empty message stream."""

    def __init__(self):
        self.sent_messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, msg):
        self.sent_messages.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


# ---------------------------------------------------------------------------
# AISIngestService.start()
# ---------------------------------------------------------------------------


class TestAISIngestServiceStart:
    """Tests for AISIngestService.start() full startup sequence."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self, service):
        """start() sets self.running = True."""
        with patch.object(service, "connect_nats", AsyncMock()):
            await service.start()

        assert service.running is True
        # Cleanup
        service.running = False
        if service.ws_task:
            service.ws_task.cancel()
            try:
                await service.ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_calls_connect_nats(self, service):
        """start() calls connect_nats() to wire up the NATS connection."""
        connect_nats_mock = AsyncMock()

        with patch.object(service, "connect_nats", connect_nats_mock):
            await service.start()

        connect_nats_mock.assert_called_once()

        service.running = False
        if service.ws_task:
            service.ws_task.cancel()
            try:
                await service.ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_creates_ws_task(self, service):
        """start() creates a background asyncio task for subscribe_to_aisstream()."""
        with patch.object(service, "connect_nats", AsyncMock()):
            await service.start()

        assert service.ws_task is not None

        service.running = False
        if service.ws_task:
            service.ws_task.cancel()
            try:
                await service.ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_ws_task_is_not_done_immediately(self, service):
        """Background ws_task is still running (not done) immediately after start()."""

        async def long_running():
            await asyncio.sleep(100)

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "subscribe_to_aisstream", long_running):
                await service.start()

        assert service.ws_task is not None
        assert not service.ws_task.done()

        service.running = False
        if service.ws_task:
            service.ws_task.cancel()
            try:
                await service.ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_propagates_connect_nats_failure(self, service):
        """start() propagates exceptions from connect_nats()."""
        with patch.object(
            service,
            "connect_nats",
            AsyncMock(side_effect=Exception("NATS unavailable")),
        ):
            with pytest.raises(Exception, match="NATS unavailable"):
                await service.start()

        # ws_task should not have been created since connect_nats failed
        assert service.ws_task is None

    @pytest.mark.asyncio
    async def test_start_subscribe_runs_as_background_task(self, service):
        """subscribe_to_aisstream() is started as a background task, not awaited."""
        subscribe_called = asyncio.Event()

        async def fake_subscribe():
            subscribe_called.set()
            await asyncio.sleep(100)  # keep running

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "subscribe_to_aisstream", fake_subscribe):
                await service.start()

        # Give the event loop a moment to start the background task
        await asyncio.sleep(0.01)
        assert subscribe_called.is_set(), (
            "subscribe_to_aisstream should have been called"
        )

        service.running = False
        if service.ws_task:
            service.ws_task.cancel()
            try:
                await service.ws_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_start_followed_by_stop_is_clean(self, service):
        """Calling start() then stop() completes without errors."""

        async def long_subscribe():
            await asyncio.sleep(100)

        with patch.object(service, "connect_nats", AsyncMock()):
            with patch.object(service, "subscribe_to_aisstream", long_subscribe):
                await service.start()

        mock_nc = MagicMock()
        mock_nc.close = AsyncMock()
        service.nc = mock_nc

        # stop() should cancel the task and close the connection cleanly
        await service.stop()

        assert service.running is False
        assert service.ready is False
        mock_nc.close.assert_called_once()


# ---------------------------------------------------------------------------
# AISIngestService.subscribe_to_aisstream() — message handling
# ---------------------------------------------------------------------------


class TestSubscribeToAisstreamMessageHandling:
    """Tests for subscribe_to_aisstream() message processing and lifecycle."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_subscribe_processes_each_message(self, service):
        """Each message received from the WebSocket is passed to process_message."""
        service.running = True
        messages_processed = []

        async def fake_process(msg):
            messages_processed.append(msg)

        service.process_message = fake_process

        msg_data = '{"MessageType": "PositionReport"}'

        class _OneMessageWS:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, msg):
                self.sent_messages.append(msg)

            def __aiter__(self):
                return self

            _done = False

            async def __anext__(self):
                if not self._done:
                    self._done = True
                    return msg_data
                raise StopAsyncIteration

        mock_ws = _OneMessageWS()

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert msg_data in messages_processed

    @pytest.mark.asyncio
    async def test_subscribe_resets_ready_after_disconnect(self, service):
        """ready is set to False after a WebSocket disconnection."""
        service.running = True
        mock_ws = _EmptyWebSocket()

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect", return_value=mock_ws
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert service.ready is False

    @pytest.mark.asyncio
    async def test_subscribe_sets_ready_true_on_connection(self, service):
        """ready is set to True once the WebSocket connection is established."""
        service.running = True
        ready_values_during_send = []

        class _SpyWS:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, msg):
                ready_values_during_send.append(service.ready)
                self.sent_messages.append(msg)

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        async def fake_sleep(_):
            service.running = False

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect", return_value=_SpyWS()
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        # ready was True when the subscription message was sent
        assert True in ready_values_during_send

    @pytest.mark.asyncio
    async def test_subscribe_skips_messages_when_stopped(self, service):
        """If running is set to False mid-loop, further messages are not processed."""
        service.running = True
        processed = []

        async def fake_process(msg):
            processed.append(msg)
            service.running = False  # stop after first message

        service.process_message = fake_process

        msg1 = '{"MessageType": "PositionReport", "msg": "1"}'
        msg2 = '{"MessageType": "PositionReport", "msg": "2"}'

        class _TwoMessageWS:
            def __init__(self):
                self._items = iter([msg1, msg2])
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, msg):
                self.sent_messages.append(msg)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        with (
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_TwoMessageWS(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()),
        ):
            await service.subscribe_to_aisstream()

        # Only first message should have been processed
        assert len(processed) == 1
        assert msg1 in processed
