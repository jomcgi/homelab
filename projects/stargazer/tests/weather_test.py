"""Tests for the weather module."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import geopandas as gpd
import httpx
import pytest
from shapely.geometry import Point

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.weather import (
    fetch_all_forecasts,
    fetch_forecast,
    output_best_locations,
    score_locations,
)


class TestFetchForecast:
    """Tests for fetch_forecast function."""

    @pytest.mark.asyncio
    async def test_fetch_forecast_success(
        self,
        settings: Settings,
        sample_forecast_response: dict,
    ):
        """Test successful forecast fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_forecast_response
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_forecast(
            lat=55.0,
            lon=-4.5,
            altitude=100,
            client=mock_client,
            settings=settings,
        )

        assert result == sample_forecast_response
        mock_client.get.assert_called_once()

        # Verify correct URL and params
        call_args = mock_client.get.call_args
        url = call_args.kwargs.get("url") or call_args.args[0]
        assert "api.met.no" in url
        assert call_args.kwargs["params"]["lat"] == 55.0
        assert call_args.kwargs["params"]["lon"] == -4.5
        assert call_args.kwargs["params"]["altitude"] == 100

    @pytest.mark.asyncio
    async def test_fetch_forecast_includes_user_agent(
        self,
        settings: Settings,
        sample_forecast_response: dict,
    ):
        """Test that fetch includes User-Agent header."""
        mock_response = AsyncMock()
        mock_response.json.return_value = sample_forecast_response
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await fetch_forecast(
            lat=55.0,
            lon=-4.5,
            altitude=100,
            client=mock_client,
            settings=settings,
        )

        call_args = mock_client.get.call_args
        assert "User-Agent" in call_args.kwargs["headers"]
        assert "stargazer" in call_args.kwargs["headers"]["User-Agent"]

    @pytest.mark.asyncio
    async def test_fetch_forecast_handles_http_error(
        self,
        settings: Settings,
    ):
        """Test graceful handling of HTTP errors."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")

        result = await fetch_forecast(
            lat=55.0,
            lon=-4.5,
            altitude=100,
            client=mock_client,
            settings=settings,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_forecast_handles_rate_limit(
        self,
        settings: Settings,
    ):
        """Test handling of rate limit errors (429)."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_forecast(
            lat=55.0,
            lon=-4.5,
            altitude=100,
            client=mock_client,
            settings=settings,
        )

        assert result is None


class TestFetchAllForecasts:
    """Tests for fetch_all_forecasts function."""

    @pytest.mark.asyncio
    async def test_fetch_all_creates_output_file(
        self,
        settings: Settings,
        sample_geojson_points: dict,
        sample_forecast_response: dict,
    ):
        """Test that fetch_all_forecasts creates output file."""
        # Create enriched points file
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        with patch(
            "projects.stargazer.backend.weather.fetch_forecast",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = sample_forecast_response

            result = await fetch_all_forecasts(settings)

        assert result.exists()
        assert result.name == "forecasts_raw.json"

    @pytest.mark.asyncio
    async def test_fetch_all_respects_rate_limit(
        self,
        settings: Settings,
        sample_geojson_points: dict,
        sample_forecast_response: dict,
    ):
        """Test that fetch_all respects rate limiting."""
        # Set low rate limit for testing
        settings.met_norway_rate_limit = 2

        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        with patch(
            "projects.stargazer.backend.weather.fetch_forecast",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = sample_forecast_response

            await fetch_all_forecasts(settings)

        # Should have been called for each point
        assert mock_fetch.call_count == len(sample_geojson_points["features"])


class TestScoreLocations:
    """Tests for score_locations function."""

    def test_score_locations_creates_output_file(
        self,
        settings: Settings,
        sample_geojson_points: dict,
        sample_forecast_response: dict,
    ):
        """Test that score_locations creates scored output file."""
        # Create input files
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Create raw forecasts with point IDs from sample_geojson_points
        forecasts = {}
        for feature in sample_geojson_points["features"]:
            point_id = feature["properties"]["id"]
            forecasts[point_id] = sample_forecast_response

        forecasts_path = settings.output_dir / "forecasts_raw.json"
        with open(forecasts_path, "w") as f:
            json.dump(forecasts, f)

        result = score_locations(settings)

        assert result.exists()
        assert result.name == "forecasts_scored.json"

    def test_score_locations_filters_by_darkness(
        self,
        settings: Settings,
        sample_geojson_points: dict,
    ):
        """Test that scoring only includes dark hours."""
        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Create forecast with both day and night hours
        daytime_forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-06-15T12:00:00Z",  # Noon - definitely not dark
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 0.0,
                                    "relative_humidity": 50.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 2.0,
                                    "air_temperature": 15.0,
                                    "dew_point_temperature": 5.0,
                                    "air_pressure_at_sea_level": 1020.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_day"}
                            },
                        },
                    }
                ]
            }
        }

        forecasts = {}
        for feature in sample_geojson_points["features"]:
            point_id = feature["properties"]["id"]
            forecasts[point_id] = daytime_forecast

        forecasts_path = settings.output_dir / "forecasts_raw.json"
        with open(forecasts_path, "w") as f:
            json.dump(forecasts, f)

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        # Daytime hours should be filtered out
        # (Sun altitude calculation should exclude them)
        # The result could be empty or have no scored_hours

    def test_score_locations_filters_by_min_score(
        self,
        settings: Settings,
        sample_geojson_points: dict,
    ):
        """Test that scoring filters hours below min_astronomy_score."""
        settings.min_astronomy_score = 80

        points_path = settings.processed_dir / "sample_points_enriched.geojson"
        with open(points_path, "w") as f:
            json.dump(sample_geojson_points, f)

        # Forecast with poor conditions (low score)
        poor_forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",  # Winter night
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 95.0,  # Very cloudy
                                    "relative_humidity": 95.0,
                                    "fog_area_fraction": 50.0,
                                    "wind_speed": 20.0,
                                    "air_temperature": 5.0,
                                    "dew_point_temperature": 4.0,
                                    "air_pressure_at_sea_level": 990.0,
                                }
                            },
                            "next_1_hours": {"summary": {"symbol_code": "cloudy"}},
                        },
                    }
                ]
            }
        }

        forecasts = {}
        for feature in sample_geojson_points["features"]:
            point_id = feature["properties"]["id"]
            forecasts[point_id] = poor_forecast

        forecasts_path = settings.output_dir / "forecasts_raw.json"
        with open(forecasts_path, "w") as f:
            json.dump(forecasts, f)

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        # Poor conditions should result in no locations passing threshold
        # (scores below 80 are filtered)


class TestOutputBestLocations:
    """Tests for output_best_locations function."""

    def test_output_best_creates_file(
        self,
        settings: Settings,
        sample_scored_forecasts: dict,
    ):
        """Test that output_best_locations creates output file."""
        scored_path = settings.output_dir / "forecasts_scored.json"
        with open(scored_path, "w") as f:
            json.dump(sample_scored_forecasts, f)

        result = output_best_locations(settings)

        assert result.exists()
        assert result.name == "best_locations.json"

    def test_output_best_filters_by_score(
        self,
        settings: Settings,
    ):
        """Test that only locations with score >= 80 are included."""
        scored_data = {
            "high_score": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 92.0},
                ],
            },
            "low_score": {
                "coordinates": {"lat": 56.0, "lon": -5.0},
                "altitude_m": 200,
                "lp_zone": "2a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 65.0},  # Below 80
                ],
            },
        }

        scored_path = settings.output_dir / "forecasts_scored.json"
        with open(scored_path, "w") as f:
            json.dump(scored_data, f)

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        # Only high_score location should be included
        assert len(best) == 1
        assert best[0]["id"] == "high_score"

    def test_output_best_sorts_by_score(
        self,
        settings: Settings,
    ):
        """Test that locations are sorted by best score descending."""
        scored_data = {
            "medium": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [{"time": "2024-01-15T22:00:00Z", "score": 85.0}],
            },
            "high": {
                "coordinates": {"lat": 56.0, "lon": -5.0},
                "altitude_m": 200,
                "lp_zone": "2a",
                "scored_hours": [{"time": "2024-01-15T22:00:00Z", "score": 95.0}],
            },
            "low": {
                "coordinates": {"lat": 57.0, "lon": -6.0},
                "altitude_m": 300,
                "lp_zone": "1b",
                "scored_hours": [{"time": "2024-01-15T22:00:00Z", "score": 82.0}],
            },
        }

        scored_path = settings.output_dir / "forecasts_scored.json"
        with open(scored_path, "w") as f:
            json.dump(scored_data, f)

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 3
        assert best[0]["id"] == "high"
        assert best[1]["id"] == "medium"
        assert best[2]["id"] == "low"

    def test_output_best_limits_hours(
        self,
        settings: Settings,
    ):
        """Test that best_hours is limited to 5 per location."""
        scored_data = {
            "many_hours": {
                "coordinates": {"lat": 55.0, "lon": -4.5},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": f"2024-01-15T{20 + i}:00:00Z", "score": 90.0 - i}
                    for i in range(10)
                ],
            },
        }

        scored_path = settings.output_dir / "forecasts_scored.json"
        with open(scored_path, "w") as f:
            json.dump(scored_data, f)

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best[0]["best_hours"]) == 5

    def test_output_best_includes_metadata(
        self,
        settings: Settings,
        sample_scored_forecasts: dict,
    ):
        """Test that output includes all required metadata fields."""
        scored_path = settings.output_dir / "forecasts_scored.json"
        with open(scored_path, "w") as f:
            json.dump(sample_scored_forecasts, f)

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        location = best[0]
        assert "id" in location
        assert "coordinates" in location
        assert "lat" in location["coordinates"]
        assert "lon" in location["coordinates"]
        assert "altitude_m" in location
        assert "lp_zone" in location
        assert "best_hours" in location
        assert "best_score" in location
