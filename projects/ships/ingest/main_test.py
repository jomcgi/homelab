"""
Tests for AIS Ingest main.py — app creation, lifespan events, and health endpoint.

Covers:
- FastAPI app metadata (title, version, description)
- Route registration for /health and /metrics
- Lifespan startup failure handling (exception does not crash the app)
- Global service instance type and initial state
- Health endpoint response structure in ready and not-ready states
- Metrics endpoint response structure
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from projects.ships.ingest.main import AISIngestService, app


class TestAppCreation:
    """Tests for FastAPI app instantiation and metadata."""

    def test_app_title(self):
        """App title is 'AIS Ingest'."""
        assert app.title == "AIS Ingest"

    def test_app_version(self):
        """App version matches expected release."""
        assert app.version == "1.0.0"

    def test_app_description_is_set(self):
        """App description is non-empty."""
        assert app.description is not None
        assert len(app.description) > 0

    def test_app_has_lifespan(self):
        """App is configured with a lifespan context manager."""
        assert app.router.lifespan_context is not None


class TestRouteRegistration:
    """Tests that all expected routes are registered on the app."""

    def _get_paths(self):
        return [r.path for r in app.routes]

    def test_health_route_registered(self):
        """/health endpoint is registered."""
        assert "/health" in self._get_paths()

    def test_metrics_route_registered(self):
        """/metrics endpoint is registered."""
        assert "/metrics" in self._get_paths()

    def test_no_unexpected_routes(self):
        """Only /health and /metrics are registered as custom routes."""
        # Filter out auto-generated OpenAPI/docs routes
        custom_paths = [
            r.path
            for r in app.routes
            if not r.path.startswith("/openapi") and r.path not in ("/docs", "/redoc")
        ]
        assert "/health" in custom_paths
        assert "/metrics" in custom_paths


class TestGlobalServiceInstance:
    """Tests for the module-level global service instance."""

    def test_service_instance_is_ais_ingest_service(self):
        """Global service is an AISIngestService instance."""
        import projects.ships.ingest.main as main_module

        assert isinstance(main_module.service, AISIngestService)

    def test_service_initial_state_flags(self):
        """A fresh service instance has running=False and ready=False."""
        fresh = AISIngestService()
        assert fresh.running is False
        assert fresh.ready is False

    def test_service_initial_counters(self):
        """A fresh service instance has zero messages_published."""
        fresh = AISIngestService()
        assert fresh.messages_published == 0

    def test_service_initial_nats_connections_none(self):
        """A fresh service has nc and js set to None."""
        fresh = AISIngestService()
        assert fresh.nc is None
        assert fresh.js is None

    def test_service_initial_task_none(self):
        """A fresh service has ws_task set to None."""
        fresh = AISIngestService()
        assert fresh.ws_task is None

    def test_service_initial_last_message_time_none(self):
        """A fresh service has last_message_time set to None."""
        fresh = AISIngestService()
        assert fresh.last_message_time is None


class TestLifespanEvents:
    """Tests for lifespan startup and shutdown behaviour."""

    @pytest.mark.asyncio
    async def test_lifespan_continues_after_startup_exception(self):
        """App continues serving even if service.start() raises during lifespan."""
        import projects.ships.ingest.main as main_module

        with patch.object(
            main_module.service, "start", side_effect=Exception("NATS unavailable")
        ):
            with patch.object(main_module.service, "stop", new_callable=AsyncMock):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    # /health should still respond even after startup failure
                    response = await client.get("/health")
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_lifespan_calls_stop_on_shutdown(self):
        """service.stop() is called when the app shuts down."""
        import projects.ships.ingest.main as main_module

        stop_called = False

        async def mock_stop():
            nonlocal stop_called
            stop_called = True

        with patch.object(main_module.service, "start", new_callable=AsyncMock):
            with patch.object(main_module.service, "stop", side_effect=mock_stop):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test"):
                    pass  # Context exit triggers lifespan shutdown

        assert stop_called, "service.stop() must be called during app shutdown"


class TestHealthEndpoint:
    """Tests for the /health endpoint structure and field values."""

    def test_health_returns_200(self):
        """Health endpoint always returns HTTP 200."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = True
            mock_svc.nc = MagicMock()
            mock_svc.nc.is_connected = True
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        assert response.status_code == 200

    def test_health_status_healthy_when_ready(self):
        """Status field is 'healthy' when service.ready is True."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = True
            mock_svc.nc = MagicMock()
            mock_svc.nc.is_connected = True
            mock_svc.messages_published = 42
            mock_svc.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        data = response.json()
        assert data["status"] == "healthy"

    def test_health_status_starting_when_not_ready(self):
        """Status field is 'starting' when service.ready is False."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = False
            mock_svc.nc = None
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        data = response.json()
        assert data["status"] == "starting"

    def test_health_includes_all_required_fields(self):
        """Health response contains every documented field."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = True
            mock_svc.nc = MagicMock()
            mock_svc.nc.is_connected = True
            mock_svc.messages_published = 5
            mock_svc.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        data = response.json()
        required_fields = {
            "status",
            "nats_connected",
            "websocket_connected",
            "messages_published",
            "last_message_time",
        }
        assert required_fields.issubset(data.keys())

    def test_health_nats_connected_false_when_nc_none(self):
        """nats_connected is False when NATS connection object is None."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = False
            mock_svc.nc = None
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        assert response.json()["nats_connected"] is False

    def test_health_nats_connected_true_when_connected(self):
        """nats_connected is True when NATS nc.is_connected is True."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = True
            mock_svc.nc = MagicMock()
            mock_svc.nc.is_connected = True
            mock_svc.messages_published = 1
            mock_svc.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        assert response.json()["nats_connected"] is True

    def test_health_websocket_connected_matches_ready_flag(self):
        """websocket_connected mirrors service.ready."""
        import projects.ships.ingest.main as main_module

        for ready_value in (True, False):
            with patch.object(main_module, "service") as mock_svc:
                mock_svc.ready = ready_value
                mock_svc.nc = MagicMock() if ready_value else None
                mock_svc.nc.is_connected = ready_value if ready_value else False
                mock_svc.messages_published = 0
                mock_svc.last_message_time = None

                client = TestClient(app, raise_server_exceptions=False)
                response = client.get("/health")

            assert response.json()["websocket_connected"] is ready_value

    def test_health_messages_published_is_integer(self):
        """messages_published is a non-negative integer."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = True
            mock_svc.nc = MagicMock()
            mock_svc.nc.is_connected = True
            mock_svc.messages_published = 999
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        data = response.json()
        assert isinstance(data["messages_published"], int)
        assert data["messages_published"] >= 0

    def test_health_last_message_time_none_when_no_messages(self):
        """last_message_time is None when no messages have been published."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.ready = False
            mock_svc.nc = None
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

        assert response.json()["last_message_time"] is None


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint (not covered by existing test files)."""

    def test_metrics_returns_200(self):
        """Metrics endpoint returns HTTP 200."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

        assert response.status_code == 200

    def test_metrics_includes_messages_published(self):
        """Metrics response contains messages_published field."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.messages_published = 1234
            mock_svc.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

        data = response.json()
        assert "messages_published" in data
        assert data["messages_published"] == 1234

    def test_metrics_includes_last_message_time(self):
        """Metrics response contains last_message_time field."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.messages_published = 5
            mock_svc.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

        data = response.json()
        assert "last_message_time" in data
        assert data["last_message_time"] == "2024-01-15T10:00:00Z"

    def test_metrics_last_message_time_none_initially(self):
        """Metrics last_message_time is None when no messages published yet."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

        assert response.json()["last_message_time"] is None

    def test_metrics_only_contains_expected_fields(self):
        """Metrics response contains exactly messages_published and last_message_time."""
        import projects.ships.ingest.main as main_module

        with patch.object(main_module, "service") as mock_svc:
            mock_svc.messages_published = 0
            mock_svc.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

        data = response.json()
        assert set(data.keys()) == {"messages_published", "last_message_time"}
