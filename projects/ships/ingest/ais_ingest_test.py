"""Tests for AIS Ingest service."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from projects.ships.ingest.main import (
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
        import projects.ships.ingest.main as main

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
        import projects.ships.ingest.main as main

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


class TestWebSocketReconnection:
    """Tests for WebSocket reconnection backoff logic."""

    def test_initial_delay_is_constant(self):
        from projects.ships.ingest.main import INITIAL_RECONNECT_DELAY

        assert INITIAL_RECONNECT_DELAY == 1.0

    def test_max_delay_is_constant(self):
        from projects.ships.ingest.main import MAX_RECONNECT_DELAY

        assert MAX_RECONNECT_DELAY == 60.0

    def test_backoff_factor_is_constant(self):
        from projects.ships.ingest.main import RECONNECT_BACKOFF_FACTOR

        assert RECONNECT_BACKOFF_FACTOR == 2.0

    def test_backoff_doubles_each_attempt(self):
        from projects.ships.ingest.main import (
            INITIAL_RECONNECT_DELAY,
            MAX_RECONNECT_DELAY,
            RECONNECT_BACKOFF_FACTOR,
        )

        delay = INITIAL_RECONNECT_DELAY
        expected_sequence = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]

        for expected in expected_sequence:
            assert delay == expected
            delay = min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY)

    def test_backoff_never_exceeds_max(self):
        from projects.ships.ingest.main import (
            INITIAL_RECONNECT_DELAY,
            MAX_RECONNECT_DELAY,
            RECONNECT_BACKOFF_FACTOR,
        )

        delay = INITIAL_RECONNECT_DELAY
        for _ in range(20):
            delay = min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY)
            assert delay <= MAX_RECONNECT_DELAY

    def test_backoff_caps_at_max(self):
        from projects.ships.ingest.main import (
            MAX_RECONNECT_DELAY,
            RECONNECT_BACKOFF_FACTOR,
        )

        # Start from just below max and verify it caps
        delay = MAX_RECONNECT_DELAY / RECONNECT_BACKOFF_FACTOR + 1
        next_delay = min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY)
        assert next_delay == MAX_RECONNECT_DELAY

    def test_first_attempt_uses_initial_delay(self):
        from projects.ships.ingest.main import INITIAL_RECONNECT_DELAY

        # The reconnect loop starts with INITIAL_RECONNECT_DELAY before the first
        # retry, so the initial value must equal the constant.
        delay = INITIAL_RECONNECT_DELAY
        assert delay == 1.0


class TestAISIngestServiceState:
    """Tests for AISIngestService initial state and NATS tracking."""

    @pytest.fixture
    def service(self):
        from projects.ships.ingest.main import AISIngestService

        return AISIngestService()

    def test_initial_running_false(self, service):
        assert service.running is False

    def test_initial_ready_false(self, service):
        assert service.ready is False

    def test_initial_nats_connection_none(self, service):
        assert service.nc is None

    def test_initial_jetstream_none(self, service):
        assert service.js is None

    def test_initial_ws_task_none(self, service):
        assert service.ws_task is None

    def test_initial_messages_published_zero(self, service):
        assert service.messages_published == 0

    def test_initial_last_message_time_none(self, service):
        assert service.last_message_time is None

    @pytest.mark.asyncio
    async def test_nats_connection_tracked_after_connect(self, service):
        """After connect_nats, nc and js should be set."""
        import nats as nats_module

        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        assert service.nc is mock_nc
        assert service.js is mock_js

    @pytest.mark.asyncio
    async def test_publish_increments_counter(self, service):
        service.js = AsyncMock()
        data = {
            "mmsi": "123",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await service.publish_position("123", data)
        assert service.messages_published == 1

        await service.publish_position("123", data)
        assert service.messages_published == 2

    @pytest.mark.asyncio
    async def test_publish_updates_last_message_time(self, service):
        service.js = AsyncMock()
        data = {
            "mmsi": "123",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await service.publish_position("123", data)
        assert service.last_message_time == "2024-01-15T10:00:00Z"


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""

    def test_metrics(self):
        import projects.ships.ingest.main as main

        with patch.object(main, "service") as mock_service:
            mock_service.messages_published = 500
            mock_service.last_message_time = "2024-01-15T12:00:00Z"

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/metrics")

            assert response.status_code == 200
            data = response.json()
            assert data["messages_published"] == 500
            assert data["last_message_time"] == "2024-01-15T12:00:00Z"


class TestConnectNatsEdgeCases:
    """Tests for connect_nats stream creation edge cases."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_connect_nats_stream_already_in_use_calls_update_stream(
        self, service
    ):
        """When the stream already exists with different config, update_stream is called."""
        import nats as nats_module
        import nats.js.errors

        class _AlreadyInUseError(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUseError()

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        mock_js.update_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_nats_update_stream_uses_same_config(self, service):
        """update_stream receives a StreamConfig with name='ais'."""
        import nats as nats_module
        import nats.js.errors

        class _AlreadyInUseError(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUseError()

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        stream_config = mock_js.update_stream.call_args[0][0]
        assert stream_config.name == "ais"
        assert "ais.>" in stream_config.subjects

    @pytest.mark.asyncio
    async def test_connect_nats_other_bad_request_error_reraises(self, service):
        """BadRequestError not containing 'already in use' should propagate."""
        import nats as nats_module
        import nats.js.errors

        class _OtherBadRequest(nats.js.errors.BadRequestError):
            def __str__(self):
                return "nats: bad request: some other error"

        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _OtherBadRequest()

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            with pytest.raises(nats.js.errors.BadRequestError):
                await service.connect_nats()


class TestProcessMessageEdgeCases:
    """Tests for process_message handling of unusual inputs."""

    @pytest.fixture
    def service(self):
        return AISIngestService()

    @pytest.mark.asyncio
    async def test_process_message_unknown_type_no_publish(self, service):
        """Unknown MessageType should be silently ignored without publishing."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "UnknownType",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {},
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_empty_position_report_skipped(self, service):
        """PositionReport with no PositionReport key in Message is skipped."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {},  # No PositionReport key
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_empty_static_data_skipped(self, service):
        """ShipStaticData with no ShipStaticData key in Message is skipped."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {},  # No ShipStaticData key
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_static_data_uses_metadata_ship_name_fallback(
        self, service
    ):
        """When static Name is empty, ShipName from MetaData is used as fallback."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "FALLBACK NAME",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1234567,
                        "CallSign": "CALL1",
                        "Name": "",  # Empty — should fall back to MetaData.ShipName
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "PORT",
                        "Eta": None,
                        "MaximumStaticDraught": 5.0,
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_called_once()
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == "FALLBACK NAME"

    @pytest.mark.asyncio
    async def test_publish_static_dedup_header_format(self, service):
        """publish_static uses 'static-{mmsi}-{timestamp}' as Nats-Msg-Id."""
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "name": "Test Vessel",
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await service.publish_static("123456789", data)

        headers = service.js.publish.call_args[1]["headers"]
        assert headers["Nats-Msg-Id"] == "static-123456789-2024-01-15T10:00:00Z"

    @pytest.mark.asyncio
    async def test_process_position_includes_all_ais_fields(self, service):
        """Position report payload includes heading, nav_status, rate_of_turn, accuracy."""
        service.js = AsyncMock()

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "987654321",
                    "time_utc": "2024-03-01T12:00:00Z",
                    "ShipName": "FULL VESSEL",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 49.0,
                        "Longitude": -124.0,
                        "Sog": 8.0,
                        "Cog": 90.0,
                        "TrueHeading": 88,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 5,
                        "PositionAccuracy": True,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["heading"] == 88
        assert payload["nav_status"] == 0
        assert payload["rate_of_turn"] == 5
        assert payload["position_accuracy"] is True
        assert payload["ship_name"] == "FULL VESSEL"
        assert payload["course"] == 90.0

    @pytest.mark.asyncio
    async def test_publish_position_without_timestamp_has_empty_msg_id(self, service):
        """publish_position with no timestamp uses empty string in Nats-Msg-Id."""
        service.js = AsyncMock()

        data = {"mmsi": "123456789", "lat": 48.5, "lon": -123.4}

        await service.publish_position("123456789", data)

        headers = service.js.publish.call_args[1]["headers"]
        assert headers["Nats-Msg-Id"] == "123456789-"
