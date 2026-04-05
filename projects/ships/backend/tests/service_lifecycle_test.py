"""Tests for ShipsAPIService cleanup loop and WebSocketManager broadcast edge cases."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCleanupLoop:
    """Tests for ShipsAPIService.cleanup_loop() lifecycle behaviour."""

    @pytest.fixture
    def service(self):
        from projects.ships.backend.main import ShipsAPIService

        return ShipsAPIService()

    @pytest.mark.asyncio
    async def test_cleanup_loop_cancels_on_cancelled_error(self, service):
        """CancelledError inside the sleep breaks the loop cleanly without re-raising."""
        service.running = True
        service.db = MagicMock()
        service.db.cleanup_old_positions = AsyncMock()

        with patch(
            "projects.ships.backend.main.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ):
            # Should return cleanly, not propagate CancelledError
            await service.cleanup_loop()

        # cleanup_old_positions was never reached because sleep raised first
        service.db.cleanup_old_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_loop_stops_when_running_false(self, service):
        """Loop exits after one iteration when running is set to False."""
        service.running = True
        service.db = MagicMock()
        service.db.cleanup_old_positions = AsyncMock()

        call_count = 0

        async def fake_sleep(_duration):
            nonlocal call_count
            call_count += 1
            # After the first sleep, flip running off so the while condition fails
            service.running = False

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.cleanup_loop()

        # sleep was called exactly once (one loop iteration)
        assert call_count == 1
        # cleanup was NOT called because running was set to False during sleep,
        # and the implementation checks `if self.running` after sleep before calling cleanup
        service.db.cleanup_old_positions.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_exceptions_without_crashing(self, service):
        """A DB exception inside cleanup_old_positions is swallowed and the loop continues."""
        service.running = True
        service.db = MagicMock()

        iteration = 0

        async def fake_sleep(_duration):
            nonlocal iteration
            iteration += 1
            if iteration >= 2:
                service.running = False

        async def failing_cleanup():
            raise RuntimeError("DB error")

        service.db.cleanup_old_positions = failing_cleanup

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            # Should not raise even though cleanup raises on every call
            await service.cleanup_loop()

        # We ran two iterations before running was set to False
        assert iteration == 2

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_cleanup_when_running(self, service):
        """cleanup_old_positions is called once per iteration while running is True."""
        service.running = True
        service.db = MagicMock()
        service.db.cleanup_old_positions = AsyncMock()

        iteration = 0

        async def fake_sleep(_duration):
            nonlocal iteration
            iteration += 1
            # Keep running True so that cleanup_old_positions is called after this sleep.
            # The loop will then check the while condition and exit because we set
            # running=False via the cleanup mock side-effect below.

        original_cleanup = service.db.cleanup_old_positions

        async def cleanup_then_stop():
            await original_cleanup()
            service.running = False

        service.db.cleanup_old_positions = AsyncMock(side_effect=cleanup_then_stop)

        with patch("projects.ships.backend.main.asyncio.sleep", side_effect=fake_sleep):
            await service.cleanup_loop()

        # cleanup_old_positions was called exactly once (running was True when checked after sleep)
        service.db.cleanup_old_positions.assert_called_once()


class TestWebSocketManagerBroadcastEdgeCases:
    """Additional broadcast edge-case tests for WebSocketManager."""

    @pytest.fixture
    def manager(self):
        from projects.ships.backend.main import WebSocketManager

        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_broadcast_all_connections_fail(self, manager):
        """When every connection fails during broadcast, all are removed."""
        from fastapi.websockets import WebSocket

        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws1.send_json.side_effect = Exception("closed")
        ws2.send_json.side_effect = Exception("closed")
        manager.active_connections = [ws1, ws2]

        await manager.broadcast({"type": "test"})

        assert ws1 not in manager.active_connections
        assert ws2 not in manager.active_connections
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_preserves_connection_order_for_successful_sends(
        self, manager
    ):
        """Successful connections remain in the list in their original order."""
        from fastapi.websockets import WebSocket

        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)
        ws3 = AsyncMock(spec=WebSocket)
        manager.active_connections = [ws1, ws2, ws3]

        message = {"type": "positions", "positions": [{"mmsi": "123"}]}
        await manager.broadcast(message)

        # All sends succeeded — order must be preserved
        assert manager.active_connections == [ws1, ws2, ws3]
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)
