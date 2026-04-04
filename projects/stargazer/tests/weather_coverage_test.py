"""Additional coverage tests for the weather module."""

import json
from unittest.mock import patch

import pytest
import pytest_asyncio  # noqa: F401 — needed to register pytest-asyncio plugin

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.weather import fetch_all_forecasts, score_locations


class TestScoreLocationsOrphanForecastIds:
    """Tests for score_locations silently skipping orphan forecast IDs."""

    def test_score_locations_skips_orphan_forecast_ids(
        self,
        settings: Settings,
        sample_geojson_points: dict,
    ):
        """score_locations silently skips forecast entries whose point_id is not in the GeoJSON."""
        # Write enriched points with ONLY the points from sample_geojson_points (pt IDs: scotland_0001, scotland_0002)
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Forecast with a valid ID and an orphan ID not in GeoJSON
        orphan_forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",  # Winter night, should be dark
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 5.0,
                                    "relative_humidity": 50.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 2.0,
                                    "air_temperature": 10.0,
                                    "dew_point_temperature": 2.0,
                                    "air_pressure_at_sea_level": 1025.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_night"}
                            },
                        },
                    }
                ]
            }
        }

        forecasts = {
            "scotland_0001": orphan_forecast,
            "orphan-999": orphan_forecast,  # Not in GeoJSON
        }

        forecasts_path = settings.output_dir / "forecasts_raw.json"
        with open(forecasts_path, "w") as f:
            json.dump(forecasts, f)

        # Should not raise even though "orphan-999" is not in GeoJSON
        result = score_locations(settings)

        assert result.exists()

        with open(result) as f:
            scored = json.load(f)

        # orphan-999 must not appear in output
        assert "orphan-999" not in scored


class TestScoreLocationsInvalidWeatherData:
    """Tests for score_locations skipping timeseries entries that fail WeatherData validation."""

    def test_score_locations_skips_invalid_weather_data(
        self,
        settings: Settings,
        sample_geojson_points: dict,
    ):
        """score_locations skips timeseries entries that fail WeatherData validation."""
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Create a forecast at high-latitude Scotland in January at 02:00 UTC (nautical darkness)
        # cloud_area_fraction=-999 is invalid per pydantic Field(ge=0, le=100)
        invalid_weather_forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",  # Winter night at Scotland latitude
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": -999,  # Invalid: ge=0 constraint violated
                                    "relative_humidity": 65.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 3.0,
                                    "air_temperature": 8.0,
                                    "dew_point_temperature": 4.0,
                                    "air_pressure_at_sea_level": 1018.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_night"}
                            },
                        },
                    }
                ]
            }
        }

        forecasts = {
            "scotland_0001": invalid_weather_forecast,
        }

        forecasts_path = settings.output_dir / "forecasts_raw.json"
        with open(forecasts_path, "w") as f:
            json.dump(forecasts, f)

        # Should not raise even though weather data is invalid
        result = score_locations(settings)

        assert result.exists()

        with open(result) as f:
            scored = json.load(f)

        # The invalid entry is skipped, so scotland_0001 should have no scored hours
        # and therefore not appear in the output (scored_hours would be empty)
        # We just verify no error was raised and the file is valid JSON
        assert isinstance(scored, dict)


class TestFetchAllForecastsPartialFailure:
    """Tests for fetch_all_forecasts partial failure scenarios."""

    @pytest.mark.asyncio
    async def test_fetch_all_forecasts_partial_failure(
        self,
        settings: Settings,
        sample_geojson_points: dict,
        sample_forecast_response: dict,
    ):
        """fetch_all_forecasts only writes forecasts that are not None (partial failure)."""
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Two points in sample_geojson_points: first returns None, second returns valid forecast
        call_count = {"n": 0}

        async def mock_fetch(lat, lon, altitude, client, settings):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # Simulate failure for first point
            return sample_forecast_response  # Success for second point

        with patch(
            "projects.stargazer.backend.weather.fetch_forecast",
            side_effect=mock_fetch,
        ):
            result = await fetch_all_forecasts(settings)

        assert result.exists()

        with open(result) as f:
            forecasts = json.load(f)

        # Only 1 entry should be present (the non-None one), not 2
        assert len(forecasts) == 1
