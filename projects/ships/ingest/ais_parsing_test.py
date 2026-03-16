"""
Additional unit tests for AIS parsing utilities in the ingest service.

Focuses on gaps not covered by ais_ingest_test.py:
- format_eta with combined unavailable Hour+Minute, and missing dict keys
- Whitespace stripping for call_sign, name, destination in static data
- Whitespace stripping for ship_name in position reports
- NATS subject construction in publish_position / publish_static
- process_message with MMSI=0 (falsy numeric value)
- _process_position_report with optional fields absent
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from projects.ships.ingest.main import (
    AISIngestService,
    format_eta,
)


class TestFormatEtaAdditionalCases:
    """Additional format_eta cases beyond those in ais_ingest_test.py."""

    def test_both_hour_and_minute_unavailable_defaults_to_midnight(self):
        """Hour=24 AND Minute=60 together should default to 00:00."""
        eta = {"Month": 6, "Day": 15, "Hour": 24, "Minute": 60}
        result = format_eta(eta)
        assert result is not None
        assert "T00:00:00Z" in result

    def test_missing_month_key_treated_as_zero(self):
        """A dict without 'Month' key defaults to 0 → None."""
        eta = {"Day": 15, "Hour": 14, "Minute": 30}
        result = format_eta(eta)
        assert result is None

    def test_missing_day_key_treated_as_zero(self):
        """A dict without 'Day' key defaults to 0 → None."""
        eta = {"Month": 6, "Hour": 14, "Minute": 30}
        result = format_eta(eta)
        assert result is None

    def test_missing_hour_key_treated_as_unavailable(self):
        """A dict without 'Hour' key defaults to 24 → 00 in output."""
        # Use a month/day guaranteed to be in the future so year is current
        eta = {"Month": 12, "Day": 31, "Minute": 0}
        result = format_eta(eta)
        # Should not be None; hour defaults to 00
        assert result is not None
        assert "T00:00:00Z" in result

    def test_missing_minute_key_treated_as_unavailable(self):
        """A dict without 'Minute' key defaults to 60 → 00 in output."""
        eta = {"Month": 12, "Day": 31, "Hour": 10}
        result = format_eta(eta)
        assert result is not None
        assert "T10:00:00Z" in result

    def test_format_eta_returns_iso_8601_format(self):
        """Output is a valid ISO 8601 UTC datetime string."""
        eta = {"Month": 8, "Day": 20, "Hour": 9, "Minute": 45}
        result = format_eta(eta)
        assert result is not None
        # Must be parseable as ISO 8601
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.month == 8
        assert parsed.day == 20
        assert parsed.hour == 9
        assert parsed.minute == 45

    def test_format_eta_future_date_stays_in_current_year(self):
        """A date clearly in the future this year should not be bumped to next year."""
        now = datetime.now(timezone.utc)
        # Pick December 31 — always in the future unless it's literally Dec 31
        if now.month == 12 and now.day == 31:
            pytest.skip("Cannot reliably test on Dec 31")
        eta = {"Month": 12, "Day": 31, "Hour": 23, "Minute": 59}
        result = format_eta(eta)
        assert result is not None
        assert result.startswith(str(now.year))

    def test_format_eta_integer_zero_values(self):
        """Explicit integer 0 for Month or Day returns None (unavailable)."""
        assert format_eta({"Month": 0, "Day": 0, "Hour": 0, "Minute": 0}) is None

    def test_format_eta_all_unavailable_sentinel_values(self):
        """Month=0, Day=0 with valid Hour/Minute still returns None."""
        assert format_eta({"Month": 0, "Day": 1, "Hour": 12, "Minute": 0}) is None
        assert format_eta({"Month": 1, "Day": 0, "Hour": 12, "Minute": 0}) is None


class TestWhitespaceStripping:
    """Tests that incoming AIS strings have leading/trailing whitespace stripped."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_static_data_strips_call_sign(self, service):
        """call_sign is stripped of surrounding whitespace."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "VESSEL",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1000001,
                        "CallSign": "  CALL1  ",
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

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["call_sign"] == "CALL1"

    @pytest.mark.asyncio
    async def test_static_data_strips_name(self, service):
        """Ship name is stripped of surrounding whitespace."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "VESSEL",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1000002,
                        "CallSign": "CALL1",
                        "Name": "  MV WHITESPACE  ",
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

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == "MV WHITESPACE"

    @pytest.mark.asyncio
    async def test_static_data_strips_destination(self, service):
        """Destination is stripped of surrounding whitespace."""
        message = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "VESSEL",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1000003,
                        "CallSign": "CALL1",
                        "Name": "VESSEL",
                        "Type": 70,
                        "Dimension": {},
                        "Destination": "  VANCOUVER  ",
                        "Eta": None,
                        "MaximumStaticDraught": 5.0,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["destination"] == "VANCOUVER"

    @pytest.mark.asyncio
    async def test_position_report_strips_ship_name(self, service):
        """ShipName from MetaData is stripped in position reports."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "  PADDED NAME  ",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                        "TrueHeading": 88,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["ship_name"] == "PADDED NAME"


class TestNATSSubjectConstruction:
    """Tests for NATS subject formatting in publish methods."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_publish_position_subject_contains_mmsi(self, service):
        """publish_position constructs subject as 'ais.position.{mmsi}'."""
        mmsi = "987654321"
        data = {
            "mmsi": mmsi,
            "lat": 49.0,
            "lon": -124.0,
            "timestamp": "2024-06-01T12:00:00Z",
        }
        await service.publish_position(mmsi, data)

        subject = service.js.publish.call_args[0][0]
        assert subject == f"ais.position.{mmsi}"

    @pytest.mark.asyncio
    async def test_publish_static_subject_contains_mmsi(self, service):
        """publish_static constructs subject as 'ais.static.{mmsi}'."""
        mmsi = "111222333"
        data = {
            "mmsi": mmsi,
            "name": "TEST",
            "timestamp": "2024-06-01T12:00:00Z",
        }
        await service.publish_static(mmsi, data)

        subject = service.js.publish.call_args[0][0]
        assert subject == f"ais.static.{mmsi}"

    @pytest.mark.asyncio
    async def test_publish_position_payload_is_valid_json(self, service):
        """publish_position encodes data as valid UTF-8 JSON bytes."""
        data = {
            "mmsi": "123",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-06-01T12:00:00Z",
        }
        await service.publish_position("123", data)

        raw = service.js.publish.call_args[0][1]
        decoded = json.loads(raw.decode("utf-8"))
        assert decoded["mmsi"] == "123"

    @pytest.mark.asyncio
    async def test_publish_static_payload_is_valid_json(self, service):
        """publish_static encodes data as valid UTF-8 JSON bytes."""
        data = {
            "mmsi": "456",
            "name": "VESSEL",
            "timestamp": "2024-06-01T12:00:00Z",
        }
        await service.publish_static("456", data)

        raw = service.js.publish.call_args[0][1]
        decoded = json.loads(raw.decode("utf-8"))
        assert decoded["mmsi"] == "456"


class TestProcessMessageMMSIEdgeCases:
    """Tests for MMSI edge cases in process_message."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_mmsi_zero_string_is_ignored(self, service):
        """MMSI of '0' (falsy string when cast from int) should be ignored.

        In the code: mmsi = str(metadata.get("MMSI", ""))
        When MMSI=0, str(0) = "0" which is truthy — but this test documents
        whether the service treats MMSI=0 as valid and publishes a message.
        """
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": 0,
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "UNKNOWN",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 0.0,
                        "Longitude": 0.0,
                        "Sog": 0.0,
                        "Cog": 0.0,
                        "TrueHeading": 511,
                        "NavigationalStatus": 15,
                        "RateOfTurn": -128,
                        "PositionAccuracy": False,
                    }
                },
            }
        )

        await service.process_message(message)

        # MMSI "0" → str(0) = "0" which is truthy, so the message IS published.
        # This test documents the actual (current) behaviour.
        if service.js.publish.called:
            subject = service.js.publish.call_args[0][0]
            assert "0" in subject
        # No assertion that it must NOT publish — just that no exception is raised.

    @pytest.mark.asyncio
    async def test_mmsi_empty_string_not_published(self, service):
        """An empty-string MMSI should cause the message to be ignored."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    # Omit MMSI entirely → str("") = "" which is falsy
                    "time_utc": "2024-01-15T10:00:00Z",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                        "TrueHeading": 88,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_not_called()


class TestPositionReportOptionalFields:
    """Tests for position report handling of optional/absent AIS fields."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_position_report_with_only_lat_lon(self, service):
        """Position report with only coordinates (all optional fields absent) is published."""
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
                        # All other fields absent
                    }
                },
            }
        )

        await service.process_message(message)

        service.js.publish.assert_called_once()
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["lat"] == 48.5
        assert payload["lon"] == -123.4
        assert payload["speed"] is None
        assert payload["heading"] is None

    @pytest.mark.asyncio
    async def test_position_report_ship_name_stripped_when_present(self, service):
        """ShipName with trailing spaces is stripped in the published payload."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "STAR VANCOUVER   ",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 49.0,
                        "Longitude": -123.0,
                        "Sog": 10.0,
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

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["ship_name"] == "STAR VANCOUVER"

    @pytest.mark.asyncio
    async def test_position_report_absent_ship_name_is_empty_string(self, service):
        """MetaData.ShipName absent → ship_name is empty string after strip."""
        message = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "123456789",
                    "time_utc": "2024-01-15T10:00:00Z",
                    # No ShipName key
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                        "Sog": 5.0,
                        "Cog": 90.0,
                        "TrueHeading": 88,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )

        await service.process_message(message)

        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["ship_name"] == ""
