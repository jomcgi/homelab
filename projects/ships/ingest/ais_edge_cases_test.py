"""
Additional edge-case tests for AIS ingest service.

Covers gaps not addressed in ais_ingest_test.py or ais_parsing_test.py:
- format_eta with falsy non-dict, non-None values (int 0, empty list, empty string)
- stop() with ws_task=None (no WebSocket task started)
- stop() with nc=None (NATS never connected)
- _process_position_report: only lat=None, only lon=None (one coord missing)
- _process_static_data: missing Dimension key, partial Dimension keys
- _process_static_data: missing Name key falls back to MetaData.ShipName
- process_message: generic exception handler path (non-JSON-decode error)
- stream config values in connect_nats (max_age, max_bytes, storage, discard)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.ships.ingest.main import (
    AISIngestService,
    format_eta,
)


class TestFormatEtaFalsyNonDictValues:
    """format_eta returns None for any falsy or non-dict input."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="integer_zero"),
            pytest.param([], id="empty_list"),
            pytest.param("", id="empty_string"),
            pytest.param(False, id="false"),
        ],
    )
    def test_falsy_non_dict_returns_none(self, value):
        assert format_eta(value) is None

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param([{"Month": 3}], id="list_of_dict"),
            pytest.param(42, id="non_zero_int"),
            pytest.param("March", id="non_empty_string"),
            pytest.param(3.14, id="float"),
        ],
    )
    def test_non_dict_truthy_returns_none(self, value):
        """Any truthy but non-dict value should return None."""
        assert format_eta(value) is None

    def test_format_eta_list_returns_none(self):
        """A list (even non-empty) is not a dict and must return None."""
        assert format_eta([{"Month": 6, "Day": 15}]) is None


class TestStopEdgeCases:
    """Tests for stop() when internal state is None."""

    @pytest.mark.asyncio
    async def test_stop_with_no_ws_task_does_not_raise(self):
        """stop() should not raise when ws_task is None."""
        service = AISIngestService()
        service.nc = AsyncMock()
        # ws_task is None (never started)
        assert service.ws_task is None

        await service.stop()  # Must not raise

        assert service.running is False
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_stop_with_no_nats_connection_does_not_raise(self):
        """stop() should not raise when nc is None (NATS never connected)."""
        service = AISIngestService()
        # nc is None, ws_task is None
        assert service.nc is None
        assert service.ws_task is None

        await service.stop()  # Must not raise

        assert service.running is False

    @pytest.mark.asyncio
    async def test_stop_resets_both_running_and_ready(self):
        """stop() sets both running and ready to False regardless of initial state."""
        service = AISIngestService()
        service.running = True
        service.ready = True
        service.nc = AsyncMock()

        await service.stop()

        assert service.running is False
        assert service.ready is False

    @pytest.mark.asyncio
    async def test_stop_cancels_running_ws_task(self):
        """stop() cancels and awaits the WebSocket task if it is running."""

        async def long_running():
            await asyncio.sleep(100)

        service = AISIngestService()
        service.running = True
        service.nc = AsyncMock()
        service.ws_task = asyncio.create_task(long_running())

        await service.stop()

        assert service.ws_task.cancelled()


class TestProcessPositionReportSingleMissingCoord:
    """_process_position_report skips messages where either coord is None."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_only_latitude_none_skips_publish(self, service):
        """lat=None with valid lon → no publish."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": None,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                    }
                },
            }
        )

        await service.process_message(message)
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_longitude_none_skips_publish(self, service):
        """lat valid with lon=None → no publish."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": None,
                        "Sog": 5.0,
                        "Cog": 90.0,
                    }
                },
            }
        )

        await service.process_message(message)
        service.js.publish.assert_not_called()


class TestStaticDataDimensionExtraction:
    """Tests for dimension field extraction in _process_static_data."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    def _make_static_msg(self, dimension):
        return json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "555555555",
                    "time_utc": "2024-06-01T12:00:00Z",
                    "ShipName": "DIM TEST",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 9999999,
                        "CallSign": "DTEST",
                        "Name": "DIM TEST",
                        "Type": 70,
                        "Dimension": dimension,
                        "Destination": "PORT",
                        "Eta": None,
                        "MaximumStaticDraught": 6.0,
                    }
                },
            }
        )

    @pytest.mark.asyncio
    async def test_full_dimension_all_keys_extracted(self, service):
        """All four dimension keys (A/B/C/D) are present and extracted."""
        msg = self._make_static_msg({"A": 100, "B": 50, "C": 15, "D": 12})
        await service.process_message(msg)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] == 100
        assert payload["dimension_b"] == 50
        assert payload["dimension_c"] == 15
        assert payload["dimension_d"] == 12

    @pytest.mark.asyncio
    async def test_empty_dimension_dict_yields_none_values(self, service):
        """When Dimension is {}, all dimension fields are None."""
        msg = self._make_static_msg({})
        await service.process_message(msg)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] is None
        assert payload["dimension_b"] is None
        assert payload["dimension_c"] is None
        assert payload["dimension_d"] is None

    @pytest.mark.asyncio
    async def test_partial_dimension_keys_present(self, service):
        """When only some dimension keys are present, missing ones are None."""
        msg = self._make_static_msg({"A": 80, "C": 12})
        await service.process_message(msg)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] == 80
        assert payload["dimension_b"] is None
        assert payload["dimension_c"] == 12
        assert payload["dimension_d"] is None

    @pytest.mark.asyncio
    async def test_missing_dimension_key_in_static_data(self, service):
        """If ShipStaticData has no Dimension key at all, all dimension fields are None."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "444444444",
                    "time_utc": "2024-06-01T12:00:00Z",
                    "ShipName": "NO DIM",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1111111,
                        "CallSign": "NODIM",
                        "Name": "NO DIM",
                        "Type": 70,
                        # No "Dimension" key
                        "Destination": "PORT",
                        "Eta": None,
                        "MaximumStaticDraught": 4.0,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] is None
        assert payload["dimension_b"] is None
        assert payload["dimension_c"] is None
        assert payload["dimension_d"] is None


class TestStaticDataNameFallback:
    """Tests for name resolution priority in _process_static_data."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_missing_name_key_falls_back_to_metadata_ship_name(self, service):
        """When Name key is absent from ShipStaticData, MetaData.ShipName is used."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "111111111",
                    "time_utc": "2024-06-01T12:00:00Z",
                    "ShipName": "META NAME",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 2222222,
                        "CallSign": "CALL",
                        # No "Name" key at all
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "DEST",
                        "Eta": None,
                        "MaximumStaticDraught": 3.0,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == "META NAME"

    @pytest.mark.asyncio
    async def test_non_empty_name_takes_priority_over_metadata(self, service):
        """A non-empty Name in ShipStaticData takes priority over MetaData.ShipName."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "222222222",
                    "time_utc": "2024-06-01T12:00:00Z",
                    "ShipName": "META NAME",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 3333333,
                        "CallSign": "CALL",
                        "Name": "STATIC NAME",
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "DEST",
                        "Eta": None,
                        "MaximumStaticDraught": 3.0,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == "STATIC NAME"

    @pytest.mark.asyncio
    async def test_both_name_and_metadata_empty_yields_empty_string(self, service):
        """When both Name and MetaData.ShipName are empty, result is empty string."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "333333333",
                    "time_utc": "2024-06-01T12:00:00Z",
                    # No ShipName
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 4444444,
                        "CallSign": "CALL",
                        "Name": "",
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "DEST",
                        "Eta": None,
                        "MaximumStaticDraught": 3.0,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == ""


class TestProcessMessageExceptionHandling:
    """Tests for exception handling paths in process_message."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_generic_exception_in_process_position_does_not_propagate(
        self, service
    ):
        """Exceptions from _process_position_report are caught and logged."""
        service.js.publish.side_effect = RuntimeError("NATS publish failed")

        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                    }
                },
            }
        )

        # Must not raise — the generic except Exception catches it
        await service.process_message(message)

    @pytest.mark.asyncio
    async def test_generic_exception_in_process_static_does_not_propagate(
        self, service
    ):
        """Exceptions from _process_static_data are caught and logged."""
        service.js.publish.side_effect = OSError("network error")

        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "987654321",
                    "time_utc": "2024-06-01T12:00:00Z",
                    "ShipName": "VESSEL",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1234567,
                        "CallSign": "CALL",
                        "Name": "VESSEL",
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "PORT",
                        "Eta": None,
                        "MaximumStaticDraught": 5.0,
                    }
                },
            }
        )

        # Must not raise
        await service.process_message(message)


class TestConnectNatsStreamConfig:
    """Tests for stream configuration values in connect_nats."""

    @pytest.mark.asyncio
    async def test_stream_max_age_is_24h(self):
        """Stream max_age is set to 86400 seconds (24 hours)."""
        import nats as nats_module

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        cfg = mock_js.add_stream.call_args[0][0]
        assert cfg.max_age == 86400

    @pytest.mark.asyncio
    async def test_stream_max_bytes_is_10gb(self):
        """Stream max_bytes is set to 10 * 1024 * 1024 * 1024."""
        import nats as nats_module

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        cfg = mock_js.add_stream.call_args[0][0]
        assert cfg.max_bytes == 10 * 1024 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_stream_discard_policy_is_old(self):
        """Stream discard policy is DiscardPolicy.OLD."""
        import nats as nats_module
        from nats.js.api import DiscardPolicy

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        cfg = mock_js.add_stream.call_args[0][0]
        assert cfg.discard == DiscardPolicy.OLD

    @pytest.mark.asyncio
    async def test_stream_storage_type_is_file(self):
        """Stream storage type is StorageType.FILE."""
        import nats as nats_module
        from nats.js.api import StorageType

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()

        cfg = mock_js.add_stream.call_args[0][0]
        assert cfg.storage == StorageType.FILE
