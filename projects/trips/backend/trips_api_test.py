"""Tests for Trips API service."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

import projects.trips.backend.main as trips_main
from projects.trips.backend.main import (
    ConnectionManager,
    TripPoint,
    TripsState,
    app,
    is_valid_coordinates,
    require_api_key,
)


class TestIsValidCoordinates:
    """Tests for coordinate validation."""

    def test_valid_coordinates(self):
        assert is_valid_coordinates(45.0, -122.0) is True
        assert is_valid_coordinates(-33.9, 151.2) is True
        assert is_valid_coordinates(90.0, 180.0) is True
        assert is_valid_coordinates(-90.0, -180.0) is True

    def test_null_island_rejected(self):
        """Null island (0, 0) is a common GPS error and should be rejected."""
        assert is_valid_coordinates(0.0, 0.0) is False

    def test_out_of_range_latitude(self):
        assert is_valid_coordinates(91.0, 0.0) is False
        assert is_valid_coordinates(-91.0, 0.0) is False

    def test_out_of_range_longitude(self):
        assert is_valid_coordinates(0.0, 181.0) is False
        assert is_valid_coordinates(0.0, -181.0) is False

    def test_zero_latitude_valid(self):
        """Zero latitude with non-zero longitude is valid (equator)."""
        assert is_valid_coordinates(0.0, 45.0) is True

    def test_zero_longitude_valid(self):
        """Zero longitude with non-zero latitude is valid (prime meridian)."""
        assert is_valid_coordinates(45.0, 0.0) is True


class TestTripPoint:
    """Tests for TripPoint model."""

    def test_create_minimal_point(self):
        point = TripPoint(
            id="test123",
            lat=45.0,
            lng=-122.0,
            timestamp="2024-01-15T10:30:00Z",
        )
        assert point.id == "test123"
        assert point.lat == 45.0
        assert point.lng == -122.0
        assert point.image is None
        assert point.source == "gopro"
        assert point.tags == ["car"]

    def test_create_full_point(self):
        point = TripPoint(
            id="test456",
            lat=60.5,
            lng=-135.0,
            timestamp="2024-01-15T12:00:00Z",
            image="IMG_0001.jpg",
            source="camera",
            tags=["hike", "mountain"],
            elevation=1500.0,
            light_value=10.5,
            iso=100,
            shutter_speed="1/500",
            aperture=8.0,
            focal_length_35mm=24,
        )
        assert point.image == "IMG_0001.jpg"
        assert point.source == "camera"
        assert point.tags == ["hike", "mountain"]
        assert point.elevation == 1500.0
        assert point.iso == 100


class TestConnectionManager:
    """Tests for WebSocket connection manager."""

    @pytest.fixture
    def manager(self):
        return ConnectionManager()

    @pytest.mark.asyncio
    async def test_connect(self, manager):
        mock_ws = AsyncMock(spec=WebSocket)
        await manager.connect(mock_ws)

        assert mock_ws in manager.active_connections
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, manager):
        mock_ws = AsyncMock(spec=WebSocket)
        manager.active_connections.append(mock_ws)

        await manager.disconnect(mock_ws)

        assert mock_ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_not_in_list(self, manager):
        """Disconnecting a websocket not in the list should not raise."""
        mock_ws = AsyncMock(spec=WebSocket)
        await manager.disconnect(mock_ws)  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast(self, manager):
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        manager.active_connections = [mock_ws1, mock_ws2]

        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self, manager):
        mock_ws_good = AsyncMock(spec=WebSocket)
        mock_ws_bad = AsyncMock(spec=WebSocket)
        mock_ws_bad.send_json.side_effect = Exception("Connection closed")
        manager.active_connections = [mock_ws_good, mock_ws_bad]

        await manager.broadcast({"type": "test"})

        assert mock_ws_good in manager.active_connections
        assert mock_ws_bad not in manager.active_connections


class TestTripsState:
    """Tests for TripsState in-memory state management."""

    @pytest.fixture
    def state(self):
        return TripsState()

    def test_initial_state(self, state):
        assert state.points == {}
        assert state.nc is None
        assert state.js is None
        assert state.ready is False

    def test_get_points_empty(self, state):
        points = state.get_points()
        assert points == []

    def test_get_points_with_data(self, state):
        point1 = TripPoint(
            id="p1", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        point2 = TripPoint(
            id="p2", lat=46.0, lng=-123.0, timestamp="2024-01-15T11:00:00Z"
        )
        state.points = {"p1": point1, "p2": point2}

        points = state.get_points()
        assert len(points) == 2
        # Should be sorted by timestamp
        assert points[0].id == "p1"
        assert points[1].id == "p2"

    def test_get_points_with_limit(self, state):
        for i in range(5):
            state.points[f"p{i}"] = TripPoint(
                id=f"p{i}",
                lat=45.0 + i,
                lng=-122.0,
                timestamp=f"2024-01-15T{10 + i:02d}:00:00Z",
            )

        points = state.get_points(limit=3)
        assert len(points) == 3

    def test_get_points_with_offset(self, state):
        for i in range(5):
            state.points[f"p{i}"] = TripPoint(
                id=f"p{i}",
                lat=45.0 + i,
                lng=-122.0,
                timestamp=f"2024-01-15T{10 + i:02d}:00:00Z",
            )

        points = state.get_points(offset=2)
        assert len(points) == 3
        assert points[0].id == "p2"

    def test_get_point_exists(self, state):
        point = TripPoint(
            id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        state.points["test"] = point

        result = state.get_point("test")
        assert result == point

    def test_get_point_not_exists(self, state):
        result = state.get_point("nonexistent")
        assert result is None

    def test_get_stats(self, state):
        state.points = {
            "p1": TripPoint(
                id="p1", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
            )
        }

        stats = state.get_stats()
        assert stats["total_points"] == 1
        assert stats["connected_clients"] == 0

    @pytest.mark.asyncio
    async def test_process_message_valid(self, state):
        data = json.dumps(
            {
                "id": "test123",
                "lat": 45.0,
                "lng": -122.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        ).encode()

        result = await state._process_message(data)

        assert result is not None
        assert result.id == "test123"
        assert "test123" in state.points

    @pytest.mark.asyncio
    async def test_process_message_invalid_coords(self, state):
        """Messages with null island coordinates should be skipped."""
        data = json.dumps(
            {
                "id": "test123",
                "lat": 0.0,
                "lng": 0.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        ).encode()

        result = await state._process_message(data)

        assert result is None
        assert "test123" not in state.points

    @pytest.mark.asyncio
    async def test_process_message_tombstone(self, state):
        """Tombstone messages should delete points from cache."""
        # Add a point first
        state.points["test123"] = TripPoint(
            id="test123", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )

        # Send tombstone
        data = json.dumps({"id": "test123", "deleted": True}).encode()
        result = await state._process_message(data)

        assert result == {"id": "test123", "deleted": True}
        assert "test123" not in state.points

    @pytest.mark.asyncio
    async def test_process_message_invalid_json(self, state):
        result = await state._process_message(b"not valid json")
        assert result is None


class TestAPIEndpoints:
    """Tests for FastAPI endpoints."""

    def test_health_endpoint(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.ready = True
            mock_state.points = {"p1": MagicMock()}
            mock_state.manager.active_connections = []

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["points"] == 1

    def test_health_endpoint_not_ready(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.ready = False
            mock_state.points = {}
            mock_state.manager.active_connections = []

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "starting"

    def test_get_points_empty(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.get_points.return_value = []
            mock_state.points = {}

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points")

            assert response.status_code == 200
            data = response.json()
            assert data["points"] == []
            assert data["total"] == 0

    def test_get_points_with_data(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            point = TripPoint(
                id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
            )
            mock_state.get_points.return_value = [point]
            mock_state.points = {"test": point}

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points")

            assert response.status_code == 200
            data = response.json()
            assert len(data["points"]) == 1
            assert data["points"][0]["id"] == "test"

    def test_get_point_exists(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            point = TripPoint(
                id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
            )
            mock_state.get_point.return_value = point

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points/test")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "test"

    def test_get_point_not_found(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.get_point.return_value = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points/nonexistent")

            assert response.status_code == 404

    def test_get_stats(self):
        import projects.trips.backend.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.get_stats.return_value = {
                "total_points": 100,
                "connected_clients": 5,
            }

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_points"] == 100
            assert data["connected_clients"] == 5


class TestAPIKeyAuth:
    """Tests for API key authentication middleware."""

    def _make_client(self) -> TestClient:
        """Return a TestClient with a mocked global state."""
        return TestClient(app, raise_server_exceptions=False)

    def test_valid_key_accepted(self):
        """Requests with the correct API key should be accepted."""
        point = TripPoint(
            id="p1", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_points.return_value = [point]
            mock_state.points = {"p1": point}

            client = self._make_client()
            response = client.get("/api/points", headers={"X-API-Key": "secret-key"})

        assert response.status_code == 200

    def test_missing_key_rejected(self):
        """Requests without the X-API-Key header should receive 401."""
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_points.return_value = []
            mock_state.points = {}

            client = self._make_client()
            response = client.get("/api/points")

        assert response.status_code == 401

    def test_wrong_key_rejected(self):
        """Requests with an incorrect API key should receive 401."""
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_points.return_value = []
            mock_state.points = {}

            client = self._make_client()
            response = client.get("/api/points", headers={"X-API-Key": "wrong-key"})

        assert response.status_code == 401

    def test_auth_disabled_when_key_empty(self):
        """When TRIP_API_KEY is empty, all requests are allowed (dev mode)."""
        point = TripPoint(
            id="p1", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        with (
            patch.object(trips_main, "TRIP_API_KEY", ""),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_points.return_value = [point]
            mock_state.points = {"p1": point}

            client = self._make_client()
            # No X-API-Key header — should still work when key is unconfigured
            response = client.get("/api/points")

        assert response.status_code == 200

    def test_stats_endpoint_requires_auth(self):
        """The /api/stats endpoint also enforces API key auth."""
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_stats.return_value = {
                "total_points": 0,
                "connected_clients": 0,
            }

            client = self._make_client()
            # Missing key
            response = client.get("/api/stats")

        assert response.status_code == 401

    def test_single_point_endpoint_requires_auth(self):
        """The /api/points/{id} endpoint also enforces API key auth."""
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.get_point.return_value = None

            client = self._make_client()
            response = client.get("/api/points/nonexistent")

        assert response.status_code == 401

    def test_health_endpoint_always_public(self):
        """The /health endpoint is never gated by API key."""
        with (
            patch.object(trips_main, "TRIP_API_KEY", "secret-key"),
            patch.object(trips_main, "state") as mock_state,
        ):
            mock_state.ready = True
            mock_state.points = {}
            mock_state.manager.active_connections = []

            client = self._make_client()
            # No X-API-Key — health check must always be reachable
            response = client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_require_api_key_returns_empty_when_unconfigured(self):
        """require_api_key returns '' when TRIP_API_KEY is not set."""
        with patch.object(trips_main, "TRIP_API_KEY", ""):
            result = await require_api_key(api_key=None)
        assert result == ""

    @pytest.mark.asyncio
    async def test_require_api_key_raises_when_key_wrong(self):
        """require_api_key raises 401 when key doesn't match."""
        with patch.object(trips_main, "TRIP_API_KEY", "secret"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key="bad")
        assert exc_info.value.status_code == 401


class TestJetStreamReplay:
    """Tests for TripsState.replay_stream() and subscribe_live() methods."""

    @pytest.fixture
    def state(self):
        return TripsState()

    def _make_msg(self, data: dict):
        """Build a mock NATS message with .data bytes."""
        msg = MagicMock()
        msg.data = json.dumps(data).encode()
        msg.ack = AsyncMock()
        return msg

    @pytest.mark.asyncio
    async def test_replay_stream_builds_cache(self, state):
        """replay_stream should populate self.points from NATS messages."""
        point_data = {
            "id": "abc123",
            "lat": 45.0,
            "lng": -122.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        msg = self._make_msg(point_data)

        mock_consumer = AsyncMock()
        # First fetch returns one message; second raises TimeoutError to end the loop.
        mock_consumer.fetch = AsyncMock(
            side_effect=[[msg], __import__("nats").errors.TimeoutError()]
        )
        mock_consumer.unsubscribe = AsyncMock()

        state.js = AsyncMock()
        state.js.pull_subscribe = AsyncMock(return_value=mock_consumer)

        await state.replay_stream()

        assert "abc123" in state.points
        assert state.points["abc123"].lat == 45.0

    @pytest.mark.asyncio
    async def test_replay_stream_handles_stream_not_found(self, state):
        """replay_stream should handle StreamNotFoundError gracefully."""
        import nats

        state.js = AsyncMock()
        state.js.pull_subscribe = AsyncMock(side_effect=nats.js.errors.NotFoundError())

        # Should not raise; state should remain empty.
        await state.replay_stream()

        assert state.points == {}

    @pytest.mark.asyncio
    async def test_replay_stream_processes_multiple_messages(self, state):
        """replay_stream should process all messages fetched before TimeoutError."""
        msgs = [
            self._make_msg(
                {
                    "id": f"p{i}",
                    "lat": 45.0 + i,
                    "lng": -122.0,
                    "timestamp": f"2024-01-15T{10 + i:02d}:00:00Z",
                }
            )
            for i in range(3)
        ]

        mock_consumer = AsyncMock()
        mock_consumer.fetch = AsyncMock(
            side_effect=[msgs, __import__("nats").errors.TimeoutError()]
        )
        mock_consumer.unsubscribe = AsyncMock()

        state.js = AsyncMock()
        state.js.pull_subscribe = AsyncMock(return_value=mock_consumer)

        await state.replay_stream()

        assert len(state.points) == 3
        for i in range(3):
            assert f"p{i}" in state.points

    @pytest.mark.asyncio
    async def test_subscribe_live_sets_subscription(self, state):
        """subscribe_live should set self.subscription via js.subscribe."""
        mock_sub = MagicMock()
        mock_sub.messages = AsyncMock()

        state.js = AsyncMock()
        state.js.subscribe = AsyncMock(return_value=mock_sub)

        await state.subscribe_live()

        state.js.subscribe.assert_called_once()
        call_kwargs = state.js.subscribe.call_args
        # Subject should be trips.>
        assert call_kwargs[0][0] == "trips.>"
        assert state.subscription is mock_sub

    @pytest.mark.asyncio
    async def test_subscribe_live_uses_deliver_new_policy(self, state):
        """subscribe_live should use DeliverPolicy.NEW for live subscription."""
        import nats

        mock_sub = MagicMock()
        state.js = AsyncMock()
        state.js.subscribe = AsyncMock(return_value=mock_sub)

        await state.subscribe_live()

        call_kwargs = state.js.subscribe.call_args[1]
        config = call_kwargs.get("config")
        assert config is not None
        assert config.deliver_policy == nats.js.api.DeliverPolicy.NEW

    @pytest.mark.asyncio
    async def test_process_subscription_broadcasts_new_point(self, state):
        """_process_subscription should broadcast new_point events to WebSocket clients."""
        point_data = {
            "id": "ws_test",
            "lat": 48.0,
            "lng": -120.0,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        msg = self._make_msg(point_data)

        # Build an async generator that yields one message then stops.
        async def one_message():
            yield msg

        mock_sub = MagicMock()
        mock_sub.messages = one_message()
        state.subscription = mock_sub

        state.manager.broadcast = AsyncMock()

        await state._process_subscription()

        msg.ack.assert_called_once()
        state.manager.broadcast.assert_called_once()
        broadcast_call = state.manager.broadcast.call_args[0][0]
        assert broadcast_call["type"] == "new_point"
        assert broadcast_call["point"]["id"] == "ws_test"

    @pytest.mark.asyncio
    async def test_process_subscription_broadcasts_delete_for_tombstone(self, state):
        """_process_subscription should broadcast delete_point for tombstone messages."""
        # Pre-populate cache
        state.points["to_delete"] = TripPoint(
            id="to_delete", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )

        tombstone_msg = self._make_msg({"id": "to_delete", "deleted": True})

        async def one_message():
            yield tombstone_msg

        mock_sub = MagicMock()
        mock_sub.messages = one_message()
        state.subscription = mock_sub

        state.manager.broadcast = AsyncMock()

        await state._process_subscription()

        tombstone_msg.ack.assert_called_once()
        assert "to_delete" not in state.points
        broadcast_call = state.manager.broadcast.call_args[0][0]
        assert broadcast_call["type"] == "delete_point"
        assert broadcast_call["id"] == "to_delete"

    @pytest.mark.asyncio
    async def test_replay_stream_skips_invalid_coordinates(self, state):
        """replay_stream should skip messages with null island coordinates."""
        msg = self._make_msg(
            {
                "id": "null_island",
                "lat": 0.0,
                "lng": 0.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.fetch = AsyncMock(
            side_effect=[[msg], __import__("nats").errors.TimeoutError()]
        )
        mock_consumer.unsubscribe = AsyncMock()

        state.js = AsyncMock()
        state.js.pull_subscribe = AsyncMock(return_value=mock_consumer)

        await state.replay_stream()

        assert "null_island" not in state.points


class TestConnectionManagerAdditional:
    """Additional coverage for ConnectionManager viewer count and edge cases."""

    @pytest.fixture
    def manager(self):
        return ConnectionManager()

    @pytest.mark.asyncio
    async def test_broadcast_viewer_count_sends_correct_message(self, manager):
        """broadcast_viewer_count sends a viewer_count message with the current count."""
        mock_ws = AsyncMock(spec=WebSocket)
        manager.active_connections = [mock_ws]

        await manager.broadcast_viewer_count()

        mock_ws.send_json.assert_called_once_with({"type": "viewer_count", "count": 1})

    @pytest.mark.asyncio
    async def test_broadcast_viewer_count_empty_connections(self, manager):
        """broadcast_viewer_count with no connections should not raise."""
        await manager.broadcast_viewer_count()  # Should not raise
        assert manager.active_connections == []

    @pytest.mark.asyncio
    async def test_connect_broadcasts_viewer_count_to_new_connection(self, manager):
        """connect() broadcasts viewer_count after adding the connection."""
        mock_ws = AsyncMock(spec=WebSocket)

        await manager.connect(mock_ws)

        # The newly connected ws is in active_connections and receives the viewer_count
        mock_ws.send_json.assert_called_once_with({"type": "viewer_count", "count": 1})

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_viewer_count_to_remaining(self, manager):
        """disconnect() broadcasts updated viewer_count to remaining connections."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        manager.active_connections = [mock_ws1, mock_ws2]

        await manager.disconnect(mock_ws1)

        # mock_ws1 is removed; mock_ws2 should receive the updated count of 1
        mock_ws2.send_json.assert_called_once_with({"type": "viewer_count", "count": 1})
        assert mock_ws1 not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections_list(self, manager):
        """broadcast() with no connections should succeed without error."""
        await manager.broadcast({"type": "test", "data": "value"})
        assert manager.active_connections == []

    @pytest.mark.asyncio
    async def test_broadcast_viewer_count_reflects_multiple_connections(self, manager):
        """broadcast_viewer_count count matches active_connections length."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        mock_ws3 = AsyncMock(spec=WebSocket)
        manager.active_connections = [mock_ws1, mock_ws2, mock_ws3]

        await manager.broadcast_viewer_count()

        for ws in [mock_ws1, mock_ws2, mock_ws3]:
            ws.send_json.assert_called_once_with({"type": "viewer_count", "count": 3})


class TestTripsStateAdditional:
    """Additional coverage for TripsState: close, connect, pagination, stats."""

    @pytest.fixture
    def state(self):
        return TripsState()

    def test_get_points_with_limit_and_offset(self, state):
        """get_points with both limit and offset applies both constraints."""
        for i in range(10):
            state.points[f"p{i}"] = TripPoint(
                id=f"p{i}",
                lat=45.0 + i,
                lng=-122.0,
                timestamp=f"2024-01-15T{10 + i:02d}:00:00Z",
            )

        points = state.get_points(limit=3, offset=2)

        assert len(points) == 3
        assert points[0].id == "p2"
        assert points[1].id == "p3"
        assert points[2].id == "p4"

    def test_get_points_offset_beyond_length(self, state):
        """get_points with offset beyond total count returns empty list."""
        for i in range(3):
            state.points[f"p{i}"] = TripPoint(
                id=f"p{i}",
                lat=45.0 + i,
                lng=-122.0,
                timestamp=f"2024-01-15T{10 + i:02d}:00:00Z",
            )

        points = state.get_points(offset=10)
        assert points == []

    def test_get_stats_with_connected_clients(self, state):
        """get_stats should reflect the number of active WebSocket connections."""
        state.points = {
            "p1": TripPoint(
                id="p1", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
            )
        }
        mock_ws1 = MagicMock()
        mock_ws2 = MagicMock()
        state.manager.active_connections = [mock_ws1, mock_ws2]

        stats = state.get_stats()

        assert stats["total_points"] == 1
        assert stats["connected_clients"] == 2

    @pytest.mark.asyncio
    async def test_process_message_tombstone_for_nonexistent_point(self, state):
        """Tombstone for a point not in cache should return None (no error)."""
        data = json.dumps({"id": "does_not_exist", "deleted": True}).encode()

        result = await state._process_message(data)

        assert result is None
        assert "does_not_exist" not in state.points

    @pytest.mark.asyncio
    async def test_close_with_subscription_and_nc(self, state):
        """close() should call unsubscribe() on subscription and close() on nc."""
        mock_sub = AsyncMock()
        mock_nc = AsyncMock()
        state.subscription = mock_sub
        state.nc = mock_nc

        await state.close()

        mock_sub.unsubscribe.assert_called_once()
        mock_nc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self, state):
        """close() should handle None subscription and nc without raising."""
        assert state.subscription is None
        assert state.nc is None

        await state.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_connect_sets_ready_true(self, state):
        """connect() should set self.ready = True after successful startup."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch("nats.connect", return_value=mock_nc):
            state.replay_stream = AsyncMock()
            state.subscribe_live = AsyncMock()

            await state.connect()

        assert state.ready is True
        state.replay_stream.assert_called_once()
        state.subscribe_live.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_stores_nats_connection(self, state):
        """connect() should store the NATS connection in self.nc and self.js."""
        mock_nc = AsyncMock()
        mock_js = MagicMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)

        with patch("nats.connect", return_value=mock_nc):
            state.replay_stream = AsyncMock()
            state.subscribe_live = AsyncMock()

            await state.connect()

        assert state.nc is mock_nc
        assert state.js is mock_js


class TestJetStreamReplayAdditional:
    """Additional coverage for replay_stream, subscribe_live, _process_subscription."""

    @pytest.fixture
    def state(self):
        return TripsState()

    def _make_msg(self, data: dict):
        """Build a mock NATS message with .data bytes."""
        msg = MagicMock()
        msg.data = json.dumps(data).encode()
        msg.ack = AsyncMock()
        return msg

    @pytest.mark.asyncio
    async def test_replay_stream_handles_generic_exception(self, state):
        """replay_stream should catch non-NotFoundError exceptions and leave cache empty."""
        state.js = AsyncMock()
        state.js.pull_subscribe = AsyncMock(
            side_effect=RuntimeError("Unexpected NATS error")
        )

        await state.replay_stream()  # Should not raise

        assert state.points == {}

    @pytest.mark.asyncio
    async def test_subscribe_live_handles_subscribe_exception(self, state):
        """subscribe_live should log and return gracefully if js.subscribe raises."""
        state.js = AsyncMock()
        state.js.subscribe = AsyncMock(side_effect=RuntimeError("Subscribe failed"))

        await state.subscribe_live()  # Should not raise

        assert state.subscription is None

    @pytest.mark.asyncio
    async def test_subscribe_live_uses_hostname_env_var(self, state):
        """subscribe_live should derive the durable consumer name from HOSTNAME."""
        mock_sub = MagicMock()
        mock_sub.messages = AsyncMock()
        state.js = AsyncMock()
        state.js.subscribe = AsyncMock(return_value=mock_sub)

        with patch.dict(os.environ, {"HOSTNAME": "trips-pod-xyz789"}):
            await state.subscribe_live()

        call_kwargs = state.js.subscribe.call_args[1]
        assert call_kwargs.get("durable") == "trips-api-live-trips-pod-xyz789"

    @pytest.mark.asyncio
    async def test_subscribe_live_inactive_threshold_set(self, state):
        """subscribe_live should set inactive_threshold in consumer config."""
        import nats

        mock_sub = MagicMock()
        state.js = AsyncMock()
        state.js.subscribe = AsyncMock(return_value=mock_sub)

        await state.subscribe_live()

        call_kwargs = state.js.subscribe.call_args[1]
        config = call_kwargs.get("config")
        assert config is not None
        assert config.inactive_threshold == 3600.0

    @pytest.mark.asyncio
    async def test_process_subscription_no_broadcast_for_none_point(self, state):
        """_process_subscription should not broadcast when _process_message returns None."""
        # Null island coords → _process_message returns None
        msg = self._make_msg(
            {
                "id": "null_island",
                "lat": 0.0,
                "lng": 0.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        )

        async def one_message():
            yield msg

        mock_sub = MagicMock()
        mock_sub.messages = one_message()
        state.subscription = mock_sub
        state.manager.broadcast = AsyncMock()

        await state._process_subscription()

        msg.ack.assert_called_once()
        state.manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_subscription_continues_after_bad_message(self, state):
        """Messages with invalid JSON are skipped; subsequent valid messages are processed."""
        invalid_msg = MagicMock()
        invalid_msg.data = b"not valid json {{{"
        invalid_msg.ack = AsyncMock()

        valid_msg = self._make_msg(
            {
                "id": "good_point",
                "lat": 45.0,
                "lng": -122.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        )

        async def two_messages():
            yield invalid_msg
            yield valid_msg

        mock_sub = MagicMock()
        mock_sub.messages = two_messages()
        state.subscription = mock_sub
        state.manager.broadcast = AsyncMock()

        await state._process_subscription()

        # Both messages are acked (invalid JSON returns None from _process_message)
        invalid_msg.ack.assert_called_once()
        valid_msg.ack.assert_called_once()

        # Only the valid point is broadcast
        state.manager.broadcast.assert_called_once()
        broadcast_call = state.manager.broadcast.call_args[0][0]
        assert broadcast_call["type"] == "new_point"
        assert broadcast_call["point"]["id"] == "good_point"

    @pytest.mark.asyncio
    async def test_process_subscription_exception_in_ack_does_not_stop_loop(
        self, state
    ):
        """If msg.ack() raises, the error is logged and processing continues."""
        failing_msg = self._make_msg(
            {
                "id": "ack_fails",
                "lat": 45.0,
                "lng": -122.0,
                "timestamp": "2024-01-15T10:00:00Z",
            }
        )
        failing_msg.ack = AsyncMock(side_effect=RuntimeError("ACK error"))

        valid_msg = self._make_msg(
            {
                "id": "ack_succeeds",
                "lat": 46.0,
                "lng": -123.0,
                "timestamp": "2024-01-15T11:00:00Z",
            }
        )

        async def two_messages():
            yield failing_msg
            yield valid_msg

        mock_sub = MagicMock()
        mock_sub.messages = two_messages()
        state.subscription = mock_sub
        state.manager.broadcast = AsyncMock()

        await state._process_subscription()

        # Despite the ack failure, the second message was still processed
        valid_msg.ack.assert_called_once()
        # The second broadcast should have the valid point
        last_call = state.manager.broadcast.call_args_list[-1][0][0]
        assert last_call["type"] == "new_point"
        assert last_call["point"]["id"] == "ack_succeeds"


class TestWebSocketEndpoint:
    """Tests for the WebSocket /ws/live endpoint."""

    def test_websocket_receives_connected_message(self):
        """Connecting via WebSocket should yield a 'connected' message with cached point count."""
        real_manager = ConnectionManager()
        with patch.object(trips_main, "state") as mock_state:
            mock_state.points = {"p1": MagicMock(), "p2": MagicMock()}
            mock_state.manager = real_manager

            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect("/ws/live") as ws:
                # First: viewer_count broadcast from connect()
                viewer_msg = ws.receive_json()
                assert viewer_msg["type"] == "viewer_count"
                assert viewer_msg["count"] == 1

                # Second: the endpoint sends the "connected" message
                connected_msg = ws.receive_json()
                assert connected_msg["type"] == "connected"
                assert connected_msg["cached_points"] == 2

    def test_websocket_ping_pong_keepalive(self):
        """Sending 'ping' over the WebSocket should receive 'pong' in response."""
        real_manager = ConnectionManager()
        with patch.object(trips_main, "state") as mock_state:
            mock_state.points = {}
            mock_state.manager = real_manager

            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()  # viewer_count
                ws.receive_json()  # connected

                ws.send_text("ping")
                response = ws.receive_text()
                assert response == "pong"

    def test_websocket_non_ping_message_ignored(self):
        """Non-ping text messages should not cause an error and receive no response."""
        real_manager = ConnectionManager()
        with patch.object(trips_main, "state") as mock_state:
            mock_state.points = {}
            mock_state.manager = real_manager

            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()  # viewer_count
                ws.receive_json()  # connected

                # Send a non-ping message — the loop continues without sending a response
                ws.send_text("hello")
                # Send ping immediately after to verify the loop is still alive
                ws.send_text("ping")
                response = ws.receive_text()
                assert response == "pong"

    def test_websocket_disconnect_removes_from_active_connections(self):
        """After the WebSocket closes, the connection should be removed from active_connections."""
        real_manager = ConnectionManager()
        with patch.object(trips_main, "state") as mock_state:
            mock_state.points = {}
            mock_state.manager = real_manager

            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()  # viewer_count
                ws.receive_json()  # connected
                assert len(real_manager.active_connections) == 1

        # Connection should be cleaned up after the context exits
        assert len(real_manager.active_connections) == 0

    def test_websocket_cached_points_count_zero_when_empty(self):
        """connected message should report cached_points=0 when state.points is empty."""
        real_manager = ConnectionManager()
        with patch.object(trips_main, "state") as mock_state:
            mock_state.points = {}
            mock_state.manager = real_manager

            client = TestClient(app, raise_server_exceptions=False)
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()  # viewer_count
                connected_msg = ws.receive_json()
                assert connected_msg["cached_points"] == 0


class TestRequireApiKeyAdditional:
    """Additional direct tests for the require_api_key dependency."""

    @pytest.mark.asyncio
    async def test_require_api_key_returns_key_when_valid(self):
        """require_api_key should return the provided key when it matches TRIP_API_KEY."""
        with patch.object(trips_main, "TRIP_API_KEY", "my-secret-key"):
            result = await require_api_key(api_key="my-secret-key")
        assert result == "my-secret-key"

    @pytest.mark.asyncio
    async def test_require_api_key_raises_when_key_is_none(self):
        """require_api_key raises 401 when no key is provided but auth is configured."""
        with patch.object(trips_main, "TRIP_API_KEY", "configured-key"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_api_key_raises_when_key_empty_string(self):
        """require_api_key raises 401 when empty string key is sent but auth is configured."""
        with patch.object(trips_main, "TRIP_API_KEY", "configured-key"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key="")
        assert exc_info.value.status_code == 401


class TestTripPointAdditional:
    """Additional coverage for TripPoint model defaults and edge cases."""

    def test_default_source_is_gopro(self):
        """TripPoint source field defaults to 'gopro'."""
        point = TripPoint(
            id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        assert point.source == "gopro"

    def test_default_tags_is_car(self):
        """TripPoint tags field defaults to ['car']."""
        point = TripPoint(
            id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        assert point.tags == ["car"]

    def test_all_optional_fields_default_to_none(self):
        """All optional fields on TripPoint default to None."""
        point = TripPoint(
            id="test", lat=45.0, lng=-122.0, timestamp="2024-01-15T10:00:00Z"
        )
        assert point.image is None
        assert point.elevation is None
        assert point.light_value is None
        assert point.iso is None
        assert point.shutter_speed is None
        assert point.aperture is None
        assert point.focal_length_35mm is None

    def test_gap_source_and_no_image(self):
        """A gap point has source='gap' and no image."""
        point = TripPoint(
            id="gap1",
            lat=62.0,
            lng=-135.0,
            timestamp="2024-06-01T08:00:00Z",
            source="gap",
            image=None,
        )
        assert point.source == "gap"
        assert point.image is None

    def test_multiple_tags(self):
        """TripPoint can store multiple tags."""
        point = TripPoint(
            id="tagged",
            lat=45.0,
            lng=-122.0,
            timestamp="2024-01-15T10:00:00Z",
            tags=["hike", "mountain", "wildlife"],
        )
        assert point.tags == ["hike", "mountain", "wildlife"]

    def test_model_dump_includes_all_fields(self):
        """model_dump() should include all fields including optional ones set to None."""
        point = TripPoint(
            id="dump_test",
            lat=45.0,
            lng=-122.0,
            timestamp="2024-01-15T10:00:00Z",
        )
        dumped = point.model_dump()
        assert "id" in dumped
        assert "lat" in dumped
        assert "lng" in dumped
        assert "timestamp" in dumped
        assert "image" in dumped
        assert "elevation" in dumped
        assert "iso" in dumped
