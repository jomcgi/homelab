"""Unit tests for the API module."""

import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from projects.stargazer.backend.api import StargazerAPIHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockWFile:
    """In-memory sink for response bytes."""

    def __init__(self):
        self._buf = BytesIO()

    def write(self, data: bytes) -> None:
        self._buf.write(data)

    def getvalue(self) -> bytes:
        return self._buf.getvalue()


def make_handler(path: str, data_dir: Path | None = None):
    """Create a StargazerAPIHandler instance with all HTTP mechanics mocked."""
    handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
    handler.path = path
    handler.client_address = ("127.0.0.1", 9999)
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}

    wfile = MockWFile()
    handler.wfile = wfile
    handler._headers: dict[str, str] = {}
    handler._status_code: int | None = None

    handler.send_response = lambda code: setattr(handler, "_status_code", code)
    handler.send_header = lambda k, v: handler._headers.__setitem__(k, v)
    handler.end_headers = lambda: None
    handler.send_error = lambda code, msg="": (
        setattr(handler, "_status_code", code),
        wfile.write(f"Error {code}: {msg}".encode()),
    )

    if data_dir is not None:
        patch("projects.stargazer.backend.api.DATA_DIR", data_dir).start()

    return handler, wfile


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_returns_200(self):
        handler, _ = make_handler("/health")
        handler.send_health_check()
        assert handler._status_code == 200

    def test_content_type_json(self):
        handler, _ = make_handler("/health")
        handler.send_health_check()
        assert handler._headers.get("Content-Type") == "application/json"

    def test_cors_header_set(self):
        handler, _ = make_handler("/health")
        handler.send_health_check()
        assert handler._headers.get("Access-Control-Allow-Origin") == "*"

    def test_body_is_valid_json(self):
        handler, wfile = make_handler("/health")
        handler.send_health_check()
        data = json.loads(wfile.getvalue())
        assert isinstance(data, dict)

    def test_status_field_is_healthy(self):
        handler, wfile = make_handler("/health")
        handler.send_health_check()
        data = json.loads(wfile.getvalue())
        assert data["status"] == "healthy"

    def test_timestamp_field_present(self):
        handler, wfile = make_handler("/health")
        handler.send_health_check()
        data = json.loads(wfile.getvalue())
        assert "timestamp" in data

    def test_timestamp_is_iso_format(self):
        handler, wfile = make_handler("/health")
        handler.send_health_check()
        data = json.loads(wfile.getvalue())
        # Should parse without error
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# /api/locations
# ---------------------------------------------------------------------------


class TestLocationsEndpoint:
    def test_returns_200_when_file_exists(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "forecasts_scored.json").write_text(json.dumps([{"id": "x"}]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/locations")
            handler.send_locations()

        assert handler._status_code == 200

    def test_returns_exact_file_contents(self, tmp_path: Path):
        payload = [{"id": "loc1", "score": 85}]
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "forecasts_scored.json").write_text(json.dumps(payload))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/locations")
            handler.send_locations()

        assert json.loads(wfile.getvalue()) == payload

    def test_calls_send_empty_when_file_missing(self, tmp_path: Path):
        (tmp_path / "output").mkdir()
        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/locations")
            handler.send_empty_response = MagicMock()
            handler.send_locations()

        handler.send_empty_response.assert_called_once()

    def test_content_type_json(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "forecasts_scored.json").write_text("[]")

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/locations")
            handler.send_locations()

        assert handler._headers.get("Content-Type") == "application/json"

    def test_cors_header(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "forecasts_scored.json").write_text("[]")

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/locations")
            handler.send_locations()

        assert handler._headers.get("Access-Control-Allow-Origin") == "*"

    def test_returns_500_on_invalid_json(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "forecasts_scored.json").write_bytes(b"\xff\xfe not json")

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/locations")
            handler.send_locations()

        assert handler._status_code == 500


# ---------------------------------------------------------------------------
# /api/best
# ---------------------------------------------------------------------------


class TestBestLocationsEndpoint:
    def _best_location(self) -> dict:
        return {
            "id": "loc1",
            "coordinates": {"lat": 55.0, "lon": -4.5},
            "altitude_m": 320,
            "lp_zone": "1a",
            "best_hours": [
                {
                    "time": "2024-01-15T22:00:00Z",
                    "score": 92.5,
                    "cloud_area_fraction": 5.0,
                    "relative_humidity": 55.0,
                    "wind_speed": 2.5,
                    "air_temperature": 8.0,
                    "dew_spread": 5.0,
                    "air_pressure": 1022.0,
                }
            ],
            "best_score": 92.5,
        }

    def test_returns_200_when_file_exists(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "best_locations.json").write_text(
            json.dumps([self._best_location()])
        )

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200

    def test_response_has_required_fields(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "best_locations.json").write_text(
            json.dumps([self._best_location()])
        )

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        loc = resp[0]
        for field in (
            "id",
            "name",
            "lat",
            "lon",
            "altitude_m",
            "lp_zone",
            "score",
            "cloud_cover",
            "humidity",
            "wind_speed",
            "next_clear",
            "moon_phase",
            "best_hours",
        ):
            assert field in loc, f"Missing field: {field}"

    def test_coordinates_are_flattened(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        loc = self._best_location()
        (out_dir / "best_locations.json").write_text(json.dumps([loc]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        assert resp[0]["lat"] == 55.0
        assert resp[0]["lon"] == -4.5

    def test_cache_headers_present(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        (out_dir / "best_locations.json").write_text(
            json.dumps([self._best_location()])
        )

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/best")
            handler.send_best_locations()

        assert "Last-Modified" in handler._headers
        assert "Cache-Control" in handler._headers
        assert "X-Next-Update" in handler._headers

    def test_best_hours_limited_to_five(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        loc = {
            "id": "multi",
            "coordinates": {"lat": 55.0, "lon": -4.5},
            "best_hours": [
                {"time": f"2024-01-15T{20 + i:02d}:00:00Z", "score": 90 - i}
                for i in range(10)
            ],
        }
        (out_dir / "best_locations.json").write_text(json.dumps([loc]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        assert len(resp[0]["best_hours"]) == 5

    def test_score_comes_from_first_best_hour(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        loc = {
            "id": "scored",
            "coordinates": {"lat": 55.0, "lon": -4.5},
            "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 87.3}],
        }
        (out_dir / "best_locations.json").write_text(json.dumps([loc]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        assert resp[0]["score"] == pytest.approx(87.3)

    def test_calls_send_empty_when_both_files_missing(self, tmp_path: Path):
        (tmp_path / "output").mkdir()
        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, _ = make_handler("/api/best")
            handler.send_empty_response = MagicMock()
            handler.send_best_locations()

        handler.send_empty_response.assert_called_once()

    def test_location_without_best_hours_or_hours_gets_score_zero(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        loc = {
            "id": "no_hours",
            "coordinates": {"lat": 55.0, "lon": -4.5},
        }
        (out_dir / "best_locations.json").write_text(json.dumps([loc]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        assert resp[0]["score"] == 0
        assert resp[0]["next_clear"] == "Unknown"

    def test_name_generated_when_absent(self, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        loc = {
            "lat": 55.08,
            "lon": -4.50,
            "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 85}],
        }
        (out_dir / "best_locations.json").write_text(json.dumps([loc]))

        with patch("projects.stargazer.backend.api.DATA_DIR", tmp_path):
            handler, wfile = make_handler("/api/best")
            handler.send_best_locations()

        resp = json.loads(wfile.getvalue())
        # Name should be auto-generated with lat/lon
        assert resp[0]["name"] != ""


# ---------------------------------------------------------------------------
# Empty response / demo data
# ---------------------------------------------------------------------------


class TestSendEmptyResponse:
    def test_returns_200(self):
        handler, _ = make_handler("/api/best")
        handler.send_empty_response()
        assert handler._status_code == 200

    def test_response_is_list(self):
        handler, wfile = make_handler("/api/best")
        handler.send_empty_response()
        data = json.loads(wfile.getvalue())
        assert isinstance(data, list)

    def test_demo_data_has_galloway(self):
        handler, wfile = make_handler("/api/best")
        handler.send_empty_response()
        data = json.loads(wfile.getvalue())
        assert any("Galloway" in item["name"] for item in data)

    def test_demo_data_structure(self):
        handler, wfile = make_handler("/api/best")
        handler.send_empty_response()
        item = json.loads(wfile.getvalue())[0]
        for field in (
            "id",
            "name",
            "lat",
            "lon",
            "altitude_m",
            "lp_zone",
            "score",
            "cloud_cover",
            "humidity",
            "wind_speed",
        ):
            assert field in item


# ---------------------------------------------------------------------------
# Index / 404
# ---------------------------------------------------------------------------


class TestIndexEndpoint:
    def test_returns_200(self):
        handler, _ = make_handler("/")
        handler.send_index()
        assert handler._status_code == 200

    def test_content_type_html(self):
        handler, _ = make_handler("/")
        handler.send_index()
        assert "text/html" in handler._headers.get("Content-Type", "")

    def test_html_has_api_links(self):
        handler, wfile = make_handler("/")
        handler.send_index()
        html = wfile.getvalue().decode()
        assert "/api/best" in html
        assert "/api/locations" in html
        assert "/health" in html


class TestNotFoundEndpoint:
    def test_unknown_path_404(self):
        handler, _ = make_handler("/unknown")
        handler.send_404()
        assert handler._status_code == 404


# ---------------------------------------------------------------------------
# Routing via do_GET
# ---------------------------------------------------------------------------


class TestDoGetRouting:
    def _make(self, path: str):
        handler, wfile = make_handler(path)
        return handler, wfile

    def test_health_route(self):
        handler, _ = self._make("/health")
        handler.send_health_check = MagicMock()
        handler.do_GET()
        handler.send_health_check.assert_called_once()

    def test_locations_route(self):
        handler, _ = self._make("/api/locations")
        handler.send_locations = MagicMock()
        handler.do_GET()
        handler.send_locations.assert_called_once()

    def test_best_route(self):
        handler, _ = self._make("/api/best")
        handler.send_best_locations = MagicMock()
        handler.do_GET()
        handler.send_best_locations.assert_called_once()

    def test_index_route(self):
        handler, _ = self._make("/")
        handler.send_index = MagicMock()
        handler.do_GET()
        handler.send_index.assert_called_once()

    def test_unknown_route(self):
        handler, _ = self._make("/no-such-page")
        handler.send_404 = MagicMock()
        handler.do_GET()
        handler.send_404.assert_called_once()

    def test_log_message_override(self):
        """log_message should not raise (uses logger instead of stderr)."""
        handler, _ = self._make("/health")
        handler.log_message("%s %s", "test", "args")  # should not raise
