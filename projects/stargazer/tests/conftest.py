"""Pytest fixtures for Stargazer tests."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from shapely.geometry import Point, Polygon

from projects.stargazer.backend.config import Settings, BoundsConfig, EuropeBoundsConfig
from projects.stargazer.backend.scoring import WeatherData


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory structure."""
    for subdir in ["raw", "processed", "cache", "output"]:
        (tmp_path / subdir).mkdir()
    return tmp_path


@pytest.fixture
def settings(temp_data_dir: Path) -> Settings:
    """Create Settings with temporary data directory."""
    return Settings(
        data_dir=temp_data_dir,
        bounds=BoundsConfig(),
        europe_bounds=EuropeBoundsConfig(),
        otel_enabled=False,
    )


@pytest.fixture
def sample_weather_data() -> WeatherData:
    """Sample weather data for clear skies."""
    return WeatherData(
        cloud_area_fraction=10.0,
        relative_humidity=60.0,
        fog_area_fraction=0.0,
        wind_speed=3.0,
        air_temperature=10.0,
        dew_point_temperature=5.0,
        air_pressure_at_sea_level=1020.0,
    )


@pytest.fixture
def cloudy_weather_data() -> WeatherData:
    """Sample weather data for cloudy conditions."""
    return WeatherData(
        cloud_area_fraction=85.0,
        relative_humidity=90.0,
        fog_area_fraction=15.0,
        wind_speed=12.0,
        air_temperature=8.0,
        dew_point_temperature=7.0,
        air_pressure_at_sea_level=1005.0,
    )


@pytest.fixture
def ideal_weather_data() -> WeatherData:
    """Ideal stargazing weather conditions."""
    return WeatherData(
        cloud_area_fraction=0.0,
        relative_humidity=40.0,
        fog_area_fraction=0.0,
        wind_speed=2.0,
        air_temperature=15.0,
        dew_point_temperature=5.0,
        air_pressure_at_sea_level=1030.0,
    )


@pytest.fixture
def sample_forecast_response() -> dict:
    """Sample MET Norway API forecast response."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-4.5, 55.0, 100]},
        "properties": {
            "meta": {
                "updated_at": "2024-01-15T12:00:00Z",
                "units": {
                    "cloud_area_fraction": "%",
                    "relative_humidity": "%",
                    "wind_speed": "m/s",
                    "air_temperature": "celsius",
                },
            },
            "timeseries": [
                {
                    "time": "2024-01-15T22:00:00Z",
                    "data": {
                        "instant": {
                            "details": {
                                "cloud_area_fraction": 15.0,
                                "relative_humidity": 65.0,
                                "fog_area_fraction": 0.0,
                                "wind_speed": 4.0,
                                "air_temperature": 8.0,
                                "dew_point_temperature": 4.0,
                                "air_pressure_at_sea_level": 1018.0,
                            }
                        },
                        "next_1_hours": {"summary": {"symbol_code": "clearsky_night"}},
                    },
                },
                {
                    "time": "2024-01-15T23:00:00Z",
                    "data": {
                        "instant": {
                            "details": {
                                "cloud_area_fraction": 80.0,
                                "relative_humidity": 88.0,
                                "fog_area_fraction": 5.0,
                                "wind_speed": 8.0,
                                "air_temperature": 6.0,
                                "dew_point_temperature": 5.0,
                                "air_pressure_at_sea_level": 1010.0,
                            }
                        },
                        "next_1_hours": {"summary": {"symbol_code": "cloudy"}},
                    },
                },
            ],
        },
    }


@pytest.fixture
def sample_geojson_points() -> dict:
    """Sample GeoJSON with enriched points."""
    return {
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
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-5.0, 56.5]},
                "properties": {
                    "id": "scotland_0002",
                    "lat": 56.5,
                    "lon": -5.0,
                    "altitude_m": 150,
                    "lp_zone": "2a",
                },
            },
        ],
    }


@pytest.fixture
def sample_color_palette() -> list[dict]:
    """Sample color palette for LP zones."""
    return [
        {"rgb": [0, 0, 0], "zone": "0", "lpi_range": [0, 0.01]},
        {"rgb": [50, 50, 50], "zone": "1a", "lpi_range": [0.01, 0.06]},
        {"rgb": [75, 75, 75], "zone": "1b", "lpi_range": [0.06, 0.11]},
        {"rgb": [100, 100, 100], "zone": "2a", "lpi_range": [0.11, 0.19]},
        {"rgb": [125, 125, 125], "zone": "2b", "lpi_range": [0.19, 0.33]},
        {"rgb": [150, 150, 150], "zone": "3a", "lpi_range": [0.33, 0.58]},
        {"rgb": [175, 175, 175], "zone": "3b", "lpi_range": [0.58, 1.00]},
        {"rgb": [200, 200, 200], "zone": "4a", "lpi_range": [1.00, 1.74]},
        {"rgb": [225, 225, 225], "zone": "4b", "lpi_range": [1.74, 3.00]},
    ]


@pytest.fixture
def sample_scored_forecasts() -> dict:
    """Sample scored forecast data."""
    return {
        "scotland_0001": {
            "coordinates": {"lat": 55.0833, "lon": -4.5},
            "altitude_m": 320,
            "lp_zone": "1a",
            "scored_hours": [
                {
                    "time": "2024-01-15T22:00:00Z",
                    "score": 92.5,
                    "cloud_area_fraction": 5.0,
                    "relative_humidity": 55.0,
                    "wind_speed": 2.5,
                    "air_temperature": 8.0,
                    "dew_spread": 5.0,
                    "air_pressure": 1022.0,
                    "symbol": "clearsky_night",
                },
                {
                    "time": "2024-01-15T23:00:00Z",
                    "score": 85.0,
                    "cloud_area_fraction": 15.0,
                    "relative_humidity": 65.0,
                    "wind_speed": 4.0,
                    "air_temperature": 7.0,
                    "dew_spread": 4.0,
                    "air_pressure": 1018.0,
                    "symbol": "fair_night",
                },
            ],
        }
    }


@pytest.fixture
def sample_best_locations() -> list[dict]:
    """Sample best locations output."""
    return [
        {
            "id": "scotland_0001",
            "coordinates": {"lat": 55.0833, "lon": -4.5},
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
                    "symbol": "clearsky_night",
                }
            ],
            "best_score": 92.5,
        }
    ]


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for API tests."""
    client = AsyncMock()
    return client


@pytest.fixture
def sample_polygon() -> Polygon:
    """Sample polygon for spatial tests (area around Galloway)."""
    return Polygon(
        [
            (-4.8, 54.9),
            (-4.2, 54.9),
            (-4.2, 55.2),
            (-4.8, 55.2),
            (-4.8, 54.9),
        ]
    )


@pytest.fixture
def sample_points() -> list[Point]:
    """Sample points for spatial tests."""
    return [
        Point(-4.5, 55.0),  # Inside sample polygon
        Point(-4.5, 55.1),  # Inside sample polygon
        Point(-3.0, 55.0),  # Outside sample polygon
    ]
