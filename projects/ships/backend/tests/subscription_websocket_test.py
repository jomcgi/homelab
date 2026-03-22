"""
Tests for Ships API subscription loop, WebSocket endpoint, cleanup loop, and startup.

Covers:
- ShipsAPIService.subscribe_ais_stream(): NATS JetStream pull subscription loop,
  durable consumer creation, batch processing, catchup detection, WS broadcast.
- websocket_live() FastAPI endpoint: accept, snapshot on connect, ping/pong,
  clean disconnect.
- ShipsAPIService.cleanup_loop(): periodic DB cleanup scheduling.
- ShipsAPIService.start() and _run_subscription(): startup task creation.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytest_asyncio

from projects.ships.backend.main import ShipsAPIService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(subject: str, data: dict) -> MagicMock:
    """Return a mock NATS message with ack tracking."""
    msg = MagicMock()
    msg.subject = subject
    msg.data = json.dumps(data).encode()
    msg.ack = AsyncMock()
    return msg


def _consumer_info(num_pending: int) -> MagicMock:
    info = MagicMock()
    info.num_pending = num_pending
    return info


# ---------------------------------------------------------------------------
# subscribe_ais_stream
# ---------------------------------------------------------------------------


class TestSubscribeAISStream:
    """Tests for ShipsAPIService.subscribe_ais_stream()."""

    @pytest.fixture
    def service(self):
        svc = ShipsAPIService()
        svc.running = True
        # Wire up a real in-memory DB without touching NATS
        svc.db.db_path = ":memory:"
        return svc

    @pytest_asyncio.fixture
    async def started_service(self, service):
        await service.db.connect()
        yield service
        await service.db.close()

    # --- consumer creation ---

    @pytest.mark.asyncio
    async def test_pull_subscribe_called_with_durable_name(self, started_service):
        """subscribe_ais_stream creates a durable pull subscription named 'ships-api'."""
        svc = started_service

        mock_psub = AsyncMock()
        # Return caught-up consumer info (no pending) so loop exits after 1 timeout
        mock_psub.consumer_info.return_value = _consumer_info(0)
        mock_psub.fetch.side_effect = asyncio.TimeoutError()

        mock_js = AsyncMock()
        mock_js.pull_subscribe.return_value = mock_psub
        svc.js = mock_js

        # Run for one iteration then stop
        async def stop_after_first_fetch(*_args, **_kwargs):
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch.side_effect = stop_after_first_fetch

        await svc.subscribe_ais_stream()

        mock_js.pull_subscribe.assert_called_once()
        call_kwargs = mock_js.pull_subscribe.call_args
        assert call_kwargs[1]["durable"] == "ships-api" or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "ships-api"
        )

    @pytest.mark.asyncio
    async def test_already_caught_up_sets_ready_immediately(self, started_service):
        """When num_pending == 0 on startup the service is marked ready immediately."""
        svc = started_service

        mock_psub = AsyncMock()
        mock_psub.consumer_info.return_value = _consumer_info(0)

        call_count = 0

        async def fetch_then_stop(*_a, **_kw):
            nonlocal call_count
            call_count += 1
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub.fetch.side_effect = fetch_then_stop
        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert svc.replay_complete is True
        assert svc.ready is True

    # --- message batch processing ---

    @pytest.mark.asyncio
    async def test_position_messages_inserted_into_db(self, started_service):
        """Position messages in a batch are written to the database."""
        svc = started_service

        pos_msg = _make_msg(
            "ais.position.111222333",
            {
                "mmsi": "111222333",
                "lat": 48.5,
                "lon": -123.4,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        # First fetch returns the message, second stops the loop
        fetch_results = [[pos_msg], asyncio.TimeoutError()]
        fetch_index = [0]

        async def fetch_side_effect(*_a, **_kw):
            idx = fetch_index[0]
            fetch_index[0] += 1
            result = fetch_results[idx]
            if isinstance(result, type) and issubclass(result, Exception):
                raise result()
            if isinstance(result, Exception):
                raise result
            return result

        async def consumer_info_side_effect():
            # After first batch mark as caught up
            return _consumer_info(0)

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.side_effect = consumer_info_side_effect

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub
        svc.replay_complete = True  # Already caught up, so DB writes happen normally
        svc.ready = True

        # Allow only 2 fetch calls then stop
        original_fetch = mock_psub.fetch.side_effect

        async def fetch_and_maybe_stop(*a, **kw):
            result = await original_fetch(*a, **kw)
            return result

        # Run subscription
        await svc.subscribe_ais_stream()

        # Verify the MMSI ended up in the in-memory cache
        assert svc.db.get_cached_position("111222333") is not None

    @pytest.mark.asyncio
    async def test_vessel_static_messages_upserted(self, started_service):
        """Static (vessel) messages in a batch are upserted into vessels table."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        vessel_msg = _make_msg(
            "ais.static.999888777",
            {
                "mmsi": "999888777",
                "name": "MV EXAMPLE",
                "ship_type": 70,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [vessel_msg]
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        # Verify vessel landed in DB
        vessel = await svc.db.get_vessel("999888777")
        # get_vessel checks latest_positions — static alone won't appear there,
        # but upsert_vessels_batch should have been called (no error means success).
        # We verify via the db directly.
        cursor = await svc.db.db.execute(
            "SELECT name FROM vessels WHERE mmsi=?", ("999888777",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "MV EXAMPLE"

    @pytest.mark.asyncio
    async def test_messages_received_counter_incremented(self, started_service):
        """messages_received is incremented for every message processed."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        msgs = [
            _make_msg(
                "ais.position.100000001",
                {
                    "mmsi": "100000001",
                    "lat": 48.0,
                    "lon": -123.0,
                    "speed": 1.0,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
            _make_msg(
                "ais.position.100000002",
                {
                    "mmsi": "100000002",
                    "lat": 48.1,
                    "lon": -123.1,
                    "speed": 2.0,
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ),
        ]

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return msgs
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert svc.messages_received == 2

    @pytest.mark.asyncio
    async def test_all_messages_acked_after_batch(self, started_service):
        """All messages in a batch are acked after successful DB write."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        msg1 = _make_msg(
            "ais.position.200000001",
            {
                "mmsi": "200000001",
                "lat": 48.0,
                "lon": -123.0,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        msg2 = _make_msg(
            "ais.position.200000002",
            {
                "mmsi": "200000002",
                "lat": 49.0,
                "lon": -124.0,
                "speed": 3.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [msg1, msg2]
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        msg1.ack.assert_called_once()
        msg2.ack.assert_called_once()

    # --- catchup threshold logic ---

    @pytest.mark.asyncio
    async def test_catchup_completes_when_pending_drops_below_threshold(
        self, started_service
    ):
        """replay_complete becomes True when num_pending falls below threshold."""
        svc = started_service
        assert svc.replay_complete is False

        pos_msg = _make_msg(
            "ais.position.300000001",
            {
                "mmsi": "300000001",
                "lat": 48.0,
                "lon": -123.0,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        fetch_calls = [0]
        consumer_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [pos_msg]
            svc.running = False
            raise asyncio.TimeoutError()

        async def consumer_info_side_effect():
            n = consumer_calls[0]
            consumer_calls[0] += 1
            # First call (initial check): large backlog
            if n == 0:
                return _consumer_info(50000)
            # Subsequent calls: below threshold (default 10000)
            return _consumer_info(100)

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.side_effect = consumer_info_side_effect

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert svc.replay_complete is True
        assert svc.ready is True

    @pytest.mark.asyncio
    async def test_catchup_completes_on_timeout_when_pending_low(
        self, started_service
    ):
        """replay_complete becomes True on TimeoutError when pending <= threshold."""
        svc = started_service

        consumer_calls = [0]

        async def consumer_info_side_effect():
            consumer_calls[0] += 1
            # Initially large, then drops on second call (triggered by timeout handler)
            if consumer_calls[0] <= 1:
                return _consumer_info(50000)
            return _consumer_info(50)

        async def fetch_side_effect(*_a, **_kw):
            # Always timeout, rely on timeout handler for catchup check
            if consumer_calls[0] >= 2:
                svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.side_effect = consumer_info_side_effect

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert svc.replay_complete is True
        assert svc.ready is True

    # --- broadcast trigger ---

    @pytest.mark.asyncio
    async def test_broadcast_not_called_during_catchup(self, started_service):
        """WebSocket broadcast is NOT called while replay_complete is False."""
        svc = started_service
        svc.replay_complete = False  # Explicitly in catchup

        broadcast_called = []
        original_broadcast = svc.ws_manager.broadcast

        async def tracking_broadcast(msg):
            broadcast_called.append(msg)
            return await original_broadcast(msg)

        svc.ws_manager.broadcast = tracking_broadcast

        pos_msg = _make_msg(
            "ais.position.400000001",
            {
                "mmsi": "400000001",
                "lat": 48.0,
                "lon": -123.0,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        fetch_calls = [0]
        consumer_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [pos_msg]
            svc.running = False
            raise asyncio.TimeoutError()

        async def consumer_info_side_effect():
            consumer_calls[0] += 1
            # Keep pending high so catchup does NOT complete during this run
            return _consumer_info(99999)

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.side_effect = consumer_info_side_effect

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert broadcast_called == [], "broadcast must not be called during catchup"

    @pytest.mark.asyncio
    async def test_broadcast_called_after_replay_complete(self, started_service):
        """WebSocket broadcast IS called with batched positions after catchup."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        received_broadcasts = []

        async def tracking_broadcast(msg):
            received_broadcasts.append(msg)

        svc.ws_manager.broadcast = tracking_broadcast

        pos_msg = _make_msg(
            "ais.position.500000001",
            {
                "mmsi": "500000001",
                "lat": 48.0,
                "lon": -123.0,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [pos_msg]
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        assert len(received_broadcasts) == 1
        broadcast_msg = received_broadcasts[0]
        assert broadcast_msg["type"] == "positions"
        assert any(p["mmsi"] == "500000001" for p in broadcast_msg["positions"])

    @pytest.mark.asyncio
    async def test_broadcast_deduplicates_positions_per_mmsi(self, started_service):
        """When multiple positions for same MMSI arrive, only the last is broadcast."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        received_broadcasts = []

        async def tracking_broadcast(msg):
            received_broadcasts.append(msg)

        svc.ws_manager.broadcast = tracking_broadcast

        # Two messages for the same MMSI in one batch
        msg1 = _make_msg(
            "ais.position.600000001",
            {
                "mmsi": "600000001",
                "lat": 48.0,
                "lon": -123.0,
                "speed": 5.0,
                "timestamp": "2024-01-15T10:00:00Z",
            },
        )
        msg2 = _make_msg(
            "ais.position.600000001",
            {
                "mmsi": "600000001",
                "lat": 48.1,
                "lon": -123.1,
                "speed": 6.0,
                "timestamp": "2024-01-15T10:01:00Z",
            },
        )

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                return [msg1, msg2]
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        await svc.subscribe_ais_stream()

        # One broadcast, one position (latest for the MMSI)
        assert len(received_broadcasts) == 1
        positions = received_broadcasts[0]["positions"]
        assert len(positions) == 1
        # Latest position (lat=48.1) wins because of dict dedup by MMSI
        assert positions[0]["lat"] == 48.1

    @pytest.mark.asyncio
    async def test_error_in_message_processing_does_not_crash_loop(
        self, started_service
    ):
        """An exception during batch processing is caught and the loop retries."""
        svc = started_service
        svc.replay_complete = True
        svc.ready = True

        fetch_calls = [0]

        async def fetch_side_effect(*_a, **_kw):
            n = fetch_calls[0]
            fetch_calls[0] += 1
            if n == 0:
                raise RuntimeError("simulated transient error")
            svc.running = False
            raise asyncio.TimeoutError()

        mock_psub = AsyncMock()
        mock_psub.fetch.side_effect = fetch_side_effect
        mock_psub.consumer_info.return_value = _consumer_info(0)

        svc.js = AsyncMock()
        svc.js.pull_subscribe.return_value = mock_psub

        # Patch asyncio.sleep so the retry pause is instant
        with patch("projects.ships.backend.main.asyncio.sleep", AsyncMock()):
            await svc.subscribe_ais_stream()

        # Loop ran without crashing — fetch_calls[0] must be > 1
        assert fetch_calls[0] >= 2

    @pytest.mark.asyncio
    async def test_subscribe_raises_on_pull_subscribe_failure(self, started_service):
        """If pull_subscribe raises, subscribe_ais_stream propagates the exception."""
        svc = started_service

        mock_js = AsyncMock()
        mock_js.pull_subscribe.side_effect = RuntimeError("NATS unavailable")
        svc.js = mock_js

        with pytest.raises(RuntimeError, match="NATS unavailable"):
            await svc.subscribe_ais_stream()


# ---------------------------------------------------------------------------
# websocket_live endpoint
# ---------------------------------------------------------------------------


class TestWebsocketLiveEndpoint:
    """Tests for the /ws/live WebSocket endpoint."""

    @pytest_asyncio.fixture
    async def test_client_setup(self):
        """Set up a test client with mocked NATS and real in-memory DB."""
        with patch("projects.ships.backend.main.nats.connect") as mock_connect:
            mock_nc = MagicMock()
            mock_nc.is_connected = True
            mock_js = AsyncMock()
            mock_nc.jetstream.return_value = mock_js
            mock_connect.return_value = mock_nc

            from projects.ships.backend.main import app, service

            service.running = True
            service.ready = True
            service.replay_complete = True
            service.nc = mock_nc
            service.js = mock_js
            service.db.db_path = ":memory:"
            await service.db.connect()

            yield app, service

            await service.db.close()
            service.running = False

    @pytest.mark.asyncio
    async def test_websocket_connects_and_receives_snapshot(self, test_client_setup):
        """On connect the endpoint sends a snapshot of current vessels."""
        app, service = test_client_setup

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)

        # Pre-populate a vessel
        pos = {
            "mmsi": "700000001",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 5.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        await service.db.insert_positions_batch([(pos, pos["timestamp"])])
        await service.db.commit()

        # Use a mock WebSocket to inspect what was sent
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=Exception("disconnect"))

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", AsyncMock()):
            with patch.object(service.ws_manager, "disconnect", AsyncMock()):
                try:
                    await websocket_live(mock_ws)
                except Exception:
                    pass

        # First send_json call must be a snapshot
        mock_ws.send_json.assert_called()
        first_call = mock_ws.send_json.call_args_list[0]
        snapshot = first_call[0][0]
        assert snapshot["type"] == "snapshot"
        assert "vessels" in snapshot

    @pytest.mark.asyncio
    async def test_websocket_snapshot_includes_vessels(self, test_client_setup):
        """Snapshot includes all currently tracked vessels."""
        app, service = test_client_setup

        # Insert two vessels
        for mmsi in ("800000001", "800000002"):
            pos = {
                "mmsi": mmsi,
                "lat": 48.0,
                "lon": -123.0,
                "speed": 3.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
            await service.db.insert_positions_batch([(pos, pos["timestamp"])])
        await service.db.commit()

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=Exception("disconnect"))

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", AsyncMock()):
            with patch.object(service.ws_manager, "disconnect", AsyncMock()):
                try:
                    await websocket_live(mock_ws)
                except Exception:
                    pass

        snapshot = mock_ws.send_json.call_args_list[0][0][0]
        mmsis_in_snapshot = {v["mmsi"] for v in snapshot["vessels"]}
        assert "800000001" in mmsis_in_snapshot
        assert "800000002" in mmsis_in_snapshot

    @pytest.mark.asyncio
    async def test_websocket_ping_pong(self, test_client_setup):
        """Sending 'ping' receives 'pong' response."""
        app, service = test_client_setup

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        # First receive returns "ping", second raises disconnect
        from fastapi import WebSocketDisconnect

        mock_ws.receive_text = AsyncMock(
            side_effect=["ping", WebSocketDisconnect()]
        )
        mock_ws.send_text = AsyncMock()

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", AsyncMock()):
            with patch.object(service.ws_manager, "disconnect", AsyncMock()):
                await websocket_live(mock_ws)

        mock_ws.send_text.assert_called_once_with("pong")

    @pytest.mark.asyncio
    async def test_websocket_disconnect_cleans_up(self, test_client_setup):
        """On WebSocketDisconnect the manager's disconnect is called."""
        app, service = test_client_setup

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        from fastapi import WebSocketDisconnect

        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        disconnect_mock = AsyncMock()

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", AsyncMock()):
            with patch.object(service.ws_manager, "disconnect", disconnect_mock):
                await websocket_live(mock_ws)

        disconnect_mock.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_websocket_connect_registers_client(self, test_client_setup):
        """On connect the manager's connect() is called, registering the client."""
        app, service = test_client_setup

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        from fastapi import WebSocketDisconnect

        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        connect_mock = AsyncMock()

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", connect_mock):
            with patch.object(service.ws_manager, "disconnect", AsyncMock()):
                await websocket_live(mock_ws)

        connect_mock.assert_called_once_with(mock_ws)

    @pytest.mark.asyncio
    async def test_websocket_disconnect_called_even_on_unexpected_error(
        self, test_client_setup
    ):
        """Disconnect is called in the finally block even if an unexpected error occurs."""
        app, service = test_client_setup

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=RuntimeError("send failure"))

        disconnect_mock = AsyncMock()

        from projects.ships.backend.main import websocket_live

        with patch.object(service.ws_manager, "connect", AsyncMock()):
            with patch.object(service.ws_manager, "disconnect", disconnect_mock):
                with pytest.raises(RuntimeError):
                    await websocket_live(mock_ws)

        disconnect_mock.assert_called_once_with(mock_ws)


# ---------------------------------------------------------------------------
# cleanup_loop
# ---------------------------------------------------------------------------


class TestCleanupLoop:
    """Tests for ShipsAPIService.cleanup_loop()."""

    @pytest.fixture
    def service(self):
        svc = ShipsAPIService()
        svc.running = True
        return svc

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_db_cleanup(self, service):
        """cleanup_loop calls db.cleanup_old_positions() after sleeping."""
        cleanup_call_count = [0]

        async def mock_cleanup():
            cleanup_call_count[0] += 1
            service.running = False  # Stop after first cleanup
            return 0

        service.db.cleanup_old_positions = mock_cleanup

        # Patch sleep to be instant and trigger cleanup immediately
        sleep_calls = []

        async def fast_sleep(seconds):
            sleep_calls.append(seconds)
            # Don't actually sleep

        with patch("projects.ships.backend.main.asyncio.sleep", fast_sleep):
            await service.cleanup_loop()

        assert cleanup_call_count[0] == 1

    @pytest.mark.asyncio
    async def test_cleanup_loop_sleeps_one_hour(self, service):
        """cleanup_loop sleeps for 3600 seconds between cleanups."""
        sleep_calls = []

        async def fast_sleep(seconds):
            sleep_calls.append(seconds)
            service.running = False  # Stop after first sleep

        service.db.cleanup_old_positions = AsyncMock(return_value=0)

        with patch("projects.ships.backend.main.asyncio.sleep", fast_sleep):
            await service.cleanup_loop()

        assert len(sleep_calls) >= 1
        assert sleep_calls[0] == 3600

    @pytest.mark.asyncio
    async def test_cleanup_loop_stops_on_cancelled_error(self, service):
        """cleanup_loop exits cleanly when CancelledError is raised."""

        async def fast_sleep(_seconds):
            raise asyncio.CancelledError()

        service.db.cleanup_old_positions = AsyncMock(return_value=0)

        with patch("projects.ships.backend.main.asyncio.sleep", fast_sleep):
            # Should return without raising
            await service.cleanup_loop()

    @pytest.mark.asyncio
    async def test_cleanup_loop_not_called_when_stopped(self, service):
        """cleanup_loop does not call cleanup if running is False after sleep."""
        cleanup_call_count = [0]

        async def fast_sleep(_seconds):
            service.running = False  # Stop before cleanup runs

        async def mock_cleanup():
            cleanup_call_count[0] += 1
            return 0

        service.db.cleanup_old_positions = mock_cleanup

        with patch("projects.ships.backend.main.asyncio.sleep", fast_sleep):
            await service.cleanup_loop()

        # cleanup_old_positions should NOT have been called because running=False
        assert cleanup_call_count[0] == 0

    @pytest.mark.asyncio
    async def test_cleanup_loop_continues_after_exception(self, service):
        """cleanup_loop logs errors and continues running instead of crashing."""
        call_count = [0]

        async def fast_sleep(_seconds):
            if call_count[0] >= 2:
                service.running = False

        async def failing_cleanup():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient DB error")
            service.running = False
            return 0

        service.db.cleanup_old_positions = failing_cleanup

        with patch("projects.ships.backend.main.asyncio.sleep", fast_sleep):
            await service.cleanup_loop()

        # Should have attempted cleanup at least once without crashing


# ---------------------------------------------------------------------------
# start() and _run_subscription()
# ---------------------------------------------------------------------------


class TestStartAndRunSubscription:
    """Tests for ShipsAPIService.start() and _run_subscription()."""

    @pytest.mark.asyncio
    async def test_start_sets_running_true(self):
        """start() sets self.running = True."""
        svc = ShipsAPIService()
        svc.db.db_path = ":memory:"

        with patch.object(svc.db, "connect", AsyncMock()):
            with patch.object(svc, "connect_nats", AsyncMock()):
                with patch.object(
                    svc, "_run_subscription", AsyncMock(return_value=None)
                ):
                    with patch("projects.ships.backend.main.asyncio.create_task") as ct:
                        ct.return_value = MagicMock()
                        await svc.start()

        assert svc.running is True

    @pytest.mark.asyncio
    async def test_start_connects_database(self):
        """start() calls db.connect()."""
        svc = ShipsAPIService()
        db_connect = AsyncMock()
        svc.db.connect = db_connect

        with patch.object(svc, "connect_nats", AsyncMock()):
            with patch("projects.ships.backend.main.asyncio.create_task") as ct:
                ct.return_value = MagicMock()
                await svc.start()

        db_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_connects_nats(self):
        """start() calls connect_nats()."""
        svc = ShipsAPIService()
        svc.db.db_path = ":memory:"
        connect_nats = AsyncMock()

        with patch.object(svc.db, "connect", AsyncMock()):
            with patch.object(svc, "connect_nats", connect_nats):
                with patch("projects.ships.backend.main.asyncio.create_task") as ct:
                    ct.return_value = MagicMock()
                    await svc.start()

        connect_nats.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_creates_subscription_task(self):
        """start() creates a background task for _run_subscription."""
        svc = ShipsAPIService()
        svc.db.db_path = ":memory:"
        created_tasks = []

        def mock_create_task(coro):
            task = MagicMock()
            created_tasks.append(coro)
            # Close the coroutine to avoid warnings
            try:
                coro.close()
            except Exception:
                pass
            return task

        with patch.object(svc.db, "connect", AsyncMock()):
            with patch.object(svc, "connect_nats", AsyncMock()):
                with patch(
                    "projects.ships.backend.main.asyncio.create_task",
                    side_effect=mock_create_task,
                ):
                    await svc.start()

        assert len(created_tasks) >= 1

    @pytest.mark.asyncio
    async def test_start_creates_cleanup_task(self):
        """start() creates a background task for cleanup_loop."""
        svc = ShipsAPIService()
        svc.db.db_path = ":memory:"
        task_mock = MagicMock()

        with patch.object(svc.db, "connect", AsyncMock()):
            with patch.object(svc, "connect_nats", AsyncMock()):
                with patch(
                    "projects.ships.backend.main.asyncio.create_task",
                    return_value=task_mock,
                ) as ct:
                    await svc.start()

        # create_task should be called at least twice (subscription + cleanup)
        assert ct.call_count >= 2

    @pytest.mark.asyncio
    async def test_run_subscription_delegates_to_subscribe(self):
        """_run_subscription() calls subscribe_ais_stream()."""
        svc = ShipsAPIService()
        subscribe_mock = AsyncMock()
        svc.subscribe_ais_stream = subscribe_mock

        await svc._run_subscription()

        subscribe_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_assigns_subscription_task(self):
        """start() assigns the subscription coroutine to self.subscription_task."""
        svc = ShipsAPIService()
        svc.db.db_path = ":memory:"
        fake_task = MagicMock()

        with patch.object(svc.db, "connect", AsyncMock()):
            with patch.object(svc, "connect_nats", AsyncMock()):
                with patch(
                    "projects.ships.backend.main.asyncio.create_task",
                    return_value=fake_task,
                ):
                    await svc.start()

        # Both subscription_task and cleanup_task should be set
        assert svc.subscription_task is not None
        assert svc.cleanup_task is not None
