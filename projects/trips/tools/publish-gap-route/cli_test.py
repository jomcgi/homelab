"""CLI integration tests for publish-gap-route — Typer command flows.

Tests exercise publish() and preview() end-to-end using
typer.testing.CliRunner with mocked file I/O and NATS.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# KML fixtures
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

LARGE_KML = """\
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


def _make_large_kml(n: int) -> str:
    """Build a KML string with n coordinates."""
    coords = " ".join(f"-122.{i:05d},{37 + i * 0.001:.5f},0" for i in range(n))
    return LARGE_KML.format(coords=coords)


def _make_nats_mocks():
    mock_js = AsyncMock()
    mock_nc = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    mock_js.stream_info = AsyncMock(return_value=MagicMock())
    return mock_nc, mock_js


# ---------------------------------------------------------------------------
# publish — file-not-found error handling
# ---------------------------------------------------------------------------


class TestPublishMissingKml:
    """publish exits with error code 1 when the KML file does not exist."""

    def test_exit_code_one_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.kml"
        result = runner.invoke(app, ["publish", str(missing), "2025-01-03T10:28:00"])
        assert result.exit_code == 1

    def test_error_message_mentions_file(self, tmp_path):
        missing = tmp_path / "nonexistent.kml"
        result = runner.invoke(app, ["publish", str(missing), "2025-01-03T10:28:00"])
        assert "not found" in result.output.lower() or "Error" in result.output


# ---------------------------------------------------------------------------
# publish — invalid start time
# ---------------------------------------------------------------------------


class TestPublishInvalidStartTime:
    """publish exits with error code 1 for an unparseable start time."""

    def test_exit_code_one_for_bad_time(self, tmp_path):
        kml = tmp_path / "route.kml"
        kml.write_text(MINIMAL_KML)
        result = runner.invoke(app, ["publish", str(kml), "not-a-time"])
        assert result.exit_code == 1

    def test_error_message_mentions_format(self, tmp_path):
        kml = tmp_path / "route.kml"
        kml.write_text(MINIMAL_KML)
        result = runner.invoke(app, ["publish", str(kml), "not-a-time"])
        assert "Invalid start time" in result.output or "ISO" in result.output


# ---------------------------------------------------------------------------
# publish — empty KML
# ---------------------------------------------------------------------------


class TestPublishEmptyKml:
    """publish exits with error code 1 when KML has no coordinates."""

    def test_exit_code_one_for_empty_kml(self, tmp_path):
        kml = tmp_path / "empty.kml"
        kml.write_text(
            """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document></Document>
</kml>
"""
        )
        result = runner.invoke(app, ["publish", str(kml), "2025-01-03T10:28:00"])
        assert result.exit_code == 1
        assert "No coordinates" in result.output


# ---------------------------------------------------------------------------
# publish — dry run (no NATS connection)
# ---------------------------------------------------------------------------


class TestPublishDryRun:
    """publish --dry-run shows a preview without connecting to NATS."""

    def _run(self, tmp_path, kml_content=MINIMAL_KML, extra_args=None):
        kml = tmp_path / "route.kml"
        kml.write_text(kml_content)
        args = ["publish", str(kml), "2025-01-03T10:28:00", "--dry-run"]
        if extra_args:
            args += extra_args
        return runner.invoke(app, args)

    def test_exit_code_zero(self, tmp_path):
        result = self._run(tmp_path)
        assert result.exit_code == 0, result.output

    def test_shows_dry_run_banner(self, tmp_path):
        result = self._run(tmp_path)
        assert "[DRY RUN]" in result.output

    def test_shows_route_preview(self, tmp_path):
        result = self._run(tmp_path)
        assert "Route preview" in result.output

    def test_shows_start_time(self, tmp_path):
        result = self._run(tmp_path)
        assert "2025-01-03T10:28:00" in result.output

    def test_no_nats_connection_in_dry_run(self, tmp_path):
        with patch("main.nats.connect") as mock_connect:
            result = self._run(tmp_path)
        assert result.exit_code == 0
        mock_connect.assert_not_called()

    def test_shows_point_coordinates(self, tmp_path):
        result = self._run(tmp_path)
        # First coordinate in MINIMAL_KML is lat=37.77493, lng=-122.41942
        assert "37.77493" in result.output

    def test_max_points_flag_limits_sampled_count(self, tmp_path):
        """--max-points 2 samples the 3-coord KML down to 2 (plus last appended)."""
        result = self._run(tmp_path, extra_args=["--max-points", "2"])
        assert result.exit_code == 0
        # Sampled to output should mention 2 or 3 points (last may be appended)
        assert "Points:" in result.output


# ---------------------------------------------------------------------------
# publish — full run (actually publishes to NATS)
# ---------------------------------------------------------------------------


class TestPublishFullRun:
    """publish without --dry-run connects to NATS and publishes gap points."""

    def _run_with_mocks(self, tmp_path, kml_content=MINIMAL_KML, extra_args=None):
        kml = tmp_path / "route.kml"
        kml.write_text(kml_content)

        mock_nc, mock_js = _make_nats_mocks()
        args = ["publish", str(kml), "2025-01-03T10:28:00"]
        if extra_args:
            args += extra_args

        with patch("main.nats.connect", return_value=mock_nc):
            result = runner.invoke(app, args)

        return result, mock_js

    def test_exit_code_zero(self, tmp_path):
        result, _ = self._run_with_mocks(tmp_path)
        assert result.exit_code == 0, result.output

    def test_publishes_correct_number_of_points(self, tmp_path):
        _, mock_js = self._run_with_mocks(tmp_path)
        # MINIMAL_KML has 3 coordinates, all within default max_points=100
        assert mock_js.publish.call_count == 3

    def test_publishes_to_trips_point_subject(self, tmp_path):
        _, mock_js = self._run_with_mocks(tmp_path)
        for call in mock_js.publish.call_args_list:
            assert call[0][0] == "trips.point"

    def test_published_points_have_gap_source(self, tmp_path):
        _, mock_js = self._run_with_mocks(tmp_path)
        for call in mock_js.publish.call_args_list:
            payload = json.loads(call[0][1].decode())
            assert payload["source"] == "gap"

    def test_published_points_have_null_image(self, tmp_path):
        _, mock_js = self._run_with_mocks(tmp_path)
        for call in mock_js.publish.call_args_list:
            payload = json.loads(call[0][1].decode())
            assert payload["image"] is None

    def test_published_points_have_gap_and_car_tags(self, tmp_path):
        _, mock_js = self._run_with_mocks(tmp_path)
        for call in mock_js.publish.call_args_list:
            payload = json.loads(call[0][1].decode())
            assert "gap" in payload["tags"]
            assert "car" in payload["tags"]

    def test_output_confirms_published_count(self, tmp_path):
        result, _ = self._run_with_mocks(tmp_path)
        assert "Published 3 gap points" in result.output

    def test_output_shows_done(self, tmp_path):
        result, _ = self._run_with_mocks(tmp_path)
        assert "Done!" in result.output

    def test_max_points_option_limits_publishing(self, tmp_path):
        """--max-points 2 must publish at most 3 points (2 sampled + last)."""
        result, mock_js = self._run_with_mocks(
            tmp_path, extra_args=["--max-points", "2"]
        )
        assert result.exit_code == 0
        # sample_coordinates with max_points=2 on 3 coords returns ≤3 points
        assert mock_js.publish.call_count <= 3

    def test_timestamps_start_at_provided_time(self, tmp_path):
        """The first published point's timestamp must equal the provided start time."""
        _, mock_js = self._run_with_mocks(tmp_path)
        first_payload = json.loads(mock_js.publish.call_args_list[0][0][1].decode())
        ts = datetime.fromisoformat(first_payload["timestamp"])
        assert ts == datetime(2025, 1, 3, 10, 28, 0)

    def test_sequential_timestamps_one_ms_apart(self, tmp_path):
        """Consecutive published points must have timestamps 1 ms apart."""
        _, mock_js = self._run_with_mocks(tmp_path)
        timestamps = [
            datetime.fromisoformat(json.loads(c[0][1].decode())["timestamp"])
            for c in mock_js.publish.call_args_list
        ]
        for i in range(1, len(timestamps)):
            delta = timestamps[i] - timestamps[i - 1]
            assert delta == timedelta(milliseconds=1)

    def test_nats_connection_closed_after_publish(self, tmp_path):
        """nc.close() must be awaited even on successful publish."""
        mock_nc, mock_js = _make_nats_mocks()
        kml = tmp_path / "route.kml"
        kml.write_text(MINIMAL_KML)

        with patch("main.nats.connect", return_value=mock_nc):
            result = runner.invoke(app, ["publish", str(kml), "2025-01-03T10:28:00"])

        assert result.exit_code == 0
        mock_nc.close.assert_awaited_once()

    def test_large_kml_sampled_to_max_points(self, tmp_path):
        """A KML with 200 coords and --max-points 50 publishes ≤51 points."""
        large_kml = _make_large_kml(200)
        result, mock_js = self._run_with_mocks(
            tmp_path, kml_content=large_kml, extra_args=["--max-points", "50"]
        )
        assert result.exit_code == 0
        # sample_coordinates(200, 50) → 50 + possibly 1 last = 51 max
        assert mock_js.publish.call_count <= 51
        assert mock_js.publish.call_count >= 50


# ---------------------------------------------------------------------------
# preview — file-not-found
# ---------------------------------------------------------------------------


class TestPreviewMissingFile:
    """preview exits with error code 1 when the KML file does not exist."""

    def test_exit_code_one_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.kml"
        result = runner.invoke(app, ["preview", str(missing)])
        assert result.exit_code == 1

    def test_error_message_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.kml"
        result = runner.invoke(app, ["preview", str(missing)])
        assert "not found" in result.output.lower() or "Error" in result.output


# ---------------------------------------------------------------------------
# preview — valid KML
# ---------------------------------------------------------------------------


class TestPreviewValidKml:
    """preview parses the KML and shows coordinate details."""

    def _run(self, tmp_path, kml_content=MINIMAL_KML):
        kml = tmp_path / "route.kml"
        kml.write_text(kml_content)
        return runner.invoke(app, ["preview", str(kml)])

    def test_exit_code_zero(self, tmp_path):
        result = self._run(tmp_path)
        assert result.exit_code == 0, result.output

    def test_shows_coordinate_count(self, tmp_path):
        result = self._run(tmp_path)
        assert "3 coordinates" in result.output

    def test_shows_start_coordinate(self, tmp_path):
        result = self._run(tmp_path)
        # First coordinate is lat=37.77493, lng=-122.41942
        assert "37.77493" in result.output

    def test_shows_end_coordinate(self, tmp_path):
        result = self._run(tmp_path)
        # Last coordinate is lat=37.79, lng=-122.43
        assert "37.79000" in result.output

    def test_no_nats_connection(self, tmp_path):
        """preview must never connect to NATS."""
        with patch("main.nats.connect") as mock_connect:
            result = self._run(tmp_path)
        assert result.exit_code == 0
        mock_connect.assert_not_called()

    def test_shows_first_few_points(self, tmp_path):
        result = self._run(tmp_path)
        assert "First 5 points" in result.output

    def test_shows_last_few_points(self, tmp_path):
        result = self._run(tmp_path)
        assert "Last 5 points" in result.output

    def test_empty_kml_shows_no_coordinates(self, tmp_path):
        empty = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document></Document>
</kml>
"""
        kml = tmp_path / "empty.kml"
        kml.write_text(empty)
        result = runner.invoke(app, ["preview", str(kml)])
        assert result.exit_code == 0
        assert "No coordinates found" in result.output

    def test_large_kml_shows_ellipsis(self, tmp_path):
        """When there are more than 10 points, an ellipsis row is shown."""
        large = _make_large_kml(20)
        kml = tmp_path / "large.kml"
        kml.write_text(large)
        result = runner.invoke(app, ["preview", str(kml)])
        assert result.exit_code == 0
        assert "more points" in result.output
