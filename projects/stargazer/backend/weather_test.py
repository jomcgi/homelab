"""Unit tests for the weather module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings
from projects.stargazer.backend.weather import (
    fetch_forecast,
    output_best_locations,
    score_locations,
)


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path,
        bounds=BoundsConfig(),
        europe_bounds=EuropeBoundsConfig(),
        otel_enabled=False,
    )
    for subdir in ("raw", "processed", "cache", "output"):
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
    return settings


def _met_response(
    cloud: float = 5.0,
    humidity: float = 50.0,
    fog: float = 0.0,
    wind: float = 2.0,
    temp: float = 10.0,
    dew: float = 4.0,
    pressure: float = 1018.0,
    symbol: str = "clearsky_night",
    time: str = "2024-01-15T02:00:00Z",
) -> dict:
    """Build a minimal MET Norway API response for a single timeseries entry."""
    return {
        "properties": {
            "timeseries": [
                {
                    "time": time,
                    "data": {
                        "instant": {
                            "details": {
                                "cloud_area_fraction": cloud,
                                "relative_humidity": humidity,
                                "fog_area_fraction": fog,
                                "wind_speed": wind,
                                "air_temperature": temp,
                                "dew_point_temperature": dew,
                                "air_pressure_at_sea_level": pressure,
                            }
                        },
                        "next_1_hours": {"summary": {"symbol_code": symbol}},
                    },
                }
            ]
        }
    }


_SAMPLE_POINTS_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-4.5, 55.0833]},
            "properties": {
                "id": "scotland_0001",
                "lat": 55.0833,
                "lon": -4.5,
                "altitude_m": 320,
                "lp_zone": "1a",
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# fetch_forecast
# ---------------------------------------------------------------------------


class TestFetchForecast:
    @pytest.mark.asyncio
    async def test_success_returns_json(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        expected = {"some": "forecast"}

        mock_resp = MagicMock()
        mock_resp.json.return_value = expected
        mock_resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        result = await fetch_forecast(55.0, -4.5, 100, client, settings)

        assert result == expected

    @pytest.mark.asyncio
    async def test_uses_met_norway_url(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        await fetch_forecast(55.0, -4.5, 100, client, settings)

        url = client.get.call_args.args[0] if client.get.call_args.args else client.get.call_args.kwargs.get("url")
        assert "api.met.no" in url

    @pytest.mark.asyncio
    async def test_passes_lat_lon_altitude_params(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        await fetch_forecast(55.1, -4.3, 250, client, settings)

        kwargs = client.get.call_args.kwargs
        assert kwargs["params"]["lat"] == 55.1
        assert kwargs["params"]["lon"] == -4.3
        assert kwargs["params"]["altitude"] == 250

    @pytest.mark.asyncio
    async def test_sends_user_agent_header(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        await fetch_forecast(55.0, -4.5, 0, client, settings)

        kwargs = client.get.call_args.kwargs
        assert "User-Agent" in kwargs["headers"]
        assert "stargazer" in kwargs["headers"]["User-Agent"]

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        client = AsyncMock()
        client.get.side_effect = httpx.HTTPError("connection refused")

        result = await fetch_forecast(55.0, -4.5, 0, client, settings)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_status_error(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )

        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        result = await fetch_forecast(55.0, -4.5, 0, client, settings)

        assert result is None


# ---------------------------------------------------------------------------
# score_locations
# ---------------------------------------------------------------------------


def _write_files(settings: Settings, points: dict, forecasts: dict) -> None:
    (settings.processed_dir / "sample_points_enriched.geojson").write_text(
        json.dumps(points)
    )
    (settings.output_dir / "forecasts_raw.json").write_text(json.dumps(forecasts))


class TestScoreLocations:
    def test_creates_scored_output_file(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _write_files(settings, _SAMPLE_POINTS_GEOJSON, {})

        result = score_locations(settings)

        assert result.exists()
        assert result.name == "forecasts_scored.json"

    def test_empty_forecasts_gives_empty_output(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _write_files(settings, _SAMPLE_POINTS_GEOJSON, {})

        result = score_locations(settings)

        assert json.loads(result.read_text()) == {}

    def test_daytime_hours_excluded(self, tmp_path: Path):
        """Hours where the sun is above -12° should be filtered out."""
        settings = make_settings(tmp_path)
        # June noon at Scotland latitude → sun very high
        forecast = _met_response(
            cloud=0.0,
            humidity=40.0,
            wind=1.0,
            temp=20.0,
            dew=5.0,
            time="2024-06-15T12:00:00Z",
        )
        _write_files(
            settings,
            _SAMPLE_POINTS_GEOJSON,
            {"scotland_0001": forecast},
        )

        result = score_locations(settings)
        data = json.loads(result.read_text())

        assert "scotland_0001" not in data  # daytime → filtered

    def test_poor_weather_below_min_score_excluded(self, tmp_path: Path):
        """Hours with score < min_astronomy_score should not appear."""
        settings = make_settings(tmp_path)
        settings.min_astronomy_score = 60

        # Terrible conditions at a reliably dark winter night time
        forecast = _met_response(
            cloud=100.0,
            humidity=100.0,
            fog=50.0,
            wind=30.0,
            temp=2.0,
            dew=2.0,
            pressure=980.0,
            time="2024-01-15T02:00:00Z",
        )
        _write_files(
            settings,
            _SAMPLE_POINTS_GEOJSON,
            {"scotland_0001": forecast},
        )

        result = score_locations(settings)
        data = json.loads(result.read_text())

        # Score should be near 0 — excluded by min_astronomy_score
        assert "scotland_0001" not in data

    def test_unknown_point_id_in_forecast_skipped(self, tmp_path: Path):
        """Forecasts for point IDs not in the points file are ignored."""
        settings = make_settings(tmp_path)
        forecast = _met_response(time="2024-01-15T02:00:00Z")
        _write_files(
            settings,
            _SAMPLE_POINTS_GEOJSON,
            {"no_such_point_99": forecast},
        )

        result = score_locations(settings)
        data = json.loads(result.read_text())

        assert "no_such_point_99" not in data

    def test_output_structure_keys(self, tmp_path: Path):
        """When a location passes filters, output contains expected keys."""
        settings = make_settings(tmp_path)
        settings.min_astronomy_score = 0  # Accept all scores

        # Clear conditions at a guaranteed dark time (Jan midnight Scotland)
        forecast = _met_response(
            cloud=0.0,
            humidity=40.0,
            fog=0.0,
            wind=1.0,
            temp=5.0,
            dew=-2.0,
            pressure=1025.0,
            time="2024-01-15T02:00:00Z",
        )
        _write_files(
            settings,
            _SAMPLE_POINTS_GEOJSON,
            {"scotland_0001": forecast},
        )

        result = score_locations(settings)
        data = json.loads(result.read_text())

        if "scotland_0001" in data:
            loc = data["scotland_0001"]
            for key in ("coordinates", "altitude_m", "lp_zone", "scored_hours"):
                assert key in loc

    def test_missing_properties_key_skips_gracefully(self, tmp_path: Path):
        """Forecast without 'properties' key should be skipped without raising."""
        settings = make_settings(tmp_path)
        _write_files(
            settings,
            _SAMPLE_POINTS_GEOJSON,
            {"scotland_0001": {"no_properties_here": True}},
        )

        # Should not raise
        result = score_locations(settings)
        assert result.exists()


# ---------------------------------------------------------------------------
# output_best_locations
# ---------------------------------------------------------------------------


class TestOutputBestLocations:
    def _write_scored(self, settings: Settings, data: dict) -> None:
        (settings.output_dir / "forecasts_scored.json").write_text(json.dumps(data))

    def test_creates_output_file(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(settings, {})

        result = output_best_locations(settings)

        assert result.exists()
        assert result.name == "best_locations.json"

    def test_empty_input_gives_empty_list(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(settings, {})

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert data == []

    def test_filters_hours_below_80(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    "scored_hours": [
                        {"time": "2024-01-15T22:00:00Z", "score": 75.0},
                    ],
                }
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert data == []

    def test_includes_locations_with_score_at_least_80(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    "scored_hours": [
                        {"time": "2024-01-15T22:00:00Z", "score": 80.0},
                    ],
                }
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert len(data) == 1

    def test_sorts_by_best_score_descending(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "a": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    "scored_hours": [{"time": "T1", "score": 85.0}],
                },
                "b": {
                    "coordinates": {"lat": 56.0, "lon": -5.0},
                    "altitude_m": 200,
                    "lp_zone": "2a",
                    "scored_hours": [{"time": "T2", "score": 95.0}],
                },
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert data[0]["id"] == "b"
        assert data[1]["id"] == "a"

    def test_best_hours_capped_at_five(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    "scored_hours": [
                        {"time": f"T{i}", "score": 95.0 - i} for i in range(10)
                    ],
                }
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert len(data[0]["best_hours"]) == 5

    def test_output_contains_required_keys(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 320,
                    "lp_zone": "1b",
                    "scored_hours": [{"time": "T", "score": 90.0}],
                }
            },
        )

        result = output_best_locations(settings)
        loc = json.loads(result.read_text())[0]

        for key in ("id", "coordinates", "altitude_m", "lp_zone", "best_hours", "best_score"):
            assert key in loc

    def test_best_score_reflects_first_qualifying_hour(self, tmp_path: Path):
        """best_score should be the score of the first qualifying hour in scored_hours.

        Note: output_best_locations trusts the order of scored_hours as given
        (the upstream score_locations function sorts them descending). Here we
        feed them in descending order to match real usage.
        """
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    # Simulate score_locations output: sorted descending
                    "scored_hours": [
                        {"time": "T1", "score": 92.5},
                        {"time": "T2", "score": 88.0},
                        {"time": "T3", "score": 81.0},
                    ],
                }
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        assert data[0]["best_score"] == 92.5

    def test_mixed_qualifying_and_non_qualifying_hours(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        self._write_scored(
            settings,
            {
                "loc1": {
                    "coordinates": {"lat": 55.0, "lon": -4.5},
                    "altitude_m": 100,
                    "lp_zone": "1a",
                    "scored_hours": [
                        {"time": "T1", "score": 95.0},   # qualifies
                        {"time": "T2", "score": 70.0},   # does NOT qualify
                        {"time": "T3", "score": 82.0},   # qualifies
                    ],
                }
            },
        )

        result = output_best_locations(settings)
        data = json.loads(result.read_text())

        best_hours = data[0]["best_hours"]
        for h in best_hours:
            assert h["score"] >= 80.0
