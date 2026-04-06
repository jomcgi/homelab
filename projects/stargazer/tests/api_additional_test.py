"""Additional tests for api module: error handling and edge cases."""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from projects.stargazer.backend.api import StargazerAPIHandler


class MockWFile:
    """Mock wfile for capturing response data."""

    def __init__(self):
        self.data = BytesIO()

    def write(self, data: bytes):
        self.data.write(data)

    def getvalue(self) -> bytes:
        return self.data.getvalue()


def create_handler(
    path: str,
) -> tuple[StargazerAPIHandler, MockWFile]:
    """Create a handler with mocked request/response objects."""
    handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
    handler.path = path
    handler.client_address = ("127.0.0.1", 12345)
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}

    wfile = MockWFile()
    handler.wfile = wfile
    handler._headers = {}
    handler._status_code = None

    def send_response(code):
        handler._status_code = code

    def send_header(key, value):
        handler._headers[key] = value

    def end_headers():
        pass

    def send_error(code, message=""):
        handler._status_code = code
        wfile.write(f"Error {code}: {message}".encode())

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    handler.send_error = send_error

    return handler, wfile


class TestLocationsErrorHandling:
    """Tests for error handling paths in send_locations."""

    def test_send_locations_returns_500_on_invalid_json(self, temp_data_dir: Path):
        """send_locations returns 500 when scored file contains invalid JSON."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "forecasts_scored.json").write_text("{ this is not valid json }")

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/locations")
            handler.send_locations()

        assert handler._status_code == 500

    def test_send_locations_includes_cors_header_when_data_exists(
        self, temp_data_dir: Path
    ):
        """send_locations includes CORS header when data file exists."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "forecasts_scored.json").write_text(json.dumps([]))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/locations")
            handler.send_locations()

        assert handler._status_code == 200
        assert handler._headers.get("Access-Control-Allow-Origin") == "*"


class TestBestLocationsEdgeCases:
    """Tests for edge cases in send_best_locations data transformation."""

    def test_location_with_no_hours_gets_zero_score(self, temp_data_dir: Path):
        """Location with no best_hours and no hours produces score=0 and next_clear=Unknown."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_data = [
            {
                "id": "empty-hours",
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 200,
                "lp_zone": "1a",
                # Neither best_hours nor hours key present
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        loc = response[0]
        assert loc["score"] == 0
        assert loc["next_clear"] == "Unknown"
        assert loc["cloud_cover"] == 100
        assert loc["humidity"] == 100
        assert loc["wind_speed"] == 0

    def test_location_with_empty_best_hours_gets_zero_score(self, temp_data_dir: Path):
        """Location with empty best_hours list produces score=0."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_data = [
            {
                "id": "empty-best",
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 150,
                "lp_zone": "2a",
                "best_hours": [],  # Empty list — best_hour remains None
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        assert response[0]["score"] == 0
        assert response[0]["next_clear"] == "Unknown"

    def test_location_uses_lat_lon_when_no_coordinates_dict(self, temp_data_dir: Path):
        """Location with top-level lat/lon (not nested coordinates) uses those values."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_data = [
            {
                "id": "flat-coords",
                "lat": 57.5,
                "lon": -3.8,
                "altitude_m": 300,
                "lp_zone": "1b",
                "best_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 88.0}
                ],
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        loc = response[0]
        assert loc["lat"] == 57.5
        assert loc["lon"] == -3.8

    def test_generates_name_when_missing(self, temp_data_dir: Path):
        """Location without name field gets auto-generated name from lat/lon."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_data = [
            {
                "id": "no-name",
                "lat": 56.123,
                "lon": -4.456,
                "altitude_m": 250,
                "lp_zone": "1a",
                "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 82.0}],
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_best_locations()

        response = json.loads(wfile.getvalue().decode())
        # Name is auto-generated as "Location {lat:.2f}, {lon:.2f}"
        assert "56.12" in response[0]["name"]
        assert "-4.46" in response[0]["name"]

    def test_passes_through_lp_zone_and_altitude(self, temp_data_dir: Path):
        """Transformed data preserves lp_zone and altitude_m from source."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_data = [
            {
                "id": "meta-check",
                "coordinates": {"lat": 55.5, "lon": -4.0},
                "altitude_m": 450,
                "lp_zone": "2b",
                "best_hours": [
                    {
                        "time": "2024-01-15T22:00:00Z",
                        "score": 91.0,
                        "cloud_area_fraction": 3.0,
                        "relative_humidity": 52.0,
                        "wind_speed": 1.5,
                    }
                ],
            }
        ]
        (output_dir / "best_locations.json").write_text(json.dumps(test_data))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_best_locations()

        response = json.loads(wfile.getvalue().decode())
        loc = response[0]
        assert loc["altitude_m"] == 450
        assert loc["lp_zone"] == "2b"
        assert loc["score"] == 91.0
        assert loc["cloud_cover"] == 3.0
        assert loc["humidity"] == 52.0
        assert loc["wind_speed"] == 1.5


class TestDemoDataStructure:
    """Tests for demo data returned when no files exist."""

    def test_demo_data_has_correct_structure(self, temp_data_dir: Path):
        """Demo data includes all required frontend fields."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_empty_response()

        response = json.loads(wfile.getvalue().decode())
        assert len(response) == 1
        demo = response[0]

        required_fields = [
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
        ]
        for field in required_fields:
            assert field in demo, f"Demo data missing field: {field}"

    def test_demo_data_has_galloway_location(self, temp_data_dir: Path):
        """Demo data uses Galloway Forest as the demo location."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_handler("/api/best")
            handler.send_empty_response()

        response = json.loads(wfile.getvalue().decode())
        demo = response[0]
        assert demo["id"] == "demo-galloway"
        assert demo["lat"] == pytest.approx(55.0833, abs=0.001)
        assert demo["lon"] == pytest.approx(-4.5, abs=0.001)
        assert demo["score"] == 0
        assert demo["best_hours"] == []


class TestHealthTimestamp:
    """Tests for health endpoint timestamp format."""

    def test_health_timestamp_is_iso_format(self):
        """Health check timestamp is in ISO 8601 format."""
        from datetime import datetime

        handler, wfile = create_handler("/health")
        handler.send_health_check()

        response = json.loads(wfile.getvalue().decode())
        # Should parse without error as ISO format
        ts = datetime.fromisoformat(response["timestamp"].replace("Z", "+00:00"))
        assert ts is not None

    def test_health_timestamp_is_utc(self):
        """Health check timestamp is in UTC timezone."""
        handler, wfile = create_handler("/health")
        handler.send_health_check()

        response = json.loads(wfile.getvalue().decode())
        # ISO format with timezone info
        assert "+" in response["timestamp"] or response["timestamp"].endswith("Z") or "UTC" in response["timestamp"]
