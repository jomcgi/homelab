"""Tests for publish-gap-route main.py."""

import json
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from main import (
    GAP_KEY_NAMESPACE,
    generate_gap_id,
    parse_kml_coordinates,
    publish_gap_points,
    sample_coordinates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>
          {coords}
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def _write_kml(tmp_path: Path, coords_text: str) -> Path:
    """Write a minimal KML file with the given coordinate text."""
    kml = _KML_TEMPLATE.format(coords=coords_text)
    kml_file = tmp_path / "route.kml"
    kml_file.write_text(kml)
    return kml_file


# ---------------------------------------------------------------------------
# TestParseKmlCoordinates
# ---------------------------------------------------------------------------


class TestParseKmlCoordinates:
    def test_parses_single_coordinate(self, tmp_path):
        kml_file = _write_kml(tmp_path, "-123.12345,49.28270,0")
        coords = parse_kml_coordinates(kml_file)
        assert len(coords) == 1
        lat, lng = coords[0]
        assert pytest.approx(lat) == 49.28270
        assert pytest.approx(lng) == -123.12345

    def test_parses_multiple_coordinates(self, tmp_path):
        kml_file = _write_kml(
            tmp_path,
            "-123.0,49.0,0 -124.0,50.0,0 -125.0,51.0,0",
        )
        coords = parse_kml_coordinates(kml_file)
        assert len(coords) == 3

    def test_coord_order_lat_lng(self, tmp_path):
        """KML stores as lng,lat,alt — we should return (lat, lng)."""
        kml_file = _write_kml(tmp_path, "-123.5,49.5,0")
        coords = parse_kml_coordinates(kml_file)
        lat, lng = coords[0]
        assert pytest.approx(lat) == 49.5
        assert pytest.approx(lng) == -123.5

    def test_returns_empty_for_no_linestring(self, tmp_path):
        kml = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <Point><coordinates>-123.0,49.0,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>"""
        kml_file = tmp_path / "points.kml"
        kml_file.write_text(kml)
        coords = parse_kml_coordinates(kml_file)
        assert coords == []

    def test_returns_empty_for_empty_coordinates(self, tmp_path):
        kml = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates></coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""
        kml_file = tmp_path / "empty.kml"
        kml_file.write_text(kml)
        coords = parse_kml_coordinates(kml_file)
        assert coords == []

    def test_multiple_linestrings_combined(self, tmp_path):
        kml = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString><coordinates>-123.0,49.0,0 -124.0,50.0,0</coordinates></LineString>
    </Placemark>
    <Placemark>
      <LineString><coordinates>-125.0,51.0,0</coordinates></LineString>
    </Placemark>
  </Document>
</kml>"""
        kml_file = tmp_path / "multi.kml"
        kml_file.write_text(kml)
        coords = parse_kml_coordinates(kml_file)
        assert len(coords) == 3

    def test_altitude_ignored(self, tmp_path):
        """Third coordinate component (altitude) is ignored."""
        kml_file = _write_kml(tmp_path, "-123.0,49.0,9999.0")
        coords = parse_kml_coordinates(kml_file)
        lat, lng = coords[0]
        assert pytest.approx(lat) == 49.0
        assert pytest.approx(lng) == -123.0

    def test_handles_whitespace_around_coordinates(self, tmp_path):
        kml_file = _write_kml(tmp_path, "\n  -123.0,49.0,0  \n  -124.0,50.0,0  \n")
        coords = parse_kml_coordinates(kml_file)
        assert len(coords) == 2


# ---------------------------------------------------------------------------
# TestSampleCoordinates
# ---------------------------------------------------------------------------


class TestSampleCoordinates:
    def _make_coords(self, n: int) -> list[tuple[float, float]]:
        return [(float(i), float(-i)) for i in range(n)]

    def test_returns_all_when_at_or_below_max(self):
        coords = self._make_coords(10)
        result = sample_coordinates(coords, max_points=10)
        assert result == coords

    def test_returns_all_when_below_max(self):
        coords = self._make_coords(5)
        result = sample_coordinates(coords, max_points=100)
        assert result == coords

    def test_reduces_to_max_points(self):
        coords = self._make_coords(200)
        result = sample_coordinates(coords, max_points=100)
        # Should be close to 100 (could be 101 due to appending last)
        assert len(result) <= 102

    def test_always_includes_last_point(self):
        coords = self._make_coords(1000)
        result = sample_coordinates(coords, max_points=7)
        assert result[-1] == coords[-1]

    def test_first_point_included(self):
        coords = self._make_coords(100)
        result = sample_coordinates(coords, max_points=10)
        assert result[0] == coords[0]

    def test_empty_list_returns_empty(self):
        result = sample_coordinates([], max_points=10)
        assert result == []

    def test_single_coord_returns_single(self):
        coords = [(49.0, -123.0)]
        result = sample_coordinates(coords, max_points=100)
        assert result == coords


# ---------------------------------------------------------------------------
# TestGenerateGapId
# ---------------------------------------------------------------------------


class TestGenerateGapId:
    def test_returns_string_starting_with_gap_prefix(self):
        gap_id = generate_gap_id(49.0, -123.0, "2025-07-01T10:00:00")
        assert gap_id.startswith("gap_")

    def test_id_has_12_hex_chars_after_prefix(self):
        gap_id = generate_gap_id(49.0, -123.0, "2025-07-01T10:00:00")
        hex_part = gap_id[4:]  # After "gap_"
        assert len(hex_part) == 12
        int(hex_part, 16)  # Should be valid hex

    def test_deterministic_same_inputs(self):
        id1 = generate_gap_id(49.12345, -123.45678, "2025-07-01T10:00:00")
        id2 = generate_gap_id(49.12345, -123.45678, "2025-07-01T10:00:00")
        assert id1 == id2

    def test_different_coords_produce_different_ids(self):
        id1 = generate_gap_id(49.0, -123.0, "2025-07-01T10:00:00")
        id2 = generate_gap_id(50.0, -124.0, "2025-07-01T10:00:00")
        assert id1 != id2

    def test_different_timestamps_produce_different_ids(self):
        id1 = generate_gap_id(49.0, -123.0, "2025-07-01T10:00:00")
        id2 = generate_gap_id(49.0, -123.0, "2025-07-01T10:00:01")
        assert id1 != id2

    def test_uses_five_decimal_precision(self):
        """IDs generated with coordinates rounded to 5 decimals should match."""
        id1 = generate_gap_id(49.123456789, -123.0, "2025-07-01T10:00:00")
        id2 = generate_gap_id(49.12346, -123.0, "2025-07-01T10:00:00")
        # Both round to 49.12346 at 5 decimal places
        assert id1 == id2


# ---------------------------------------------------------------------------
# TestPublishGapPoints
# ---------------------------------------------------------------------------


class TestPublishGapPoints:
    @pytest.mark.asyncio
    async def test_returns_correct_count(self):
        js = AsyncMock()
        coords = [(49.0 + i * 0.01, -123.0 + i * 0.01) for i in range(5)]
        start = datetime(2025, 7, 1, 10, 0, 0)

        count = await publish_gap_points(js, coords, start)
        assert count == 5

    @pytest.mark.asyncio
    async def test_publishes_to_trips_point_subject(self):
        js = AsyncMock()
        coords = [(49.0, -123.0)]
        start = datetime(2025, 7, 1, 10, 0, 0)

        await publish_gap_points(js, coords, start)

        subject, _ = js.publish.call_args[0]
        assert subject == "trips.point"

    @pytest.mark.asyncio
    async def test_point_structure(self):
        js = AsyncMock()
        coords = [(49.12345, -123.45678)]
        start = datetime(2025, 7, 1, 10, 0, 0)

        await publish_gap_points(js, coords, start)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert "id" in msg
        assert msg["lat"] == round(49.12345, 5)
        assert msg["lng"] == round(-123.45678, 5)
        assert msg["image"] is None
        assert msg["source"] == "gap"
        assert "gap" in msg["tags"]
        assert "car" in msg["tags"]

    @pytest.mark.asyncio
    async def test_timestamps_sequential_milliseconds(self):
        js = AsyncMock()
        coords = [(49.0 + i * 0.001, -123.0) for i in range(3)]
        start = datetime(2025, 7, 1, 10, 0, 0)

        await publish_gap_points(js, coords, start)

        calls = js.publish.call_args_list
        timestamps = [
            json.loads(call[0][1].decode())["timestamp"] for call in calls
        ]

        t0 = datetime.fromisoformat(timestamps[0])
        t1 = datetime.fromisoformat(timestamps[1])
        t2 = datetime.fromisoformat(timestamps[2])

        assert t1 - t0 == timedelta(milliseconds=1)
        assert t2 - t1 == timedelta(milliseconds=1)

    @pytest.mark.asyncio
    async def test_first_timestamp_matches_start(self):
        js = AsyncMock()
        coords = [(49.0, -123.0)]
        start = datetime(2025, 7, 1, 10, 28, 0)

        await publish_gap_points(js, coords, start)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["timestamp"] == start.isoformat()

    @pytest.mark.asyncio
    async def test_empty_coords_returns_zero(self):
        js = AsyncMock()
        count = await publish_gap_points(js, [], datetime(2025, 7, 1))
        assert count == 0
        js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_ids_are_deterministic(self):
        """Publishing the same coords twice should produce the same IDs."""
        coords = [(49.0, -123.0), (50.0, -124.0)]
        start = datetime(2025, 7, 1, 10, 0, 0)

        js1 = AsyncMock()
        await publish_gap_points(js1, coords, start)
        ids1 = [
            json.loads(call[0][1].decode())["id"]
            for call in js1.publish.call_args_list
        ]

        js2 = AsyncMock()
        await publish_gap_points(js2, coords, start)
        ids2 = [
            json.loads(call[0][1].decode())["id"]
            for call in js2.publish.call_args_list
        ]

        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_coordinates_rounded_to_5_decimals(self):
        js = AsyncMock()
        coords = [(49.123456789, -123.987654321)]
        start = datetime(2025, 7, 1)

        await publish_gap_points(js, coords, start)

        _, payload = js.publish.call_args[0]
        msg = json.loads(payload.decode())
        assert msg["lat"] == round(49.123456789, 5)
        assert msg["lng"] == round(-123.987654321, 5)
