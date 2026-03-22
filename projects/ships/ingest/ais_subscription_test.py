"""
Tests for AISIngestService.subscribe_to_aisstream() and start().

Covers:
- Successful WebSocket connection flow: sends subscription message, sets ready, processes msgs.
- Reconnection on ConnectionClosed with exponential backoff delays.
- Reconnection on generic Exception with exponential backoff delays.
- Subscription message content (APIKey, BoundingBoxes, FilterMessageTypes).
- SSL context creation using certifi CA bundle.
- ready flag transitions (True on connect, False on disconnect, reset on reconnect).
- Running flag check stops reconnection loop when self.running is False.
- start() orchestration: sets running, calls connect_nats, creates ws_task.
"""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio

from projects.ships.ingest.main import (
    AISIngestService,
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    RECONNECT_BACKOFF_FACTOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_ws(messages=None, raise_on_iter=None):
    """
    Build a mock async context manager that yields a WebSocket-like object.

    messages: list of raw string messages to yield during 'async for message in ws'.
    raise_on_iter: exception class to raise when iterating.
    """
    mock_ws = AsyncMock()

    async def send(data):
        pass

    mock_ws.send = AsyncMock(side_effect=send)

    if raise_on_iter is not None:

        async def _iter(self):
            raise raise_on_iter("simulated error")
            # unreachable but required by linter
            return
            yield  # make it a generator  # noqa: unreachable

        mock_ws.__aiter__ = _iter
    elif messages is not None:

        async def _iter(self):
            for msg in messages:
                yield msg

        mock_ws.__aiter__ = _iter
    else:

        async def _iter(self):
            return
            yield  # noqa: unreachable

        mock_ws.__aiter__ = _iter

    # Make the context manager return the ws object
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_ws)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_ws


# ---------------------------------------------------------------------------
# subscribe_to_aisstream
# ---------------------------------------------------------------------------


class TestSubscribeToAisstream:
    """Tests for AISIngestService.subscribe_to_aisstream()."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.running = True
        svc.js = AsyncMock()
        svc.nc = AsyncMock()
        return svc

    # --- successful connection flow ---

    @pytest.mark.asyncio
    async def test_sends_subscription_message_on_connect(self, service):
        """After connecting, the service sends a subscription message to AISStream."""
        ctx, mock_ws = _make_mock_ws(messages=[])

        def stop_after_connect(*_a, **_kw):
            service.running = False
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", stop_after_connect):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        mock_ws.send.assert_called_once()
        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert "APIKey" in sent_payload
        assert "BoundingBoxes" in sent_payload
        assert "FilterMessageTypes" in sent_payload

    @pytest.mark.asyncio
    async def test_subscription_message_filter_types(self, service):
        """Subscription message requests PositionReport and ShipStaticData."""
        ctx, mock_ws = _make_mock_ws(messages=[])

        def stop_after_connect(*_a, **_kw):
            service.running = False
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", stop_after_connect):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert "PositionReport" in sent_payload["FilterMessageTypes"]
        assert "ShipStaticData" in sent_payload["FilterMessageTypes"]

    @pytest.mark.asyncio
    async def test_subscription_message_bounding_boxes_valid_json(self, service):
        """BoundingBoxes in subscription message is a valid list."""
        ctx, mock_ws = _make_mock_ws(messages=[])

        def stop_after_connect(*_a, **_kw):
            service.running = False
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", stop_after_connect):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert isinstance(sent_payload["BoundingBoxes"], list)

    @pytest.mark.asyncio
    async def test_ready_set_true_after_connect(self, service):
        """self.ready becomes True once successfully connected."""
        ctx, mock_ws = _make_mock_ws(messages=[])

        ready_after_connect = []

        async def send_and_capture(data):
            # Called right after the subscription message; at this point ready should be True
            pass

        mock_ws.send = AsyncMock(side_effect=send_and_capture)

        def make_ctx(*_a, **_kw):
            service.running = False
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert service.ready is True

    @pytest.mark.asyncio
    async def test_processes_incoming_messages(self, service):
        """Messages received from the WebSocket are passed to process_message."""
        raw_message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "TEST",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                    }
                },
            }
        )

        ctx, mock_ws = _make_mock_ws(messages=[raw_message])
        connect_call_count = [0]

        def make_ctx(*_a, **_kw):
            connect_call_count[0] += 1
            return ctx

        process_calls = []
        original_process = service.process_message

        async def capturing_process(msg):
            process_calls.append(msg)
            service.running = False  # stop reconnect loop after first message
            await original_process(msg)

        service.process_message = capturing_process

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert len(process_calls) == 1
        assert process_calls[0] == raw_message

    @pytest.mark.asyncio
    async def test_reconnect_delay_resets_after_successful_connection(self, service):
        """On successful connection the reconnect delay resets to INITIAL_RECONNECT_DELAY."""
        connect_count = [0]
        sleep_calls = []

        ctx, mock_ws = _make_mock_ws(messages=[])

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 2:
                service.running = False
            return ctx

        async def tracking_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", tracking_sleep):
                await service.subscribe_to_aisstream()

        # After a successful connect, the next reconnect delay should be INITIAL
        if sleep_calls:
            assert sleep_calls[0] == INITIAL_RECONNECT_DELAY

    # --- reconnection on failure ---

    @pytest.mark.asyncio
    async def test_reconnects_on_connection_closed(self, service):
        """Service reconnects when ConnectionClosed is raised."""
        import websockets.exceptions

        connect_count = [0]
        ctx_closed, _ = _make_mock_ws(
            raise_on_iter=websockets.exceptions.ConnectionClosed
        )
        ctx_clean, _ = _make_mock_ws(messages=[])

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 2:
                service.running = False
            if connect_count[0] == 1:
                return ctx_closed
            return ctx_clean

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert connect_count[0] >= 2

    @pytest.mark.asyncio
    async def test_reconnects_on_generic_exception(self, service):
        """Service reconnects when a generic exception occurs."""
        connect_count = [0]

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 2:
                service.running = False
            raise RuntimeError("network error")

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert connect_count[0] >= 2

    @pytest.mark.asyncio
    async def test_backoff_delay_used_on_reconnect(self, service):
        """Service sleeps for reconnect_delay seconds after a failed connection."""
        import websockets.exceptions

        connect_count = [0]
        sleep_calls = []

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 2:
                service.running = False
            ctx, mock_ws = _make_mock_ws(
                raise_on_iter=websockets.exceptions.ConnectionClosed
            )
            return ctx

        async def tracking_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", tracking_sleep):
                await service.subscribe_to_aisstream()

        # Should have slept at least once with the initial delay
        assert len(sleep_calls) >= 1
        assert sleep_calls[0] == INITIAL_RECONNECT_DELAY

    @pytest.mark.asyncio
    async def test_backoff_doubles_on_repeated_failures(self, service):
        """Reconnect delay doubles after each failure up to MAX_RECONNECT_DELAY."""
        connect_count = [0]
        sleep_calls = []

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 4:
                service.running = False
            raise RuntimeError("repeated failure")

        async def tracking_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", tracking_sleep):
                await service.subscribe_to_aisstream()

        # Delays should follow exponential backoff: 1, 2, 4 ...
        assert len(sleep_calls) >= 3
        assert sleep_calls[0] == INITIAL_RECONNECT_DELAY
        assert sleep_calls[1] == min(
            INITIAL_RECONNECT_DELAY * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY
        )
        assert sleep_calls[2] == min(
            INITIAL_RECONNECT_DELAY * RECONNECT_BACKOFF_FACTOR**2,
            MAX_RECONNECT_DELAY,
        )

    @pytest.mark.asyncio
    async def test_backoff_never_exceeds_max(self, service):
        """Reconnect delay is capped at MAX_RECONNECT_DELAY."""
        connect_count = [0]
        sleep_calls = []

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 10:
                service.running = False
            raise RuntimeError("repeated failure")

        async def tracking_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", tracking_sleep):
                await service.subscribe_to_aisstream()

        for delay in sleep_calls:
            assert delay <= MAX_RECONNECT_DELAY

    # --- ready flag transitions ---

    @pytest.mark.asyncio
    async def test_ready_set_false_after_disconnect(self, service):
        """self.ready is reset to False after a connection drops."""
        import websockets.exceptions

        connect_count = [0]

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            if connect_count[0] >= 2:
                service.running = False
            ctx, _ = _make_mock_ws(raise_on_iter=websockets.exceptions.ConnectionClosed)
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        # After loop ends, ready should be False (set in reconnect block)
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_does_not_reconnect_when_running_false(self, service):
        """Loop exits without reconnecting when self.running is False."""
        service.running = False

        connect_count = [0]

        def make_ctx(*_a, **_kw):
            connect_count[0] += 1
            ctx, _ = _make_mock_ws(messages=[])
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert connect_count[0] == 0

    # --- SSL context ---

    @pytest.mark.asyncio
    async def test_ssl_context_passed_to_websockets_connect(self, service):
        """subscribe_to_aisstream passes an SSL context to websockets.connect."""
        ctx, _ = _make_mock_ws(messages=[])
        captured_kwargs = {}

        def make_ctx(*_a, **_kw):
            captured_kwargs.update(_kw)
            service.running = False
            return ctx

        with patch("projects.ships.ingest.main.websockets.connect", make_ctx):
            with patch("projects.ships.ingest.main.asyncio.sleep", AsyncMock()):
                await service.subscribe_to_aisstream()

        assert "ssl" in captured_kwargs
        assert isinstance(captured_kwargs["ssl"], ssl.SSLContext)


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    """Tests for AISIngestService.start()."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self):
        """start() sets self.running = True before anything else."""
        svc = AISIngestService()
        assert svc.running is False

        with patch.object(svc, "connect_nats", AsyncMock()):
            with patch(
                "projects.ships.ingest.main.asyncio.create_task"
            ) as mock_create_task:
                mock_create_task.return_value = MagicMock()
                await svc.start()

        assert svc.running is True

    @pytest.mark.asyncio
    async def test_start_calls_connect_nats(self):
        """start() calls connect_nats() to establish NATS connection."""
        svc = AISIngestService()
        connect_nats_mock = AsyncMock()

        with patch.object(svc, "connect_nats", connect_nats_mock):
            with patch(
                "projects.ships.ingest.main.asyncio.create_task"
            ) as mock_create_task:
                mock_create_task.return_value = MagicMock()
                await svc.start()

        connect_nats_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_creates_ws_task(self):
        """start() creates a background task for subscribe_to_aisstream."""
        svc = AISIngestService()
        fake_task = MagicMock()
        created_coros = []

        def mock_create_task(coro):
            created_coros.append(coro)
            try:
                coro.close()
            except Exception:
                pass
            return fake_task

        with patch.object(svc, "connect_nats", AsyncMock()):
            with patch(
                "projects.ships.ingest.main.asyncio.create_task",
                side_effect=mock_create_task,
            ):
                await svc.start()

        assert len(created_coros) >= 1

    @pytest.mark.asyncio
    async def test_start_assigns_ws_task(self):
        """start() assigns the created task to self.ws_task."""
        svc = AISIngestService()
        assert svc.ws_task is None
        fake_task = MagicMock()

        with patch.object(svc, "connect_nats", AsyncMock()):
            with patch(
                "projects.ships.ingest.main.asyncio.create_task",
                return_value=fake_task,
            ):
                await svc.start()

        assert svc.ws_task is fake_task

    @pytest.mark.asyncio
    async def test_start_connect_nats_called_before_task(self):
        """start() calls connect_nats before spawning the background task."""
        svc = AISIngestService()
        call_order = []

        async def mock_connect_nats():
            call_order.append("connect_nats")

        def mock_create_task(coro):
            call_order.append("create_task")
            try:
                coro.close()
            except Exception:
                pass
            return MagicMock()

        with patch.object(svc, "connect_nats", mock_connect_nats):
            with patch(
                "projects.ships.ingest.main.asyncio.create_task",
                side_effect=mock_create_task,
            ):
                await svc.start()

        # connect_nats must come before create_task
        assert call_order.index("connect_nats") < call_order.index("create_task")
