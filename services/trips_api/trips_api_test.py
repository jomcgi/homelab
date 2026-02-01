"""Tests for Trips API service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from services.trips_api.main import (
    ConnectionManager,
    TripPoint,
    TripsState,
    app,
    is_valid_coordinates,
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
        import services.trips_api.main as main

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
        import services.trips_api.main as main

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
        import services.trips_api.main as main

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
        import services.trips_api.main as main

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
        import services.trips_api.main as main

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
        import services.trips_api.main as main

        with patch.object(main, "state") as mock_state:
            mock_state.get_point.return_value = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points/nonexistent")

            assert response.status_code == 404

    def test_get_stats(self):
        import services.trips_api.main as main

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
