"""New coverage tests for remaining gaps in stargazer backend.

Covers:
  api.py   — send_best_locations elif "hours" branch (line 98-100)
  weather.py — output_best_locations best_hours[:5] truncation with >=6 qualifying hours
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from projects.stargazer.backend.config import Settings


# ---------------------------------------------------------------------------
# Shared helper — replicates the pattern from api_test.py / gap_coverage_test.py
# ---------------------------------------------------------------------------


class MockWFile:
    def __init__(self):
        self.data = BytesIO()

    def write(self, data: bytes):
        self.data.write(data)

    def getvalue(self) -> bytes:
        return self.data.getvalue()


def create_api_handler(path: str):
    from projects.stargazer.backend.api import StargazerAPIHandler

    handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
    handler.path = path
    handler.client_address = ("127.0.0.1", 9999)
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}

    wfile = MockWFile()
    handler.wfile = wfile
    handler._headers = {}
    handler._status_code = None

    handler.send_response = lambda code: setattr(handler, "_status_code", code)
    handler.send_header = lambda k, v: handler._headers.__setitem__(k, v)
    handler.end_headers = lambda: None
    handler.send_error = lambda code, msg="": (
        setattr(handler, "_status_code", code),
        wfile.write(f"Error {code}: {msg}".encode()),
    )

    return handler, wfile


# ===========================================================================
# api.py — send_best_locations elif "hours" branch
# ===========================================================================


class TestSendBestLocationsHoursFallback:
    """Tests for the elif 'hours' in location branch in send_best_locations."""

    def test_hours_key_selects_best_scoring_hour(self, temp_data_dir: Path):
        """When best_locations.json contains a location with 'hours' (not 'best_hours'),
        the elif branch selects the max-score hour as best_hour."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        location = {
            "id": "hours_loc",
            "lat": 55.0,
            "lon": -4.5,
            "altitude_m": 200,
            "lp_zone": "1a",
            # uses 'hours' not 'best_hours'
            "hours": [
                {"time": "2024-01-15T21:00:00Z", "score": 70.0},
                {"time": "2024-01-15T22:00:00Z", "score": 92.0},
                {"time": "2024-01-15T23:00:00Z", "score": 85.0},
            ],
        }
        (output_dir / "best_locations.json").write_text(json.dumps([location]))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        assert len(response) == 1
        # max(hours, key=score) → the 92.0 entry is chosen
        assert response[0]["score"] == pytest.approx(92.0)
        assert response[0]["id"] == "hours_loc"

    def test_hours_empty_list_gives_score_zero(self, temp_data_dir: Path):
        """When 'hours' key exists but list is empty, the elif condition is falsy
        → best_hour stays None → score=0, next_clear='Unknown'."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        location = {
            "id": "empty_hours_loc",
            "lat": 56.0,
            "lon": -5.0,
            "altitude_m": 150,
            "lp_zone": "2a",
            "hours": [],  # falsy → elif branch NOT taken
        }
        (output_dir / "best_locations.json").write_text(json.dumps([location]))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        assert len(response) == 1
        assert response[0]["score"] == 0
        assert response[0]["next_clear"] == "Unknown"

    def test_hours_with_score_key_missing_defaults_to_zero(self, temp_data_dir: Path):
        """When 'hours' entries lack a 'score' key, h.get('score', 0) returns 0
        for all entries, but max() still picks one deterministically."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        location = {
            "id": "noscore_loc",
            "lat": 55.5,
            "lon": -4.0,
            "altitude_m": 100,
            "lp_zone": "1b",
            "hours": [
                {"time": "2024-01-15T22:00:00Z"},  # no score key
                {"time": "2024-01-15T23:00:00Z"},  # no score key
            ],
        }
        (output_dir / "best_locations.json").write_text(json.dumps([location]))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        # Should not raise; score defaults to 0
        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        assert response[0]["score"] == 0


# ===========================================================================
# weather.py — output_best_locations best_hours[:5] truncation
# ===========================================================================


class TestOutputBestLocationsTruncation:
    """Tests for best_hours[:5] truncation when >=6 qualifying hours exist."""

    def test_six_qualifying_hours_truncated_to_five(self, settings: Settings):
        """A location with 6 scored_hours all >= 80 should yield best_hours of
        exactly 5 entries ([:5] applied)."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "many_hours_loc": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": f"2024-01-15T{20 + i:02d}:00:00Z", "score": 95.0 - i}
                    for i in range(6)  # scores: 95, 94, 93, 92, 91, 90 — all >= 80
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 1
        # 6 qualifying hours → truncated to 5
        assert len(best[0]["best_hours"]) == 5
        # All returned hours should have score >= 80
        for h in best[0]["best_hours"]:
            assert h["score"] >= 80.0
        # best_score is the highest qualifying hour (index 0)
        assert best[0]["best_score"] == pytest.approx(95.0)

    def test_five_qualifying_hours_not_truncated(self, settings: Settings):
        """Exactly 5 qualifying hours → best_hours has all 5 (no truncation)."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "five_hours_loc": {
                "coordinates": {"lat": 56.0, "lon": -5.0},
                "altitude_m": 200,
                "lp_zone": "2a",
                "scored_hours": [
                    {"time": f"2024-01-15T{20 + i:02d}:00:00Z", "score": 88.0 - i}
                    for i in range(5)  # exactly 5 qualifying hours
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 1
        assert len(best[0]["best_hours"]) == 5

    def test_seven_qualifying_hours_truncated_to_five(self, settings: Settings):
        """7 qualifying hours → still truncated to 5."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "seven_hours_loc": {
                "coordinates": {"lat": 57.0, "lon": -5.5},
                "altitude_m": 300,
                "lp_zone": "3a",
                "scored_hours": [
                    {"time": f"2024-01-15T{18 + i:02d}:00:00Z", "score": 90.0 - i * 0.5}
                    for i in range(7)  # 7 hours, all >= 80
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 1
        assert len(best[0]["best_hours"]) == 5
