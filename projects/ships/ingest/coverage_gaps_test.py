"""
Coverage gap tests for AIS ingest service.

Tests cover gaps not addressed by existing test files:
1. subscribe_to_aisstream() — bounding box JSON parse errors caught gracefully,
   and SSL context created with certifi CA bundle
2. connect_nats() — non-BadRequestError exceptions propagate (are not swallowed)
3. /metrics endpoint — counter increments reflected correctly after multiple
   publish_position() calls (end-to-end: real service instance + real endpoint)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.ingest.main import AISIngestService


# ---------------------------------------------------------------------------
# Helpers — minimal async context-manager WebSocket mock
# ---------------------------------------------------------------------------


class _EmptyWebSocket:
    """WebSocket context manager that immediately returns an empty message stream."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, _msg):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


# ---------------------------------------------------------------------------
# 1. subscribe_to_aisstream() — bounding box JSON errors
# ---------------------------------------------------------------------------


class TestSubscribeToAisstreamBoundingBox:
    """subscribe_to_aisstream handles invalid BOUNDING_BOX env variable gracefully."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_invalid_bounding_box_json_caught_gracefully(self, service):
        """json.loads(BOUNDING_BOX) failure is caught by generic except and does not propagate."""
        service.running = True

        async def fake_sleep(delay):
            service.running = False

        import projects.ships.ingest.main as main_module

        with (
            patch.object(main_module, "BOUNDING_BOX", "{{invalid json here}}"),
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_EmptyWebSocket(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            # Must not raise — the generic except block catches json.JSONDecodeError
            await service.subscribe_to_aisstream()

        # Loop exited cleanly (running set to False by fake_sleep)
        assert service.running is False

    @pytest.mark.asyncio
    async def test_ssl_context_uses_certifi_ca_bundle(self, service):
        """ssl.create_default_context is called with cafile=certifi.where()."""
        service.running = True

        async def fake_sleep(delay):
            service.running = False

        fake_ca_path = "/fake/path/cacert.pem"

        with (
            patch(
                "projects.ships.ingest.main.certifi.where",
                return_value=fake_ca_path,
            ),
            patch("projects.ships.ingest.main.ssl.create_default_context") as mock_ssl,
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_EmptyWebSocket(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        mock_ssl.assert_called_once_with(cafile=fake_ca_path)

    @pytest.mark.asyncio
    async def test_ready_reset_after_bounding_box_error(self, service):
        """After a bounding-box parse error the ready flag is reset to False."""
        service.running = True
        service.ready = True  # set before subscribe

        async def fake_sleep(delay):
            service.running = False

        import projects.ships.ingest.main as main_module

        with (
            patch.object(main_module, "BOUNDING_BOX", "not-json"),
            patch(
                "projects.ships.ingest.main.websockets.connect",
                return_value=_EmptyWebSocket(),
            ),
            patch("projects.ships.ingest.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await service.subscribe_to_aisstream()

        assert service.ready is False


# ---------------------------------------------------------------------------
# 2. connect_nats() — non-BadRequestError propagation
# ---------------------------------------------------------------------------


class TestConnectNatsNonBadRequestError:
    """connect_nats() propagates exceptions that are not BadRequestError."""

    @pytest.mark.asyncio
    async def test_generic_exception_from_add_stream_propagates(self):
        """A non-BadRequestError raised by add_stream is not caught."""
        import nats as nats_module

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = RuntimeError("NATS server unavailable")

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            with pytest.raises(RuntimeError, match="NATS server unavailable"):
                await service.connect_nats()

    @pytest.mark.asyncio
    async def test_connection_error_from_nats_connect_propagates(self):
        """nats.connect() failure propagates (not swallowed by connect_nats)."""
        import nats as nats_module

        service = AISIngestService()

        with patch.object(
            nats_module, "connect", AsyncMock(side_effect=OSError("refused"))
        ):
            with pytest.raises(OSError, match="refused"):
                await service.connect_nats()

    @pytest.mark.asyncio
    async def test_update_stream_called_with_same_config_on_already_in_use(self):
        """When 'already in use' is raised, update_stream receives a config with name='ais'."""
        import nats as nats_module
        import nats.js.errors

        class _AlreadyInUse(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUse()

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        # update_stream must be called with a config whose name is 'ais'
        mock_js.update_stream.assert_called_once()
        cfg = mock_js.update_stream.call_args[0][0]
        assert cfg.name == "ais"
        assert "ais.>" in cfg.subjects


# ---------------------------------------------------------------------------
# 3. /metrics endpoint — counter increments reflected correctly
# ---------------------------------------------------------------------------


class TestMetricsCounterIncrements:
    """/metrics endpoint reflects actual publish_position() call counts."""

    @pytest.mark.asyncio
    async def test_metrics_counter_increments_across_multiple_publishes(self):
        """After N publish_position() calls messages_published == N in /metrics."""
        from fastapi.testclient import TestClient

        import projects.ships.ingest.main as main_module

        service = AISIngestService()
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }

        # Simulate three sequential publishes
        await service.publish_position("123456789", data)
        await service.publish_position(
            "123456789", {**data, "timestamp": "2024-01-15T10:01:00Z"}
        )
        await service.publish_position(
            "123456789", {**data, "timestamp": "2024-01-15T10:02:00Z"}
        )

        assert service.messages_published == 3

        # Confirm the /metrics endpoint returns the current counter value
        with patch.object(main_module, "service", service):
            client = TestClient(main_module.app)
            response = client.get("/metrics")

        assert response.status_code == 200
        payload = response.json()
        assert payload["messages_published"] == 3
        assert payload["last_message_time"] == "2024-01-15T10:02:00Z"

    @pytest.mark.asyncio
    async def test_metrics_last_message_time_tracks_most_recent_publish(self):
        """last_message_time in /metrics is the timestamp of the most recent publish."""
        from fastapi.testclient import TestClient

        import projects.ships.ingest.main as main_module

        service = AISIngestService()
        service.js = AsyncMock()

        timestamps = [
            "2024-06-01T08:00:00Z",
            "2024-06-01T09:00:00Z",
            "2024-06-01T10:30:00Z",
        ]
        for ts in timestamps:
            await service.publish_position(
                "123",
                {"mmsi": "123", "lat": 48.5, "lon": -123.4, "timestamp": ts},
            )

        with patch.object(main_module, "service", service):
            client = TestClient(main_module.app)
            response = client.get("/metrics")

        payload = response.json()
        assert payload["last_message_time"] == timestamps[-1]

    @pytest.mark.asyncio
    async def test_metrics_zero_publishes_returns_zero_and_none(self):
        """Before any publish_position, /metrics returns messages_published=0 and last_message_time=None."""
        from fastapi.testclient import TestClient

        import projects.ships.ingest.main as main_module

        service = AISIngestService()  # fresh — no publishes

        with patch.object(main_module, "service", service):
            client = TestClient(main_module.app)
            response = client.get("/metrics")

        payload = response.json()
        assert payload["messages_published"] == 0
        assert payload["last_message_time"] is None
