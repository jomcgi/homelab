"""Unit tests for backend/main.py — supplementing trips_api_test.py.

Covers gaps not addressed by the existing test file:
- require_api_key: auth enforcement when TRIP_API_KEY is configured
- TripsState.get_points: limit/offset pagination and sort order
- TripsState.get_point: miss path
- TripsState.get_stats: correct shape
- TripsState._process_message: tombstone for unknown id, invalid JSON
- /health endpoint: ready vs starting state
- ConnectionManager: broadcast removes dead connections
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin
from fastapi import HTTPException
from fastapi.testclient import TestClient

import projects.trips.backend.main as trips_main
from projects.trips.backend.main import (
    ConnectionManager,
    TripPoint,
    TripsState,
    app,
    require_api_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_point(pid: str, ts: str, lat: float = 45.0, lng: float = -122.0) -> TripPoint:
    return TripPoint(
        id=pid,
        lat=lat,
        lng=lng,
        timestamp=ts,
        source="gopro",
        tags=["car"],
    )


# ---------------------------------------------------------------------------
# require_api_key
# ---------------------------------------------------------------------------


class TestRequireApiKey:
    """API key enforcement when TRIP_API_KEY is configured."""

    @pytest.mark.asyncio
    async def test_no_key_configured_allows_any_request(self):
        """When TRIP_API_KEY is empty, all requests pass through."""
        with patch.object(trips_main, "TRIP_API_KEY", ""):
            result = await require_api_key(api_key=None)
        assert result == ""

    @pytest.mark.asyncio
    async def test_valid_key_passes(self):
        """Correct API key is accepted."""
        with patch.object(trips_main, "TRIP_API_KEY", "secret-key"):
            result = await require_api_key(api_key="secret-key")
        assert result == "secret-key"

    @pytest.mark.asyncio
    async def test_invalid_key_raises_401(self):
        """Wrong API key raises HTTPException(401)."""
        with patch.object(trips_main, "TRIP_API_KEY", "secret-key"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key="wrong-key")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_key_raises_401_when_key_configured(self):
        """Missing X-API-Key header raises 401 when a key is configured."""
        with patch.object(trips_main, "TRIP_API_KEY", "secret-key"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_string_key_rejected_when_key_configured(self):
        """Empty string key is rejected when TRIP_API_KEY is set."""
        with patch.object(trips_main, "TRIP_API_KEY", "secret-key"):
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key="")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# TripsState.get_points — pagination and sort order
# ---------------------------------------------------------------------------


class TestTripsStateGetPoints:
    """In-memory point retrieval with pagination."""

    def _state_with_points(self, *timestamps: str) -> TripsState:
        state = TripsState()
        for i, ts in enumerate(timestamps):
            state.points[f"p{i}"] = _make_point(f"p{i}", ts)
        return state

    def test_returns_all_points_by_default(self):
        state = self._state_with_points(
            "2025-01-01T10:00:00",
            "2025-01-01T11:00:00",
            "2025-01-01T12:00:00",
        )
        points = state.get_points()
        assert len(points) == 3

    def test_points_sorted_by_timestamp_ascending(self):
        state = self._state_with_points(
            "2025-01-01T12:00:00",
            "2025-01-01T10:00:00",
            "2025-01-01T11:00:00",
        )
        points = state.get_points()
        timestamps = [p.timestamp for p in points]
        assert timestamps == sorted(timestamps)

    def test_limit_restricts_result_count(self):
        state = self._state_with_points(
            "2025-01-01T10:00:00",
            "2025-01-01T11:00:00",
            "2025-01-01T12:00:00",
        )
        points = state.get_points(limit=2)
        assert len(points) == 2

    def test_offset_skips_leading_points(self):
        state = self._state_with_points(
            "2025-01-01T10:00:00",
            "2025-01-01T11:00:00",
            "2025-01-01T12:00:00",
        )
        # Sorted order: p0@10, p1@11, p2@12 → skip 1 → p1, p2
        points = state.get_points(offset=1)
        assert len(points) == 2

    def test_limit_and_offset_combined(self):
        state = self._state_with_points(
            "2025-01-01T10:00:00",
            "2025-01-01T11:00:00",
            "2025-01-01T12:00:00",
            "2025-01-01T13:00:00",
        )
        points = state.get_points(limit=2, offset=1)
        assert len(points) == 2

    def test_empty_state_returns_empty_list(self):
        state = TripsState()
        assert state.get_points() == []

    def test_limit_larger_than_count_returns_all(self):
        state = self._state_with_points("2025-01-01T10:00:00")
        points = state.get_points(limit=100)
        assert len(points) == 1


# ---------------------------------------------------------------------------
# TripsState.get_point — single point lookup
# ---------------------------------------------------------------------------


class TestTripsStateGetPoint:
    """Single point lookup by ID."""

    def test_returns_point_for_known_id(self):
        state = TripsState()
        p = _make_point("abc", "2025-01-01T10:00:00")
        state.points["abc"] = p
        result = state.get_point("abc")
        assert result is p

    def test_returns_none_for_unknown_id(self):
        state = TripsState()
        assert state.get_point("nonexistent") is None

    def test_returns_none_for_empty_state(self):
        state = TripsState()
        assert state.get_point("anything") is None


# ---------------------------------------------------------------------------
# TripsState.get_stats
# ---------------------------------------------------------------------------


class TestTripsStateGetStats:
    """Statistics dictionary shape."""

    def test_returns_total_points(self):
        state = TripsState()
        state.points["a"] = _make_point("a", "2025-01-01T10:00:00")
        state.points["b"] = _make_point("b", "2025-01-01T11:00:00")
        stats = state.get_stats()
        assert stats["total_points"] == 2

    def test_returns_connected_clients(self):
        state = TripsState()
        stats = state.get_stats()
        assert "connected_clients" in stats
        assert stats["connected_clients"] == 0

    def test_empty_state_returns_zero_totals(self):
        state = TripsState()
        stats = state.get_stats()
        assert stats["total_points"] == 0
        assert stats["connected_clients"] == 0


# ---------------------------------------------------------------------------
# TripsState._process_message
# ---------------------------------------------------------------------------


class TestTripsStateProcessMessage:
    """Message processing: normal, tombstone, invalid."""

    @pytest.mark.asyncio
    async def test_valid_point_added_to_cache(self):
        state = TripsState()
        data = json.dumps(
            {
                "id": "p1",
                "lat": 45.0,
                "lng": -122.0,
                "timestamp": "2025-01-01T10:00:00",
                "source": "gopro",
                "tags": ["car"],
            }
        ).encode()
        result = await state._process_message(data)
        assert result is not None
        assert "p1" in state.points

    @pytest.mark.asyncio
    async def test_tombstone_removes_existing_point(self):
        state = TripsState()
        state.points["p1"] = _make_point("p1", "2025-01-01T10:00:00")
        data = json.dumps({"id": "p1", "deleted": True}).encode()
        result = await state._process_message(data)
        assert isinstance(result, dict)
        assert result.get("deleted") is True
        assert "p1" not in state.points

    @pytest.mark.asyncio
    async def test_tombstone_for_unknown_id_returns_none(self):
        """Deleting an ID that's not in the cache should return None."""
        state = TripsState()
        data = json.dumps({"id": "unknown-id", "deleted": True}).encode()
        result = await state._process_message(data)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self):
        state = TripsState()
        result = await state._process_message(b"not valid json {{{")
        assert result is None

    @pytest.mark.asyncio
    async def test_null_island_coordinates_rejected(self):
        """Points at (0, 0) are GPS errors and must be skipped."""
        state = TripsState()
        data = json.dumps(
            {
                "id": "bad",
                "lat": 0.0,
                "lng": 0.0,
                "timestamp": "2025-01-01T10:00:00",
                "source": "gopro",
                "tags": [],
            }
        ).encode()
        result = await state._process_message(data)
        assert result is None
        assert "bad" not in state.points

    @pytest.mark.asyncio
    async def test_out_of_range_lat_rejected(self):
        state = TripsState()
        data = json.dumps(
            {
                "id": "bad2",
                "lat": 200.0,
                "lng": -122.0,
                "timestamp": "2025-01-01T10:00:00",
                "source": "gopro",
                "tags": [],
            }
        ).encode()
        result = await state._process_message(data)
        assert result is None


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Health check reflects ready state."""

    def test_health_returns_starting_when_not_ready(self):
        state = TripsState()
        state.ready = False

        with patch.object(trips_main, "state", state):
            client = TestClient(app)
            response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "starting"

    def test_health_returns_healthy_when_ready(self):
        state = TripsState()
        state.ready = True

        with patch.object(trips_main, "state", state):
            client = TestClient(app)
            response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"

    def test_health_includes_point_count(self):
        state = TripsState()
        state.ready = True
        state.points["p1"] = _make_point("p1", "2025-01-01T10:00:00")

        with patch.object(trips_main, "state", state):
            client = TestClient(app)
            response = client.get("/health")

        assert response.json()["points"] == 1

    def test_health_no_auth_required(self):
        """The /health endpoint must be publicly accessible."""
        state = TripsState()
        state.ready = True

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", "secret"),
        ):
            client = TestClient(app)
            response = client.get("/health")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /api/points and /api/points/{id} via TestClient
# ---------------------------------------------------------------------------


class TestApiPointsEndpoints:
    """REST endpoint behaviour via FastAPI TestClient."""

    def _state_with_auth_disabled(self, points: list[TripPoint]) -> TripsState:
        state = TripsState()
        for p in points:
            state.points[p.id] = p
        state.ready = True
        return state

    def test_get_points_returns_all_points(self):
        state = self._state_with_auth_disabled(
            [
                _make_point("a", "2025-01-01T10:00:00"),
                _make_point("b", "2025-01-01T11:00:00"),
            ]
        )
        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", ""),
        ):
            client = TestClient(app)
            response = client.get("/api/points")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["points"]) == 2

    def test_get_point_by_id_found(self):
        p = _make_point("abc123", "2025-01-01T10:00:00")
        state = self._state_with_auth_disabled([p])

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", ""),
        ):
            client = TestClient(app)
            response = client.get("/api/points/abc123")

        assert response.status_code == 200
        assert response.json()["id"] == "abc123"

    def test_get_point_by_id_not_found_returns_404(self):
        state = self._state_with_auth_disabled([])

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", ""),
        ):
            client = TestClient(app)
            response = client.get("/api/points/nonexistent")

        assert response.status_code == 404

    def test_get_stats_returns_correct_shape(self):
        state = self._state_with_auth_disabled(
            [_make_point("a", "2025-01-01T10:00:00")]
        )

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", ""),
        ):
            client = TestClient(app)
            response = client.get("/api/stats")

        assert response.status_code == 200
        body = response.json()
        assert body["total_points"] == 1
        assert "connected_clients" in body

    def test_get_points_requires_api_key_when_configured(self):
        state = self._state_with_auth_disabled([])

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", "my-secret"),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/points")

        assert response.status_code == 401

    def test_get_points_succeeds_with_correct_api_key(self):
        state = self._state_with_auth_disabled([])

        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", "my-secret"),
        ):
            client = TestClient(app)
            response = client.get("/api/points", headers={"X-API-Key": "my-secret"})

        assert response.status_code == 200

    def test_get_points_with_limit_param(self):
        state = self._state_with_auth_disabled(
            [
                _make_point("a", "2025-01-01T10:00:00"),
                _make_point("b", "2025-01-01T11:00:00"),
                _make_point("c", "2025-01-01T12:00:00"),
            ]
        )
        with (
            patch.object(trips_main, "state", state),
            patch.object(trips_main, "TRIP_API_KEY", ""),
        ):
            client = TestClient(app)
            response = client.get("/api/points?limit=2")

        assert response.status_code == 200
        body = response.json()
        assert len(body["points"]) == 2
        assert body["total"] == 3  # total is always the full count


# ---------------------------------------------------------------------------
# ConnectionManager.broadcast
# ---------------------------------------------------------------------------


class TestConnectionManagerBroadcast:
    """Broadcast removes dead WebSocket connections."""

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connection(self):
        """A connection that raises on send_json is removed from active_connections."""
        manager = ConnectionManager()

        dead_ws = MagicMock()
        dead_ws.send_json = AsyncMock(side_effect=Exception("disconnected"))
        healthy_ws = MagicMock()
        healthy_ws.send_json = AsyncMock()

        manager.active_connections = [dead_ws, healthy_ws]

        await manager.broadcast({"type": "test"})

        assert dead_ws not in manager.active_connections
        assert healthy_ws in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_connections_does_not_raise(self):
        manager = ConnectionManager()
        await manager.broadcast({"type": "test"})  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_viewer_count_sends_count(self):
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager.active_connections = [ws]

        await manager.broadcast_viewer_count()

        ws.send_json.assert_awaited_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "viewer_count"
        assert msg["count"] == 1
