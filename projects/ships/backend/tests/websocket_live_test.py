"""
Integration tests for the /ws/live WebSocket endpoint.

Covers gaps identified in the coverage analysis:
1. Snapshot send on connect — the endpoint sends an initial "snapshot" message
   with all current vessels immediately upon WebSocket connection.
2. Ping/pong handling — sending "ping" over the WebSocket returns "pong".
3. Disconnect handling — WebSocketDisconnect causes graceful cleanup (the client
   is removed from the manager's active_connections list).
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect

from projects.ships.backend.main import WebSocketManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingWebSocket:
    """Minimal WebSocket mock that records sent messages and can simulate events."""

    def __init__(self, receive_sequence=None):
        self.accepted = False
        self.sent_json: list[dict] = []
        self.sent_text: list[str] = []
        # Sequence of values/exceptions to return from receive_text()
        self._receive_sequence = list(receive_sequence or [])
        self._receive_index = 0

    async def accept(self):
        self.accepted = True

    async def send_json(self, data: dict):
        self.sent_json.append(data)

    async def send_text(self, text: str):
        self.sent_text.append(text)

    async def receive_text(self):
        if self._receive_index >= len(self._receive_sequence):
            # Default: raise WebSocketDisconnect to end the loop
            raise WebSocketDisconnect()
        item = self._receive_sequence[self._receive_index]
        self._receive_index += 1
        if isinstance(item, Exception):
            raise item
        return item


# ---------------------------------------------------------------------------
# 1. Snapshot send on connect
# ---------------------------------------------------------------------------


class TestWebSocketLiveSnapshotOnConnect:
    """The /ws/live endpoint sends a snapshot of all vessels on connect."""

    @pytest.mark.asyncio
    async def test_snapshot_message_sent_on_connect(self, test_client):
        """On connect the endpoint immediately sends a snapshot of current vessels."""
        from projects.ships.backend.main import service

        # Insert a vessel so the snapshot is non-empty
        vessel_data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "speed": 5.0,
            "course": 90.0,
            "heading": 88,
            "nav_status": 0,
            "ship_name": "TEST VESSEL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await service.db.insert_positions_batch([(vessel_data, vessel_data["timestamp"])])
        await service.db.commit()

        mock_ws = _RecordingWebSocket(receive_sequence=[WebSocketDisconnect()])

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        assert mock_ws.accepted, "WebSocket should have been accepted"
        assert len(mock_ws.sent_json) >= 1, "Should have sent at least one JSON message"

        # First message should be a snapshot
        first_msg = mock_ws.sent_json[0]
        assert first_msg["type"] == "snapshot", (
            f"Expected first message type='snapshot', got {first_msg['type']!r}"
        )
        assert "vessels" in first_msg, "Snapshot message should have a 'vessels' key"

    @pytest.mark.asyncio
    async def test_snapshot_contains_correct_vessels(self, test_client):
        """Snapshot contains vessel data that was in the database at connect time."""
        from projects.ships.backend.main import service

        vessels = [
            {
                "mmsi": "111111111",
                "lat": 48.5,
                "lon": -123.4,
                "speed": 5.0,
                "course": 90.0,
                "heading": 88,
                "nav_status": 0,
                "ship_name": "VESSEL ONE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "mmsi": "222222222",
                "lat": 49.0,
                "lon": -124.0,
                "speed": 0.0,
                "course": 0.0,
                "heading": 0,
                "nav_status": 1,
                "ship_name": "VESSEL TWO",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await service.db.insert_positions_batch(
            [(v, v["timestamp"]) for v in vessels]
        )
        await service.db.commit()

        mock_ws = _RecordingWebSocket(receive_sequence=[WebSocketDisconnect()])

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        snapshot = mock_ws.sent_json[0]
        assert snapshot["type"] == "snapshot"
        returned_mmsis = {v["mmsi"] for v in snapshot["vessels"]}
        assert "111111111" in returned_mmsis
        assert "222222222" in returned_mmsis

    @pytest.mark.asyncio
    async def test_snapshot_sent_even_with_empty_database(self, test_client):
        """Snapshot is sent even when no vessels are in the database."""
        mock_ws = _RecordingWebSocket(receive_sequence=[WebSocketDisconnect()])

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        assert len(mock_ws.sent_json) >= 1
        snapshot = mock_ws.sent_json[0]
        assert snapshot["type"] == "snapshot"
        assert snapshot["vessels"] == []


# ---------------------------------------------------------------------------
# 2. Ping/pong handling
# ---------------------------------------------------------------------------


class TestWebSocketLivePingPong:
    """The /ws/live endpoint responds to 'ping' text frames with 'pong'."""

    @pytest.mark.asyncio
    async def test_ping_returns_pong(self, test_client):
        """Sending 'ping' text triggers a 'pong' text response."""
        mock_ws = _RecordingWebSocket(
            receive_sequence=["ping", WebSocketDisconnect()]
        )

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        assert "pong" in mock_ws.sent_text, (
            f"Expected 'pong' in sent text, got {mock_ws.sent_text!r}"
        )

    @pytest.mark.asyncio
    async def test_multiple_pings_return_multiple_pongs(self, test_client):
        """Multiple 'ping' frames each result in a 'pong' response."""
        mock_ws = _RecordingWebSocket(
            receive_sequence=["ping", "ping", "ping", WebSocketDisconnect()]
        )

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        pong_count = mock_ws.sent_text.count("pong")
        assert pong_count == 3, (
            f"Expected 3 pongs for 3 pings, got {pong_count}"
        )

    @pytest.mark.asyncio
    async def test_non_ping_message_does_not_send_pong(self, test_client):
        """A non-'ping' text message does not trigger a 'pong' response."""
        mock_ws = _RecordingWebSocket(
            receive_sequence=["hello", "not a ping", WebSocketDisconnect()]
        )

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        assert "pong" not in mock_ws.sent_text, (
            "Non-ping messages should not generate pong responses"
        )

    @pytest.mark.asyncio
    async def test_ping_after_initial_snapshot(self, test_client):
        """'pong' is sent after the initial snapshot has been transmitted."""
        mock_ws = _RecordingWebSocket(
            receive_sequence=["ping", WebSocketDisconnect()]
        )

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        # Snapshot should be the first sent message, pong in sent_text
        assert len(mock_ws.sent_json) >= 1
        assert mock_ws.sent_json[0]["type"] == "snapshot"
        assert "pong" in mock_ws.sent_text


# ---------------------------------------------------------------------------
# 3. Disconnect handling
# ---------------------------------------------------------------------------


class TestWebSocketLiveDisconnectHandling:
    """WebSocketDisconnect causes the client to be removed from the manager."""

    @pytest.mark.asyncio
    async def test_client_removed_from_manager_on_disconnect(self, test_client):
        """After WebSocketDisconnect the WebSocket is no longer in active_connections."""
        from projects.ships.backend.main import service

        mock_ws = _RecordingWebSocket(receive_sequence=[WebSocketDisconnect()])

        # Track the ws_manager state before and after
        initial_count = len(service.ws_manager.active_connections)

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        final_count = len(service.ws_manager.active_connections)
        assert final_count == initial_count, (
            f"Client should have been removed: count went from {initial_count} to {final_count}"
        )
        assert mock_ws not in service.ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_client_is_added_during_connection(self, test_client):
        """The WebSocket is in active_connections while the handler is running."""
        from projects.ships.backend.main import service

        connected_count: list[int] = []

        class _SpyWebSocket(_RecordingWebSocket):
            async def receive_text(self):
                # Capture the count while we're "inside" the loop
                connected_count.append(len(service.ws_manager.active_connections))
                raise WebSocketDisconnect()

        mock_ws = _SpyWebSocket()

        from projects.ships.backend.main import websocket_live

        await websocket_live(mock_ws)

        assert len(connected_count) >= 1
        # During the receive_text call, the WebSocket was in active_connections
        assert connected_count[0] >= 1, (
            "WebSocket should be in active_connections during the handler loop"
        )

    @pytest.mark.asyncio
    async def test_finally_block_runs_on_disconnect(self, test_client):
        """The finally block (disconnect call) runs even on WebSocketDisconnect."""
        from projects.ships.backend.main import service

        disconnect_called = []

        original_disconnect = service.ws_manager.disconnect

        async def spy_disconnect(ws):
            disconnect_called.append(ws)
            await original_disconnect(ws)

        mock_ws = _RecordingWebSocket(receive_sequence=[WebSocketDisconnect()])

        with patch.object(service.ws_manager, "disconnect", spy_disconnect):
            from projects.ships.backend.main import websocket_live

            await websocket_live(mock_ws)

        assert len(disconnect_called) == 1, (
            "ws_manager.disconnect should have been called exactly once"
        )
        assert disconnect_called[0] is mock_ws


# ---------------------------------------------------------------------------
# 4. WebSocketManager integration with the endpoint
# ---------------------------------------------------------------------------


class TestWebSocketManagerEndpointIntegration:
    """The websocket_live endpoint uses the service.ws_manager correctly."""

    @pytest.mark.asyncio
    async def test_broadcast_reaches_connected_client(self, test_client):
        """A broadcast while a client is connected delivers the message to them."""
        from projects.ships.backend.main import service

        received: list[dict] = []

        class _ListeningWebSocket(_RecordingWebSocket):
            async def send_json(self, data: dict):
                received.append(data)

            async def receive_text(self):
                # Let the broadcast happen, then disconnect
                await asyncio.sleep(0.05)
                raise WebSocketDisconnect()

        mock_ws = _ListeningWebSocket()

        broadcast_done = asyncio.Event()

        async def do_broadcast():
            # Wait until the WS is connected (in active_connections)
            for _ in range(20):
                if mock_ws in service.ws_manager.active_connections:
                    break
                await asyncio.sleep(0.01)
            await service.ws_manager.broadcast(
                {"type": "positions", "positions": [{"mmsi": "999"}]}
            )
            broadcast_done.set()

        from projects.ships.backend.main import websocket_live

        # Run the endpoint and the broadcast concurrently
        await asyncio.gather(
            websocket_live(mock_ws),
            do_broadcast(),
        )

        # The listening WebSocket should have received the broadcast
        broadcast_msgs = [m for m in received if m.get("type") == "positions"]
        assert len(broadcast_msgs) >= 1, (
            f"Expected at least one 'positions' broadcast, got {received!r}"
        )
