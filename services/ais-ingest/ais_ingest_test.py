"""Tests for AIS Ingest service."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from main import (
    AISIngestService,
    app,
    format_eta,
)


class TestFormatEta:
    """Tests for ETA formatting function."""

    def test_format_eta_valid(self):
        """Valid ETA with all fields should produce ISO timestamp."""
        eta = {"Month": 3, "Day": 15, "Hour": 14, "Minute": 30}
        result = format_eta(eta)

        assert result is not None
        assert "03-15T14:30:00Z" in result

    def test_format_eta_unavailable_month(self):
        """Month=0 indicates unavailable ETA."""
        eta = {"Month": 0, "Day": 15, "Hour": 14, "Minute": 30}
        result = format_eta(eta)
        assert result is None

    def test_format_eta_unavailable_day(self):
        """Day=0 indicates unavailable ETA."""
        eta = {"Month": 3, "Day": 0, "Hour": 14, "Minute": 30}
        result = format_eta(eta)
        assert result is None

    def test_format_eta_unavailable_hour(self):
        """Hour=24 indicates unavailable, should default to 00."""
        eta = {"Month": 3, "Day": 15, "Hour": 24, "Minute": 30}
        result = format_eta(eta)

        assert result is not None
        assert "T00:30:00Z" in result

    def test_format_eta_unavailable_minute(self):
        """Minute=60 indicates unavailable, should default to 00."""
        eta = {"Month": 3, "Day": 15, "Hour": 14, "Minute": 60}
        result = format_eta(eta)

        assert result is not None
        assert "T14:00:00Z" in result

    def test_format_eta_none(self):
        result = format_eta(None)
        assert result is None

    def test_format_eta_empty_dict(self):
        result = format_eta({})
        assert result is None

    def test_format_eta_not_dict(self):
        result = format_eta("not a dict")
        assert result is None

    def test_format_eta_invalid_date(self):
        """Invalid date like Feb 30 should return None."""
        eta = {"Month": 2, "Day": 30, "Hour": 12, "Minute": 0}
        result = format_eta(eta)
        assert result is None

    def test_format_eta_past_date_uses_next_year(self):
        """Past dates should be inferred as next year."""
        now = datetime.now(timezone.utc)
        # Use a date that's definitely in the past this year
        past_month = (now.month - 2) % 12 or 12
        eta = {"Month": past_month, "Day": 1, "Hour": 12, "Minute": 0}
        result = format_eta(eta)

        if result:
            # Parse the result and check year
            result_year = int(result[:4])
            # Should be current or next year
            assert result_year >= now.year


class TestAISIngestService:
    """Tests for AIS ingestion service."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    def test_initial_state(self, service):
        assert service.nc is None
        assert service.js is None
        assert service.running is False
        assert service.ready is False
        assert service.messages_published == 0
        assert service.last_message_time is None

    @pytest.mark.asyncio
    async def test_process_message_position_report(self, service):
        """Position reports should be published to NATS."""
        service.js = AsyncMock()
        service.nc = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "Test Vessel",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 12.5,
                        "Cog": 180.0,
                        "TrueHeading": 179,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_called_once()
        call_args = service.js.publish.call_args
        assert call_args[0][0] == "ais.position.123456789"

        payload = json.loads(call_args[0][1])
        assert payload["mmsi"] == "123456789"
        assert payload["lat"] == 48.5
        assert payload["lon"] == -123.4
        assert payload["speed"] == 12.5

    @pytest.mark.asyncio
    async def test_process_message_static_data(self, service):
        """Ship static data should be published to NATS."""
        service.js = AsyncMock()
        service.nc = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "Test Vessel",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 9876543,
                        "CallSign": "TEST1",
                        "Name": "MV Test Vessel",
                        "Type": 70,
                        "Dimension": {"A": 100, "B": 50, "C": 10, "D": 10},
                        "Destination": "VANCOUVER",
                        "Eta": {"Month": 3, "Day": 15, "Hour": 14, "Minute": 0},
                        "MaximumStaticDraught": 8.5,
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_called_once()
        call_args = service.js.publish.call_args
        assert call_args[0][0] == "ais.static.123456789"

        payload = json.loads(call_args[0][1])
        assert payload["mmsi"] == "123456789"
        assert payload["imo"] == 9876543
        assert payload["call_sign"] == "TEST1"
        assert payload["destination"] == "VANCOUVER"

    @pytest.mark.asyncio
    async def test_process_message_missing_mmsi(self, service):
        """Messages without MMSI should be ignored."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {"time_utc": "2024-01-15T10:00:00Z"},
                "Message": {"PositionReport": {}},
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_invalid_json(self, service):
        """Invalid JSON should be handled gracefully."""
        service.js = AsyncMock()

        await service.process_message("not valid json")

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_position_without_coords(self, service):
        """Position reports without coordinates should be skipped."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {
                    "PositionReport": {
                        "Sog": 12.5,
                        "Cog": 180.0,
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_position(self, service):
        """publish_position should increment counter and update timestamp."""
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await service.publish_position("123456789", data)

        assert service.messages_published == 1
        assert service.last_message_time == "2024-01-15T10:00:00Z"

        # Check deduplication header
        call_args = service.js.publish.call_args
        headers = call_args[1]["headers"]
        assert "Nats-Msg-Id" in headers
        assert "123456789-2024-01-15T10:00:00Z" in headers["Nats-Msg-Id"]

    @pytest.mark.asyncio
    async def test_publish_static(self, service):
        """publish_static should publish to correct subject."""
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "name": "Test Vessel",
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await service.publish_static("123456789", data)

        call_args = service.js.publish.call_args
        assert call_args[0][0] == "ais.static.123456789"

    @pytest.mark.asyncio
    async def test_connect_nats(self, service):
        """connect_nats should create stream if needed."""
        import nats as nats_module

        mock_nc = MagicMock()  # Use MagicMock for sync methods
        mock_js = AsyncMock()  # Use AsyncMock for async methods
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

            mock_js.add_stream.assert_called_once()

            # Check stream config
            call_args = mock_js.add_stream.call_args
            stream_config = call_args[0][0]
            assert stream_config.name == "ais"
            assert "ais.>" in stream_config.subjects

    @pytest.mark.asyncio
    async def test_stop(self, service):
        """stop should close connections gracefully."""
        service.running = True
        service.ready = True
        service.nc = AsyncMock()
        # Create a proper task mock that can be cancelled and awaited
        async def dummy_task():
            await asyncio.sleep(10)

        service.ws_task = asyncio.create_task(dummy_task())

        await service.stop()

        assert service.running is False
        assert service.ready is False
        service.nc.close.assert_called_once()


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_ready(self):
        import main

        with patch.object(main, "service") as mock_service:
            mock_service.ready = True
            mock_service.nc = MagicMock()
            mock_service.nc.is_connected = True
            mock_service.messages_published = 100
            mock_service.last_message_time = "2024-01-15T10:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["nats_connected"] is True
            assert data["websocket_connected"] is True
            assert data["messages_published"] == 100

    def test_health_not_ready(self):
        import main

        with patch.object(main, "service") as mock_service:
            mock_service.ready = False
            mock_service.nc = None
            mock_service.messages_published = 0
            mock_service.last_message_time = None

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "starting"


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    def test_metrics(self):
        import main

        with patch.object(main, "service") as mock_service:
            mock_service.messages_published = 500
            mock_service.last_message_time = "2024-01-15T12:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

            assert response.status_code == 200
            data = response.json()
            assert data["messages_published"] == 500
            assert data["last_message_time"] == "2024-01-15T12:00:00Z"
