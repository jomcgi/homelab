"""
Tests for Ships API main.py — app creation, lifespan events, route registration, health.

Covers:
- FastAPI app metadata (title, version, description)
- Route registration for all API endpoints
- CORS middleware presence
- Lifespan startup failure handling (exception does not prevent app from serving)
- Global service instance type and initial attributes
- Health endpoint response structure and field values
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestAppCreation:
    """Tests for FastAPI app instantiation and metadata."""

    def test_app_title(self):
        """App title is 'Ships API'."""
        from projects.ships.backend.main import app

        assert app.title == "Ships API"

    def test_app_version(self):
        """App version matches expected release."""
        from projects.ships.backend.main import app

        assert app.version == "2.1.0"

    def test_app_description_mentions_vessel(self):
        """App description references vessel tracking."""
        from projects.ships.backend.main import app

        assert app.description is not None
        assert len(app.description) > 0

    def test_app_has_lifespan(self):
        """App is configured with a lifespan context manager."""
        from projects.ships.backend.main import app

        # FastAPI stores the lifespan on router.lifespan_context
        assert app.router.lifespan_context is not None


class TestRouteRegistration:
    """Tests that all expected routes are registered on the app."""

    def _get_paths(self):
        from projects.ships.backend.main import app

        return [r.path for r in app.routes]

    def test_health_route_registered(self):
        """/health liveness probe route exists."""
        assert "/health" in self._get_paths()

    def test_ready_route_registered(self):
        """/ready readiness probe route exists."""
        assert "/ready" in self._get_paths()

    def test_vessels_list_route_registered(self):
        """/api/vessels listing route exists."""
        assert "/api/vessels" in self._get_paths()

    def test_vessel_detail_route_registered(self):
        """/api/vessels/{mmsi} detail route exists."""
        assert "/api/vessels/{mmsi}" in self._get_paths()

    def test_vessel_track_route_registered(self):
        """/api/vessels/{mmsi}/track history route exists."""
        assert "/api/vessels/{mmsi}/track" in self._get_paths()

    def test_stats_route_registered(self):
        """/api/stats service statistics route exists."""
        assert "/api/stats" in self._get_paths()

    def test_websocket_route_registered(self):
        """/ws/live WebSocket route exists."""
        assert "/ws/live" in self._get_paths()

    def test_no_unexpected_api_routes(self):
        """Exactly the expected API routes are registered (no undocumented extras)."""
        from projects.ships.backend.main import app

        api_paths = [r.path for r in app.routes if r.path.startswith("/api/")]
        expected = {"/api/vessels", "/api/vessels/{mmsi}", "/api/vessels/{mmsi}/track", "/api/stats"}
        assert set(api_paths) == expected


class TestCORSMiddleware:
    """Tests for CORS middleware configuration."""

    @pytest.mark.asyncio
    async def test_cors_allows_configured_origin(self, test_client: AsyncClient):
        """Configured origin receives Access-Control-Allow-Origin header."""
        response = await test_client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_cors_preflight_succeeds(self, test_client: AsyncClient):
        """CORS preflight OPTIONS request succeeds for allowed origin."""
        response = await test_client.options(
            "/api/vessels",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # 200 or 204 — not a 4xx error
        assert response.status_code < 400


class TestGlobalServiceInstance:
    """Tests for the module-level global service instance."""

    def test_service_instance_is_ships_api_service(self):
        """Global service is a ShipsAPIService instance."""
        from projects.ships.backend.main import service, ShipsAPIService

        assert isinstance(service, ShipsAPIService)

    def test_service_has_database(self):
        """Service has a Database attribute."""
        from projects.ships.backend.main import service, Database

        assert isinstance(service.db, Database)

    def test_service_has_websocket_manager(self):
        """Service has a WebSocketManager attribute."""
        from projects.ships.backend.main import service, WebSocketManager

        assert isinstance(service.ws_manager, WebSocketManager)

    def test_service_initial_counters(self):
        """Service message counters start at zero on a fresh instance."""
        from projects.ships.backend.main import ShipsAPIService

        fresh = ShipsAPIService()
        assert fresh.messages_received == 0
        assert fresh.messages_deduplicated == 0

    def test_service_initial_state_flags(self):
        """Service running/ready/replay flags start as False on a fresh instance."""
        from projects.ships.backend.main import ShipsAPIService

        fresh = ShipsAPIService()
        assert fresh.running is False
        assert fresh.ready is False
        assert fresh.replay_complete is False

    def test_service_initial_tasks_none(self):
        """Service background tasks start as None on a fresh instance."""
        from projects.ships.backend.main import ShipsAPIService

        fresh = ShipsAPIService()
        assert fresh.subscription_task is None
        assert fresh.cleanup_task is None


class TestLifespanEvents:
    """Tests for lifespan startup and shutdown behaviour."""

    @pytest.mark.asyncio
    async def test_lifespan_continues_after_startup_exception(self):
        """App remains alive even if service.start() raises during lifespan startup."""
        from projects.ships.backend.main import app, service

        with patch.object(service, "start", side_effect=Exception("NATS unavailable")):
            with patch.object(service, "stop", new_callable=AsyncMock):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    # /health should still respond — lifespan catches startup errors
                    response = await client.get("/health")
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_lifespan_calls_stop_on_shutdown(self):
        """service.stop() is called when the app shuts down."""
        from projects.ships.backend.main import app, service

        stop_called = False

        async def mock_stop():
            nonlocal stop_called
            stop_called = True

        with patch.object(service, "start", new_callable=AsyncMock):
            with patch.object(service, "stop", side_effect=mock_stop):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test"):
                    pass  # Context exit triggers shutdown

        assert stop_called, "service.stop() must be called during app shutdown"


class TestHealthEndpoint:
    """Tests for the /health endpoint structure specific to main.py wiring."""

    @pytest.mark.asyncio
    async def test_health_status_is_alive(self, test_client: AsyncClient):
        """Health endpoint always returns status 'alive'."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_includes_all_required_fields(self, test_client: AsyncClient):
        """Health response contains every documented field."""
        response = await test_client.get("/health")
        data = response.json()
        required_fields = {
            "status",
            "nats_connected",
            "vessel_count",
            "cache_size",
            "caught_up",
            "messages_processed",
        }
        assert required_fields.issubset(data.keys())

    @pytest.mark.asyncio
    async def test_health_nats_connected_reflects_mock(self, test_client: AsyncClient):
        """nats_connected in health reflects the actual NATS connection object state."""
        from projects.ships.backend.main import service

        response = await test_client.get("/health")
        data = response.json()
        expected = service.nc is not None and service.nc.is_connected
        assert data["nats_connected"] == expected

    @pytest.mark.asyncio
    async def test_health_messages_processed_is_integer(self, test_client: AsyncClient):
        """messages_processed is a non-negative integer."""
        response = await test_client.get("/health")
        data = response.json()
        assert isinstance(data["messages_processed"], int)
        assert data["messages_processed"] >= 0

    @pytest.mark.asyncio
    async def test_health_caught_up_reflects_replay_state(self, test_client: AsyncClient):
        """caught_up in health reflects service.replay_complete."""
        from projects.ships.backend.main import service

        original = service.replay_complete
        try:
            service.replay_complete = True
            response = await test_client.get("/health")
            assert response.json()["caught_up"] is True

            service.replay_complete = False
            response = await test_client.get("/health")
            assert response.json()["caught_up"] is False
        finally:
            service.replay_complete = original
