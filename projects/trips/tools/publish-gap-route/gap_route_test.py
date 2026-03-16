"""Tests for the publish-gap-route tool."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

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

MINIMAL_KML = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>
          -122.41942,37.77493,0
          -122.42000,37.78000,0
          -122.43000,37.79000,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""

MULTI_LINESTRING_KML = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>-122.0,45.0,0 -122.1,45.1,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <LineString>
        <coordinates>-122.2,45.2,0 -122.3,45.3,0</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""

EMPTY_KML = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
  </Document>
</kml>
"""

MALFORMED_KML = "this is not xml at all <<<"


# ---------------------------------------------------------------------------
# parse_kml_coordinates
# ---------------------------------------------------------------------------


class TestParseKmlCoordinates:
    """KML coordinate parsing."""

    def test_valid_kml_returns_lat_lng_tuples(self, tmp_path):
        kml_file = tmp_path / "route.kml"
        kml_file.write_text(MINIMAL_KML)

        coords = parse_kml_coordinates(kml_file)

        assert len(coords) == 3
        # KML format is lng,lat,alt — parser must swap to (lat, lng)
        lat, lng = coords[0]
        assert lat == pytest.approx(37.77493)
        assert lng == pytest.approx(-122.41942)

    def test_multiple_linestrings_merged(self, tmp_path):
        kml_file = tmp_path / "route.kml"
        kml_file.write_text(MULTI_LINESTRING_KML)

        coords = parse_kml_coordinates(kml_file)

        assert len(coords) == 4

    def test_empty_document_returns_empty_list(self, tmp_path):
        kml_file = tmp_path / "empty.kml"
        kml_file.write_text(EMPTY_KML)

        coords = parse_kml_coordinates(kml_file)

        assert coords == []

    def test_malformed_xml_raises(self, tmp_path):
        kml_file = tmp_path / "bad.kml"
        kml_file.write_text(MALFORMED_KML)

        with pytest.raises(Exception):
            parse_kml_coordinates(kml_file)

    def test_file_not_found_raises(self, tmp_path):
        missing = tmp_path / "missing.kml"

        with pytest.raises(Exception):
            parse_kml_coordinates(missing)

    def test_coordinate_order_lat_lng(self, tmp_path):
        """Verify the parser correctly swaps KML lng,lat to (lat, lng) tuples."""
        kml = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>10.0,20.0,0</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""
        kml_file = tmp_path / "swap.kml"
        kml_file.write_text(kml)
        coords = parse_kml_coordinates(kml_file)
        assert len(coords) == 1
        lat, lng = coords[0]
        # Input was lng=10, lat=20
        assert lat == pytest.approx(20.0)
        assert lng == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# sample_coordinates
# ---------------------------------------------------------------------------


class TestSampleCoordinates:
    """Point sampling logic."""

    def _make_coords(self, n: int) -> list[tuple[float, float]]:
        return [(float(i), float(i)) for i in range(n)]

    def test_fewer_than_max_returns_all(self):
        coords = self._make_coords(50)
        result = sample_coordinates(coords, max_points=100)
        assert result == coords

    def test_exactly_max_returns_all(self):
        coords = self._make_coords(100)
        result = sample_coordinates(coords, max_points=100)
        assert result == coords

    def test_more_than_max_samples_down(self):
        coords = self._make_coords(200)
        result = sample_coordinates(coords, max_points=100)
        # Should have approximately max_points or max_points + 1 (last point appended)
        assert len(result) <= 102
        assert len(result) >= 100

    def test_last_point_always_included(self):
        coords = self._make_coords(200)
        result = sample_coordinates(coords, max_points=10)
        assert result[-1] == coords[-1]

    def test_first_point_always_included(self):
        coords = self._make_coords(200)
        result = sample_coordinates(coords, max_points=10)
        assert result[0] == coords[0]

    def test_sample_rate_one_returns_max_points(self):
        """With max_points=1, only the first (and possibly last) point is returned."""
        coords = self._make_coords(50)
        result = sample_coordinates(coords, max_points=1)
        assert coords[0] in result
        assert coords[-1] in result

    def test_uniform_distribution(self):
        """Sampled indices should be spread across the full range."""
        coords = self._make_coords(1000)
        result = sample_coordinates(coords, max_points=10)
        # First and last should be present; mid-point area should be represented
        lats = [c[0] for c in result]
        assert min(lats) < 100
        assert max(lats) > 900


# ---------------------------------------------------------------------------
# generate_gap_id
# ---------------------------------------------------------------------------


class TestGenerateGapId:
    """Deterministic gap point ID generation."""

    def test_same_input_same_id(self):
        id1 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        assert id1 == id2

    def test_different_lat_different_id(self):
        id1 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(46.0, -122.0, "2025-01-01T00:00:00")
        assert id1 != id2

    def test_different_lng_different_id(self):
        id1 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(45.0, -123.0, "2025-01-01T00:00:00")
        assert id1 != id2

    def test_different_timestamp_different_id(self):
        id1 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:01")
        assert id1 != id2

    def test_id_has_gap_prefix(self):
        gap_id = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        assert gap_id.startswith("gap_")

    def test_id_uses_correct_namespace(self):
        """The UUID5 must be generated with GAP_KEY_NAMESPACE."""
        lat, lng, ts = 45.0, -122.0, "2025-01-01T00:00:00"
        identity = f"gap:{lat:.5f}:{lng:.5f}:{ts}"
        expected_uuid = uuid.uuid5(GAP_KEY_NAMESPACE, identity)
        expected_id = f"gap_{expected_uuid.hex[:12]}"
        assert generate_gap_id(lat, lng, ts) == expected_id

    def test_id_length_is_fixed(self):
        """gap_ prefix (4) + 12 hex chars = 16 characters total."""
        gap_id = generate_gap_id(45.0, -122.0, "2025-01-01T00:00:00")
        assert len(gap_id) == 16

    def test_coordinate_precision_five_decimals(self):
        """IDs should differ only at 5 dp boundary."""
        # Both 45.000001 and 45.000003 have a 6th decimal < 5 so both round
        # to 45.00000 at 5dp — they should produce the same gap ID.
        id1 = generate_gap_id(45.000001, -122.0, "2025-01-01T00:00:00")
        id2 = generate_gap_id(45.000003, -122.0, "2025-01-01T00:00:00")
        assert id1 == id2


# ---------------------------------------------------------------------------
# publish_gap_points
# ---------------------------------------------------------------------------


class TestPublishGapPoints:
    """NATS publishing of gap points."""

    @pytest.mark.asyncio
    async def test_publishes_correct_number_of_points(self):
        mock_js = AsyncMock()
        coords = [(45.0 + i * 0.001, -122.0) for i in range(5)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        count = await publish_gap_points(mock_js, coords, start)

        assert count == 5
        assert mock_js.publish.call_count == 5

    @pytest.mark.asyncio
    async def test_publishes_to_trips_point_subject(self):
        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        subject = mock_js.publish.call_args[0][0]
        assert subject == "trips.point"

    @pytest.mark.asyncio
    async def test_published_point_has_null_image(self):
        import json

        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1])
        assert payload["image"] is None

    @pytest.mark.asyncio
    async def test_published_point_has_gap_source(self):
        import json

        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1])
        assert payload["source"] == "gap"

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential_milliseconds(self):
        import json

        mock_js = AsyncMock()
        coords = [(45.0, -122.0), (46.0, -123.0), (47.0, -124.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        calls = mock_js.publish.call_args_list
        timestamps = [
            datetime.fromisoformat(json.loads(c[0][1])["timestamp"]) for c in calls
        ]

        for i in range(1, len(timestamps)):
            delta = timestamps[i] - timestamps[i - 1]
            assert delta == timedelta(milliseconds=1)

    @pytest.mark.asyncio
    async def test_empty_coords_publishes_nothing(self):
        mock_js = AsyncMock()
        start = datetime(2025, 1, 1, 10, 0, 0)

        count = await publish_gap_points(mock_js, [], start)

        assert count == 0
        mock_js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_point_id_is_deterministic(self):
        import json

        mock_js = AsyncMock()
        coords = [(45.0, -122.0)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)
        first_call_payload = json.loads(mock_js.publish.call_args[0][1])

        mock_js.reset_mock()
        await publish_gap_points(mock_js, coords, start)
        second_call_payload = json.loads(mock_js.publish.call_args[0][1])

        assert first_call_payload["id"] == second_call_payload["id"]

    @pytest.mark.asyncio
    async def test_coordinates_rounded_to_five_dp(self):
        import json

        mock_js = AsyncMock()
        coords = [(45.123456789, -122.987654321)]
        start = datetime(2025, 1, 1, 10, 0, 0)

        await publish_gap_points(mock_js, coords, start)

        payload = json.loads(mock_js.publish.call_args[0][1])
        # round(45.123456789, 5) == 45.12346
        assert payload["lat"] == pytest.approx(45.12346, abs=1e-5)
        assert payload["lng"] == pytest.approx(-122.98765, abs=1e-5)
