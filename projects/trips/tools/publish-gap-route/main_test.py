"""Unit tests for publish-gap-route/main.py — get_jetstream and edge cases.

Supplements gap_route_test.py by covering:
- get_jetstream: creates stream when it does not exist, returns (nc, js)
- parse_kml_coordinates: KML without altitude component, single coordinate
- publish_gap_points: tags field in published points
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

import nats.js.errors

from main import (
    GAP_KEY_NAMESPACE,
    generate_gap_id,
    get_jetstream,
    parse_kml_coordinates,
    publish_gap_points,
    sample_coordinates,
)


# ---------------------------------------------------------------------------
# get_jetstream
# ---------------------------------------------------------------------------


class TestGetJetstream:
    """NATS JetStream connection factory."""

    @pytest.mark.asyncio
    async def test_returns_nc_and_js_tuple(self):
        """get_jetstream returns a 2-tuple of (nc, js)."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)
        mock_js.stream_info = AsyncMock(return_value=MagicMock())

        with patch("main.nats.connect", return_value=mock_nc):
            nc, js = await get_jetstream()

        assert nc is mock_nc
        assert js is mock_js

    @pytest.mark.asyncio
    async def test_calls_nats_connect_with_configured_url(self):
        import main as _main_mod

        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)
        mock_js.stream_info = AsyncMock(return_value=MagicMock())

        with patch("main.nats.connect", return_value=mock_nc) as mock_connect:
            await get_jetstream()

        mock_connect.assert_awaited_once_with(_main_mod.NATS_URL)

    @pytest.mark.asyncio
    async def test_checks_for_existing_stream(self):
        """get_jetstream calls js.stream_info to check for the 'trips' stream."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)
        mock_js.stream_info = AsyncMock(return_value=MagicMock())

        with patch("main.nats.connect", return_value=mock_nc):
            await get_jetstream()

        mock_js.stream_info.assert_awaited_once_with("trips")

    @pytest.mark.asyncio
    async def test_creates_stream_when_not_found(self):
        """When the stream is missing, get_jetstream creates it via add_stream."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)
        mock_js.stream_info = AsyncMock(side_effect=nats.js.errors.NotFoundError())
        mock_js.add_stream = AsyncMock()

        with patch("main.nats.connect", return_value=mock_nc):
            await get_jetstream()

        mock_js.add_stream.assert_awaited_once_with(name="trips", subjects=["trips.>"])

    @pytest.mark.asyncio
    async def test_does_not_create_stream_when_it_exists(self):
        """When stream_info succeeds, add_stream must not be called."""
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_nc.jetstream = MagicMock(return_value=mock_js)
        mock_js.stream_info = AsyncMock(return_value=MagicMock())
        mock_js.add_stream = AsyncMock()

        with patch("main.nats.connect", return_value=mock_nc):
            await get_jetstream()

        mock_js.add_stream.assert_not_called()


# ---------------------------------------------------------------------------
# parse_kml_coordinates — additional edge cases
# ---------------------------------------------------------------------------

_KML_NO_ALT = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>
          -122.0,45.0
          -122.1,45.1
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""

_KML_SINGLE_COORD = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>-135.0,60.5,100</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""

_KML_WHITESPACE_ONLY = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>   </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


class TestParseKmlCoordinatesEdgeCases:
    """Edge cases not covered by gap_route_test.py."""

    def test_coordinates_without_altitude(self, tmp_path):
        """KML coordinates that omit the altitude component are still parsed."""
        kml_file = tmp_path / "no_alt.kml"
        kml_file.write_text(_KML_NO_ALT)

        coords = parse_kml_coordinates(kml_file)

        # Parser requires at least 2 parts; no-alt has exactly 2.
        assert len(coords) == 2
        lat, lng = coords[0]
        assert lat == pytest.approx(45.0)
        assert lng == pytest.approx(-122.0)

    def test_single_coordinate(self, tmp_path):
        kml_file = tmp_path / "single.kml"
        kml_file.write_text(_KML_SINGLE_COORD)

        coords = parse_kml_coordinates(kml_file)

        assert len(coords) == 1
        lat, lng = coords[0]
        assert lat == pytest.approx(60.5)
        assert lng == pytest.approx(-135.0)

    def test_whitespace_only_coordinates_element_returns_empty(self, tmp_path):
        """A <coordinates> element containing only whitespace produces no points."""
        kml_file = tmp_path / "ws.kml"
        kml_file.write_text(_KML_WHITESPACE_ONLY)

        coords = parse_kml_coordinates(kml_file)

        assert coords == []


# ---------------------------------------------------------------------------
# sample_coordinates — additional edge cases
# ---------------------------------------------------------------------------


class TestSampleCoordinatesEdgeCases:
    """Edge cases not in gap_route_test.py."""

    def test_empty_input_returns_empty(self):
        assert sample_coordinates([], max_points=10) == []

    def test_single_coord_returned_unchanged(self):
        coords = [(45.0, -122.0)]
        result = sample_coordinates(coords, max_points=100)
        assert result == coords

    def test_two_coords_returned_unchanged(self):
        coords = [(45.0, -122.0), (46.0, -123.0)]
        result = sample_coordinates(coords, max_points=100)
        assert result == coords

    def test_max_points_of_two_includes_first_and_last(self):
        coords = [(float(i), float(i)) for i in range(10)]
        result = sample_coordinates(coords, max_points=2)
        assert result[0] == coords[0]
        assert result[-1] == coords[-1]

    def test_result_contains_only_input_coords(self):
        """Sampled coordinates must all come from the input list."""
        coords = [(float(i), -float(i)) for i in range(50)]
        result = sample_coordinates(coords, max_points=10)
        input_set = set(coords)
        assert all(c in input_set for c in result)


# ---------------------------------------------------------------------------
# publish_gap_points — additional field checks
# ---------------------------------------------------------------------------


class TestPublishGapPointsAdditional:
    """Additional field validation for published gap points."""

    @pytest.mark.asyncio
    async def test_published_points_have_gap_and_car_tags(self):
        """Gap points are tagged with both 'gap' and 'car'."""
        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert "gap" in payload["tags"]
        assert "car" in payload["tags"]

    @pytest.mark.asyncio
    async def test_published_point_id_starts_with_gap_prefix(self):
        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        assert payload["id"].startswith("gap_")

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_coords(self):
        mock_js = AsyncMock()
        count = await publish_gap_points(mock_js, [], datetime(2025, 1, 1))
        assert count == 0

    @pytest.mark.asyncio
    async def test_first_point_timestamp_equals_start(self):
        """The first gap point's timestamp should equal start_time exactly."""
        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 3, 15, 8, 30, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        ts = datetime.fromisoformat(payload["timestamp"])
        assert ts == start

    @pytest.mark.asyncio
    async def test_points_contain_required_fields(self):
        """Every published point must contain id, lat, lng, timestamp, image, source, tags."""
        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1].decode())
        for field in ("id", "lat", "lng", "timestamp", "image", "source", "tags"):
            assert field in payload, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# generate_gap_id — additional tests
# ---------------------------------------------------------------------------


class TestGenerateGapIdAdditional:
    """Additional coverage not in gap_route_test.py."""

    def test_id_consists_of_alphanumeric_prefix_and_hex(self):
        gap_id = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        assert gap_id.startswith("gap_")
        hex_part = gap_id[4:]  # strip "gap_"
        assert len(hex_part) == 12
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_negative_coordinates_produce_valid_id(self):
        gap_id = generate_gap_id(-33.8688, 151.2093, "2025-01-01T12:00:00")
        assert gap_id.startswith("gap_")
        assert len(gap_id) == 16

    def test_same_coords_different_timestamps_produce_different_ids(self):
        id1 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:01")
        assert id1 != id2
