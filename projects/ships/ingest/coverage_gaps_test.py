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

from projects.ships.ingest.main import AISIngestService, format_eta


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

        # Confirm the /metrics endpoint returns the current counter value by
        # calling the endpoint function directly — avoids a TestClient/httpx dep
        with patch.object(main_module, "service", service):
            payload = await main_module.metrics()

        assert payload["messages_published"] == 3
        assert payload["last_message_time"] == "2024-01-15T10:02:00Z"

    @pytest.mark.asyncio
    async def test_metrics_last_message_time_tracks_most_recent_publish(self):
        """last_message_time in /metrics is the timestamp of the most recent publish."""
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
            payload = await main_module.metrics()

        assert payload["last_message_time"] == timestamps[-1]

    @pytest.mark.asyncio
    async def test_metrics_zero_publishes_returns_zero_and_none(self):
        """Before any publish_position, /metrics returns messages_published=0 and last_message_time=None."""
        import projects.ships.ingest.main as main_module

        service = AISIngestService()  # fresh — no publishes

        with patch.object(main_module, "service", service):
            payload = await main_module.metrics()

        assert payload["messages_published"] == 0
        assert payload["last_message_time"] is None


# ---------------------------------------------------------------------------
# 4. _process_static_data() — dimension edge cases
# ---------------------------------------------------------------------------


class TestProcessStaticDataDimensionEdgeCases:
    """Test _process_static_data() dimension handling."""

    @pytest.mark.asyncio
    async def test_missing_dimension_key_all_none(self):
        """When Dimension key is absent, dimension_a/b/c/d are all None."""
        service = AISIngestService()
        mock_js = AsyncMock()
        service.js = mock_js

        message = {
            "Message": {
                "ShipStaticData": {
                    "ImoNumber": 1234567,
                    "CallSign": "ABCD1",
                    "Name": "TEST VESSEL",
                    "Type": 70,
                    # Dimension key is absent
                    "Destination": "PORT",
                    "MaximumStaticDraught": 5.5,
                }
            }
        }
        metadata = {"time_utc": "2024-06-01T10:00:00Z"}

        await service._process_static_data(message, "123456789", metadata)

        mock_js.publish.assert_called_once()
        published_payload = json.loads(mock_js.publish.call_args[0][1])
        assert published_payload["dimension_a"] is None
        assert published_payload["dimension_b"] is None
        assert published_payload["dimension_c"] is None
        assert published_payload["dimension_d"] is None

    @pytest.mark.asyncio
    async def test_empty_ship_static_data_returns_none(self):
        """When ShipStaticData is empty, function returns without publishing."""
        service = AISIngestService()
        mock_js = AsyncMock()
        service.js = mock_js

        # ShipStaticData is an empty dict — falsy → early return
        message = {"Message": {"ShipStaticData": {}}}
        metadata = {"time_utc": "2024-06-01T10:00:00Z"}

        await service._process_static_data(message, "123456789", metadata)

        # publish must NOT have been called
        mock_js.publish.assert_not_called()


# ---------------------------------------------------------------------------
# 4. format_eta() — year rollover inference
# ---------------------------------------------------------------------------


class TestFormatEtaYearRolloverInference:
    """Tests for format_eta year inference: past dates become next year.

    The existing ais_ingest_test.py test_format_eta_past_date_uses_next_year
    is date-sensitive and asserts `result_year >= now.year` (weak check).
    These tests are more explicit.
    """

    def test_january_1_always_results_in_future_or_current_year(self):
        """ETA of January 1 is always treated as future: if Jan 1 already passed
        this year, it should return next year."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        result = format_eta({"Month": 1, "Day": 1, "Hour": 0, "Minute": 0})
        assert result is not None
        result_year = int(result[:4])
        # Result must be current or next year (never in the past)
        assert result_year >= now.year

    def test_past_date_gets_bumped_to_next_year(self):
        """A date that was clearly in the past this year returns next year."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        # Pick a month guaranteed to be in the past (at least 2 months ago)
        # Skip if we're in Jan or Feb (can't guarantee a past month)
        if now.month <= 2:
            # Use January with day 1 — guaranteed to be in the past if we're in Feb+
            if now.month == 1 and now.day == 1:
                return  # Edge case: literally Jan 1 right now
            past_month = 1
        else:
            past_month = now.month - 2

        result = format_eta({"Month": past_month, "Day": 1, "Hour": 0, "Minute": 0})
        assert result is not None
        result_year = int(result[:4])
        assert result_year == now.year + 1

    def test_future_date_stays_in_current_year(self):
        """A date clearly in the future stays in the current year."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        # Pick Dec 31 unless it's actually Dec 31 right now
        if now.month == 12 and now.day >= 30:
            return  # Skip — can't guarantee Dec 31 is in future

        result = format_eta({"Month": 12, "Day": 31, "Hour": 23, "Minute": 59})
        assert result is not None
        assert result.startswith(str(now.year))

    def test_invalid_date_feb_30_returns_none(self):
        """Dates that don't exist (e.g. Feb 30) return None gracefully."""
        assert format_eta({"Month": 2, "Day": 30, "Hour": 12, "Minute": 0}) is None

    def test_none_input_returns_none(self):
        """None input returns None (not an exception)."""
        assert format_eta(None) is None

    def test_empty_dict_input_returns_none(self):
        """Empty dict — all keys absent (Month=0, Day=0) — returns None."""
        assert format_eta({}) is None

    def test_non_dict_input_returns_none(self):
        """Non-dict input (string, list) returns None."""
        assert format_eta("March 15 14:30") is None  # type: ignore[arg-type]
        assert format_eta([3, 15, 14, 30]) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. AISIngestService._process_position_report() — null/invalid coordinates
# ---------------------------------------------------------------------------


class TestProcessPositionReportCoordinates:
    """Tests for _process_position_report coordinate validation."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    def _make_position_message(self, lat, lon, mmsi="123456789"):
        """Build a PositionReport JSON message with given coordinates."""
        payload = {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": mmsi,
                "time_utc": "2024-01-15T10:00:00Z",
                "ShipName": "TEST",
            },
            "Message": {
                "PositionReport": {
                    "Latitude": lat,
                    "Longitude": lon,
                    "Sog": 5.0,
                    "Cog": 90.0,
                    "TrueHeading": 88,
                    "NavigationalStatus": 0,
                    "RateOfTurn": 0,
                    "PositionAccuracy": True,
                }
            },
        }
        return json.dumps(payload)

    @pytest.mark.asyncio
    async def test_null_latitude_skips_publish(self, service):
        """A position report with Latitude=None must NOT be published."""
        await service.process_message(self._make_position_message(lat=None, lon=-123.4))
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_longitude_skips_publish(self, service):
        """A position report with Longitude=None must NOT be published."""
        await service.process_message(self._make_position_message(lat=48.5, lon=None))
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_null_coordinates_skips_publish(self, service):
        """A position report with both Latitude=None and Longitude=None is skipped."""
        await service.process_message(self._make_position_message(lat=None, lon=None))
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_coordinates_publishes(self, service):
        """A position report with valid coordinates is published."""
        await service.process_message(self._make_position_message(lat=48.5, lon=-123.4))
        service.js.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_position_payload_includes_all_fields(self, service):
        """Published payload includes mmsi, lat, lon, speed, course, heading, etc."""
        await service.process_message(self._make_position_message(lat=48.5, lon=-123.4))
        raw = service.js.publish.call_args[0][1]
        payload = json.loads(raw)
        assert payload["mmsi"] == "123456789"
        assert payload["lat"] == pytest.approx(48.5)
        assert payload["lon"] == pytest.approx(-123.4)
        assert payload["speed"] is not None
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_missing_position_report_key_skips_publish(self, service):
        """A PositionReport message where Message.PositionReport is absent is skipped."""
        msg = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {},  # No PositionReport key
            }
        )
        await service.process_message(msg)
        service.js.publish.assert_not_called()


# ---------------------------------------------------------------------------
# 6. AISIngestService._process_static_data() — field extraction
# ---------------------------------------------------------------------------


class TestProcessStaticDataFields:
    """Tests for _process_static_data with various field configurations."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    def _make_static_message(
        self,
        mmsi="123456789",
        static_data: dict | None = None,
        metadata: dict | None = None,
    ):
        """Build a ShipStaticData JSON message."""
        msg = {
            "MessageType": "ShipStaticData",
            "MetaData": {
                "MMSI": mmsi,
                "time_utc": "2024-01-15T10:00:00Z",
                "ShipName": "TEST",
                **(metadata or {}),
            },
            "Message": {"ShipStaticData": static_data or {}},
        }
        return json.dumps(msg)

    @pytest.mark.asyncio
    async def test_valid_static_data_published(self, service):
        """Complete static data is published to ais.static.{mmsi}."""
        static = {
            "ImoNumber": 1234567,
            "CallSign": "TEST1",
            "Name": "MV TEST",
            "Type": 70,
            "Dimension": {"A": 100, "B": 50, "C": 10, "D": 10},
            "Destination": "PORT",
            "Eta": {"Month": 6, "Day": 15, "Hour": 12, "Minute": 0},
            "MaximumStaticDraught": 8.5,
        }
        await service.process_message(self._make_static_message(static_data=static))
        service.js.publish.assert_called_once()
        subject = service.js.publish.call_args[0][0]
        assert subject == "ais.static.123456789"

    @pytest.mark.asyncio
    async def test_empty_dimension_dict_produces_none_fields(self, service):
        """When Dimension is an empty dict, all dimension fields are None."""
        static = {
            "ImoNumber": 1234567,
            "CallSign": "TEST1",
            "Name": "MV TEST",
            "Type": 70,
            "Dimension": {},  # Empty — no A/B/C/D keys
            "Destination": "PORT",
            "Eta": None,
            "MaximumStaticDraught": 8.5,
        }
        await service.process_message(self._make_static_message(static_data=static))
        service.js.publish.assert_called_once()
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] is None
        assert payload["dimension_b"] is None
        assert payload["dimension_c"] is None
        assert payload["dimension_d"] is None

    @pytest.mark.asyncio
    async def test_missing_dimension_key_produces_none_fields(self, service):
        """When Dimension key is absent, dimension fields are None."""
        static = {
            "ImoNumber": 1234567,
            "CallSign": "TEST1",
            "Name": "MV TEST",
            "Type": 70,
            # No "Dimension" key at all
            "Destination": "PORT",
            "Eta": None,
            "MaximumStaticDraught": 8.5,
        }
        await service.process_message(self._make_static_message(static_data=static))
        service.js.publish.assert_called_once()
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["dimension_a"] is None
        assert payload["dimension_b"] is None

    @pytest.mark.asyncio
    async def test_empty_static_data_skips_publish(self, service):
        """When ShipStaticData value is an empty dict, publish is skipped."""
        # _process_static_data returns early if `static` is falsy (empty dict)
        msg = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {"ShipStaticData": {}},  # Empty → falsy check triggers
            }
        )
        await service.process_message(msg)
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_name_falls_back_to_metadata_ship_name(self, service):
        """When Name is empty in static data, falls back to MetaData.ShipName."""
        static = {
            "ImoNumber": 1234567,
            "CallSign": "TEST1",
            "Name": "",  # Empty → falls back to metadata
            "Type": 70,
            "Dimension": {},
            "Destination": "PORT",
            "Eta": None,
            "MaximumStaticDraught": 8.5,
        }
        await service.process_message(
            self._make_static_message(
                static_data=static,
                metadata={"ShipName": "FALLBACK NAME"},
            )
        )
        service.js.publish.assert_called_once()
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["name"] == "FALLBACK NAME"

    @pytest.mark.asyncio
    async def test_eta_included_in_payload(self, service):
        """ETA is formatted and included in the published static payload."""
        static = {
            "ImoNumber": 1234567,
            "CallSign": "TEST1",
            "Name": "MV TEST",
            "Type": 70,
            "Dimension": {},
            "Destination": "PORT",
            "Eta": {"Month": 12, "Day": 25, "Hour": 10, "Minute": 0},
            "MaximumStaticDraught": 8.5,
        }
        await service.process_message(self._make_static_message(static_data=static))
        payload = json.loads(service.js.publish.call_args[0][1])
        assert payload["eta"] is not None
        assert "12-25T10:00:00Z" in payload["eta"]


# ---------------------------------------------------------------------------
# 7. publish_position() and publish_static() — NATS header and counter
# ---------------------------------------------------------------------------


class TestPublishPositionNATSDetails:
    """Tests for publish_position NATS header format and counter tracking."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_publish_position_uses_msg_id_header(self, service):
        """publish_position passes Nats-Msg-Id header to js.publish."""
        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        await service.publish_position("123456789", data)
        call_kwargs = service.js.publish.call_args[1]
        assert "headers" in call_kwargs
        assert "Nats-Msg-Id" in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_publish_position_msg_id_format_is_mmsi_timestamp(self, service):
        """Nats-Msg-Id for positions is '{mmsi}-{timestamp}'."""
        mmsi = "987654321"
        ts = "2024-06-01T12:34:56Z"
        data = {"mmsi": mmsi, "lat": 49.0, "lon": -124.0, "timestamp": ts}
        await service.publish_position(mmsi, data)
        headers = service.js.publish.call_args[1]["headers"]
        assert headers["Nats-Msg-Id"] == f"{mmsi}-{ts}"

    @pytest.mark.asyncio
    async def test_publish_position_increments_counter(self, service):
        """Each publish_position call increments messages_published by 1."""
        data = {
            "mmsi": "111",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        assert service.messages_published == 0
        await service.publish_position("111", data)
        assert service.messages_published == 1
        await service.publish_position(
            "111", {**data, "timestamp": "2024-01-15T10:01:00Z"}
        )
        assert service.messages_published == 2

    @pytest.mark.asyncio
    async def test_publish_position_updates_last_message_time(self, service):
        """publish_position sets last_message_time to the data timestamp."""
        ts = "2024-06-01T09:30:00Z"
        data = {"mmsi": "222", "lat": 48.5, "lon": -123.4, "timestamp": ts}
        await service.publish_position("222", data)
        assert service.last_message_time == ts

    @pytest.mark.asyncio
    async def test_publish_position_last_message_time_tracks_latest(self, service):
        """last_message_time always holds the most recent publish timestamp."""
        for ts in ["T08:00:00Z", "T09:00:00Z", "T10:30:00Z"]:
            full_ts = f"2024-06-01{ts}"
            await service.publish_position(
                "333", {"mmsi": "333", "lat": 48.5, "lon": -123.4, "timestamp": full_ts}
            )
        assert service.last_message_time == "2024-06-01T10:30:00Z"


class TestPublishStaticNATSDetails:
    """Tests for publish_static NATS header format and counter behaviour."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_publish_static_uses_static_prefix_in_msg_id(self, service):
        """Nats-Msg-Id for static data is 'static-{mmsi}-{timestamp}'."""
        mmsi = "123456789"
        ts = "2024-06-01T12:00:00Z"
        data = {"mmsi": mmsi, "name": "TEST", "timestamp": ts}
        await service.publish_static(mmsi, data)
        headers = service.js.publish.call_args[1]["headers"]
        assert headers["Nats-Msg-Id"] == f"static-{mmsi}-{ts}"

    @pytest.mark.asyncio
    async def test_publish_static_does_not_increment_messages_published(self, service):
        """publish_static does NOT increment messages_published (only position does)."""
        data = {"mmsi": "111", "name": "TEST", "timestamp": "2024-06-01T12:00:00Z"}
        await service.publish_static("111", data)
        assert service.messages_published == 0

    @pytest.mark.asyncio
    async def test_publish_static_does_not_update_last_message_time(self, service):
        """publish_static does NOT update last_message_time."""
        data = {"mmsi": "111", "name": "TEST", "timestamp": "2024-06-01T12:00:00Z"}
        await service.publish_static("111", data)
        assert service.last_message_time is None

    @pytest.mark.asyncio
    async def test_publish_static_publishes_to_correct_subject(self, service):
        """publish_static publishes to 'ais.static.{mmsi}'."""
        mmsi = "555444333"
        data = {"mmsi": mmsi, "name": "TEST", "timestamp": "2024-06-01T12:00:00Z"}
        await service.publish_static(mmsi, data)
        subject = service.js.publish.call_args[0][0]
        assert subject == f"ais.static.{mmsi}"


# ---------------------------------------------------------------------------
# 8. process_message() — routing and error handling
# ---------------------------------------------------------------------------


class TestProcessMessageRouting:
    """Tests for process_message routing between position/static handlers."""

    @pytest.fixture
    def service(self):
        svc = AISIngestService()
        svc.js = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_unknown_message_type_does_not_publish(self, service):
        """An unrecognised MessageType is silently ignored (no publish)."""
        msg = json.dumps(
            {
                "MessageType": "UnknownType",
                "MetaData": {"MMSI": "123456789", "time_utc": "2024-01-15T10:00:00Z"},
                "Message": {"UnknownType": {}},
            }
        )
        await service.process_message(msg)
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_json_does_not_raise(self, service):
        """Malformed JSON is caught by json.JSONDecodeError handler, no exception."""
        await service.process_message("this is not json at all {{{")
        # No exception should propagate
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_position_report_routed_to_position_handler(self, service):
        """PositionReport is routed to _process_position_report (publishes to ais.position.*)."""
        msg = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "111222333",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "VESSEL",
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
        await service.process_message(msg)
        service.js.publish.assert_called_once()
        subject = service.js.publish.call_args[0][0]
        assert subject.startswith("ais.position.")

    @pytest.mark.asyncio
    async def test_static_data_routed_to_static_handler(self, service):
        """ShipStaticData is routed to _process_static_data (publishes to ais.static.*)."""
        msg = json.dumps(
            {
                "MessageType": "ShipStaticData",
                "MetaData": {
                    "MMSI": "444555666",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "VESSEL",
                },
                "Message": {
                    "ShipStaticData": {
                        "ImoNumber": 1234567,
                        "CallSign": "TEST1",
                        "Name": "MV TEST",
                        "Type": 70,
                        "Dimension": {"A": 100, "B": 50, "C": 10, "D": 10},
                        "Destination": "PORT",
                        "Eta": None,
                        "MaximumStaticDraught": 8.5,
                    }
                },
            }
        )
        await service.process_message(msg)
        service.js.publish.assert_called_once()
        subject = service.js.publish.call_args[0][0]
        assert subject.startswith("ais.static.")

    @pytest.mark.asyncio
    async def test_missing_mmsi_in_metadata_does_not_publish(self, service):
        """Message with no MMSI in MetaData is silently dropped."""
        msg = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {"time_utc": "2024-01-15T10:00:00Z"},  # No MMSI
                "Message": {
                    "PositionReport": {
                        "Latitude": 48.5,
                        "Longitude": -123.4,
                    }
                },
            }
        )
        await service.process_message(msg)
        service.js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_position_report_increments_counter(self, service):
        """After routing a valid position report, messages_published is 1."""
        msg = json.dumps(
            {
                "MessageType": "PositionReport",
                "MetaData": {
                    "MMSI": "999888777",
                    "time_utc": "2024-01-15T10:00:00Z",
                    "ShipName": "",
                },
                "Message": {
                    "PositionReport": {
                        "Latitude": 49.0,
                        "Longitude": -124.0,
                        "Sog": 10.0,
                        "Cog": 180.0,
                        "TrueHeading": 178,
                        "NavigationalStatus": 0,
                        "RateOfTurn": 0,
                        "PositionAccuracy": True,
                    }
                },
            }
        )
        await service.process_message(msg)
        assert service.messages_published == 1
