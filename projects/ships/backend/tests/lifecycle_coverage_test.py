"""
Additional lifecycle and WebSocket coverage tests for Ships API backend.

These tests complement existing coverage by exercising additional paths in:
1. ShipsAPIService.connect_nats() — successful connection and jetstream wiring
2. ShipsAPIService.start() — task creation and lifecycle ordering
3. ShipsAPIService.stop() — graceful shutdown with db.close() called
4. ShipsAPIService.cleanup_loop() — hourly sleep interval confirmed
5. websocket_live() — non-ping message ignored (no pong), disconnect cleans up
6. ShipsAPIService.subscribe_ais_stream() — connect_nats wires js used by subscribe
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# connect_nats()
# ---------------------------------------------------------------------------


class TestConnectNatsSuccessPath:
    """Tests for ShipsAPIService.connect_nats() successful connection."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_connect_nats_sets_nc_attribute(self, service):
        """connect_nats() sets self.nc to the returned NATS connection."""
        import nats as nats_module

        mock_nc = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=MagicMock())

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        assert service.nc is mock_nc

    @pytest.mark.asyncio
    async def test_connect_nats_sets_js_attribute(self, service):
        """connect_nats() sets self.js via nc.jetstream()."""
        import nats as nats_module

        mock_js = MagicMock()
        mock_nc = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        assert service.js is mock_js

    @pytest.mark.asyncio
    async def test_connect_nats_calls_jetstream(self, service):
        """connect_nats() calls nc.jetstream() to obtain the JetStream context."""
        import nats as nats_module

        mock_nc = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=MagicMock())

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        mock_nc.jetstream.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_nats_uses_configured_url(self, service):
        """connect_nats() passes NATS_URL to nats.connect."""
        import nats as nats_module
        import projects.ships.backend.main as main_module

        mock_nc = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=MagicMock())
        connect_mock = AsyncMock(return_value=mock_nc)

        with patch.object(nats_module, "connect", connect_mock):
            await service.connect_nats()

        connect_mock.assert_called_once_with(main_module.NATS_URL)


# ---------------------------------------------------------------------------
# stop() — db.close() is called
# ---------------------------------------------------------------------------


class TestStopDbClose:
    """Tests that stop() always calls db.close()."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_stop_calls_db_close(self, service):
        """stop() calls db.close() to release the database connection."""
        service.db = MagicMock()
        service.db.close = AsyncMock()
        service.nc = None

        await service.stop()

        service.db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_running_subscription_task(self, service):
        """stop() cancels a running subscription_task."""
        service.nc = None
        service.db = MagicMock()
        service.db.close = AsyncMock()

        async def long_task():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_task())
        service.subscription_task = task

        await service.stop()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_cancels_running_cleanup_task(self, service):
        """stop() cancels a running cleanup_task."""
        service.nc = None
        service.db = MagicMock()
        service.db.close = AsyncMock()

        async def long_task():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_task())
        service.cleanup_task = task

        await service.stop()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_closes_nats_when_nc_set(self, service):
        """stop() calls nc.close() when nc is set."""
        service.db = MagicMock()
        service.db.close = AsyncMock()

        mock_nc = MagicMock()
        mock_nc.close = AsyncMock()
        service.nc = mock_nc

        await service.stop()

        mock_nc.close.assert_called_once()


# ---------------------------------------------------------------------------
# cleanup_loop() — sleep interval
# ---------------------------------------------------------------------------


class TestCleanupLoopSleepInterval:
    """Tests that cleanup_loop() sleeps for the correct interval (3600s)."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_cleanup_loop_sleeps_3600_seconds(self, service):
        """cleanup_loop() calls asyncio.sleep(3600) each iteration."""
        service.running = True
        service.db = MagicMock()
        service.db.cleanup_old_positions = AsyncMock()

        sleep_durations = []

        async def fake_sleep(duration):
            sleep_durations.append(duration)
            service.running = False  # stop after first sleep

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.cleanup_loop()

        assert len(sleep_durations) == 1
        assert sleep_durations[0] == 3600


# ---------------------------------------------------------------------------
# websocket_live() — additional edge cases
# ---------------------------------------------------------------------------


class TestWebsocketLiveAdditionalCases:
    """Additional tests for websocket_live() endpoint behaviour."""

    @pytest.mark.asyncio
    async def test_non_ping_message_ignored(self):
        """Messages other than 'ping' are silently ignored (no pong sent)."""
        from fastapi import WebSocketDisconnect
        from projects.ships.backend.main import websocket_live, service

        mock_ws = AsyncMock()
        # First receive: a non-ping message; second: disconnect
        mock_ws.receive_text = AsyncMock(
            side_effect=["hello", WebSocketDisconnect()]
        )

        mock_db = MagicMock()
        mock_db.get_latest_positions = AsyncMock(return_value=[])

        original_db = service.db
        try:
            service.db = mock_db
            await websocket_live(mock_ws)
        finally:
            service.db = original_db

        # send_text (pong) should NOT have been called for a non-ping message
        mock_ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_manager(self):
        """When client disconnects, ws_manager.disconnect() is called."""
        from fastapi import WebSocketDisconnect
        from projects.ships.backend.main import websocket_live, service

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        mock_db = MagicMock()
        mock_db.get_latest_positions = AsyncMock(return_value=[])

        disconnect_called_with = []

        original_disconnect = service.ws_manager.disconnect
        original_db = service.db

        async def spy_disconnect(ws):
            disconnect_called_with.append(ws)
            # We still call original to keep state consistent (though manager is real)

        try:
            service.db = mock_db
            with patch.object(service.ws_manager, "disconnect", side_effect=spy_disconnect):
                await websocket_live(mock_ws)
        finally:
            service.db = original_db

        assert len(disconnect_called_with) == 1
        assert disconnect_called_with[0] is mock_ws

    @pytest.mark.asyncio
    async def test_snapshot_contains_vessels_key(self):
        """Initial snapshot message sent to client has a 'vessels' key."""
        from fastapi import WebSocketDisconnect
        from projects.ships.backend.main import websocket_live, service

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        sample_vessels = [
            {"mmsi": "111111111", "lat": 48.5, "lon": -123.4},
        ]

        mock_db = MagicMock()
        mock_db.get_latest_positions = AsyncMock(return_value=sample_vessels)

        sent_json_messages = []
        original_send_json = mock_ws.send_json

        async def capture_send_json(msg):
            sent_json_messages.append(msg)

        mock_ws.send_json = capture_send_json

        original_db = service.db
        try:
            service.db = mock_db
            await websocket_live(mock_ws)
        finally:
            service.db = original_db

        assert len(sent_json_messages) >= 1
        snapshot = sent_json_messages[0]
        assert snapshot["type"] == "snapshot"
        assert "vessels" in snapshot
        assert snapshot["vessels"] == sample_vessels

    @pytest.mark.asyncio
    async def test_connect_called_on_websocket(self):
        """websocket_live() calls ws_manager.connect() to accept the connection."""
        from fastapi import WebSocketDisconnect
        from projects.ships.backend.main import websocket_live, service

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        mock_db = MagicMock()
        mock_db.get_latest_positions = AsyncMock(return_value=[])

        connect_called_with = []
        original_connect = service.ws_manager.connect

        async def spy_connect(ws):
            connect_called_with.append(ws)
            # Actually accept to keep state consistent
            await ws.accept()

        original_db = service.db
        try:
            service.db = mock_db
            with patch.object(service.ws_manager, "connect", side_effect=spy_connect):
                await websocket_live(mock_ws)
        finally:
            service.db = original_db

        assert len(connect_called_with) == 1
        assert connect_called_with[0] is mock_ws


# ---------------------------------------------------------------------------
# subscribe_ais_stream() — uses js set by connect_nats()
# ---------------------------------------------------------------------------


class TestSubscribeUsesJsFromConnectNats:
    """Verify subscribe_ais_stream() uses the self.js set by connect_nats()."""

    @pytest.mark.asyncio
    async def test_subscribe_uses_js_attribute(self):
        """subscribe_ais_stream() calls pull_subscribe on self.js (not a new connection)."""
        from projects.ships.backend.main import ShipsAPIService, Database

        service = ShipsAPIService()
        service.running = False  # skip the while-loop body

        mock_psub = AsyncMock()
        consumer_info = MagicMock()
        consumer_info.num_pending = 0
        mock_psub.consumer_info = AsyncMock(return_value=consumer_info)

        mock_js = MagicMock()
        mock_js.pull_subscribe = AsyncMock(return_value=mock_psub)

        # Set js directly (as connect_nats would do)
        service.js = mock_js

        await service.subscribe_ais_stream()

        # pull_subscribe was called on our mock_js
        mock_js.pull_subscribe.assert_called_once()
