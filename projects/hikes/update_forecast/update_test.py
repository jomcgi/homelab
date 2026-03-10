"""Tests for weather forecast update service."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests  # nosemgrep: no-requests

from projects.hikes.update_forecast.update import (
    Walk,
    create_bundle,
    fetch_weather_forecast,
    is_daylight_hour,
    is_weather_viable,
    load_walks_from_db,
    parse_weather_data,
    process_walk,
)


class TestWalkModel:
    """Tests for Walk Pydantic model."""

    def test_create_walk(self):
        walk = Walk(
            uuid="test-uuid",
            name="Ben Nevis",
            url="https://example.com/walk",
            distance_km=17.0,
            ascent_m=1350,
            duration_h=8.5,
            summary="A great mountain walk",
            latitude=56.7969,
            longitude=-5.0035,
        )

        assert walk.uuid == "test-uuid"
        assert walk.name == "Ben Nevis"
        assert walk.distance_km == 17.0


class TestFetchWeatherForecast:
    """Tests for weather API fetching."""

    def test_fetch_weather_success(self):
        """Successful weather fetch returns JSON data."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "Feature",
            "properties": {"timeseries": []},
        }
        mock_response.status_code = 200

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = fetch_weather_forecast(56.7969, -5.0035)

            assert result is not None
            assert "properties" in result
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[1]["params"]["lat"] == 56.7969
            assert call_args[1]["params"]["lon"] == -5.0035

    def test_fetch_weather_rounds_coordinates(self):
        """Coordinates are rounded to 4 decimal places."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"properties": {"timeseries": []}}

        with patch("requests.get", return_value=mock_response) as mock_get:
            fetch_weather_forecast(56.79691234, -5.00351234)

            call_args = mock_get.call_args
            assert call_args[1]["params"]["lat"] == 56.7969
            assert call_args[1]["params"]["lon"] == -5.0035

    def test_fetch_weather_network_error(self):
        """Network errors return None."""
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            result = fetch_weather_forecast(56.7969, -5.0035)
            assert result is None

    def test_fetch_weather_http_error(self):
        """HTTP errors return None."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404")

        with patch("requests.get", return_value=mock_response):
            result = fetch_weather_forecast(56.7969, -5.0035)
            assert result is None


class TestParseWeatherData:
    """Tests for weather data parsing."""

    def test_parse_weather_data_success(self):
        """Valid forecast data is parsed correctly."""
        forecast_data = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-03-15T10:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 10.5,
                                    "wind_speed": 5.0,
                                    "cloud_area_fraction": 25.0,
                                }
                            },
                            "next_1_hours": {"details": {"precipitation_amount": 0.5}},
                        },
                    }
                ]
            }
        }

        result = parse_weather_data(forecast_data)

        assert len(result) == 1
        assert result[0]["time"] == "2024-03-15T10:00:00Z"
        assert result[0]["temp_c"] == 10.5
        assert result[0]["wind_speed_ms"] == 5.0
        assert result[0]["precipitation_mm"] == 0.5
        assert result[0]["cloud_area_fraction"] == 25.0

    def test_parse_weather_data_missing_hourly(self):
        """Entries without next_1_hours are skipped."""
        forecast_data = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-03-15T10:00:00Z",
                        "data": {
                            "instant": {"details": {"air_temperature": 10.5}},
                            # No next_1_hours
                        },
                    }
                ]
            }
        }

        result = parse_weather_data(forecast_data)

        assert len(result) == 0

    def test_parse_weather_data_none(self):
        result = parse_weather_data(None)
        assert result == []

    def test_parse_weather_data_no_properties(self):
        result = parse_weather_data({})
        assert result == []


class TestIsWeatherViable:
    """Tests for weather viability checks."""

    def test_good_weather(self):
        """Low precipitation and wind is viable."""
        weather = {"precipitation_mm": 0.5, "wind_speed_ms": 5.0}
        assert is_weather_viable(weather) is True

    def test_high_precipitation(self):
        """Heavy rain is not viable."""
        weather = {"precipitation_mm": 3.0, "wind_speed_ms": 5.0}
        assert is_weather_viable(weather) is False

    def test_threshold_precipitation(self):
        """Precipitation exactly at threshold is viable."""
        weather = {"precipitation_mm": 2.0, "wind_speed_ms": 5.0}
        assert is_weather_viable(weather) is True

    def test_high_wind(self):
        """Strong wind is not viable (80+ km/h)."""
        # 80 km/h = 22.22 m/s
        weather = {"precipitation_mm": 0, "wind_speed_ms": 23.0}
        assert is_weather_viable(weather) is False

    def test_threshold_wind(self):
        """Wind exactly at threshold is viable."""
        # 80 km/h = 22.22 m/s, but threshold checks > 80
        weather = {"precipitation_mm": 0, "wind_speed_ms": 22.2}
        assert is_weather_viable(weather) is True

    def test_missing_values(self):
        """Missing values default to safe values."""
        weather = {}
        assert is_weather_viable(weather) is True


class TestIsDaylightHour:
    """Tests for daylight hour checking."""

    def test_midday_is_daylight(self):
        result = is_daylight_hour("2024-03-15T12:00:00Z", 56.0, -5.0)
        assert result is True

    def test_morning_is_daylight(self):
        result = is_daylight_hour("2024-03-15T08:00:00Z", 56.0, -5.0)
        assert result is True

    def test_evening_is_daylight(self):
        result = is_daylight_hour("2024-03-15T18:00:00Z", 56.0, -5.0)
        assert result is True

    def test_early_morning_not_daylight(self):
        result = is_daylight_hour("2024-03-15T05:00:00Z", 56.0, -5.0)
        assert result is False

    def test_night_not_daylight(self):
        result = is_daylight_hour("2024-03-15T22:00:00Z", 56.0, -5.0)
        assert result is False

    def test_boundary_7am(self):
        result = is_daylight_hour("2024-03-15T07:00:00Z", 56.0, -5.0)
        assert result is True

    def test_boundary_7pm(self):
        result = is_daylight_hour("2024-03-15T19:00:00Z", 56.0, -5.0)
        assert result is True


class TestProcessWalk:
    """Tests for processing individual walks."""

    @pytest.fixture
    def sample_walk(self):
        return Walk(
            uuid="test-uuid",
            name="Test Walk",
            url="https://example.com",
            distance_km=10.0,
            ascent_m=500,
            duration_h=4.0,
            summary="A test walk",
            latitude=56.0,
            longitude=-5.0,
        )

    def test_process_walk_with_viable_windows(self, sample_walk):
        """Walk with good weather returns viable windows."""
        now = datetime.now(timezone.utc)
        tomorrow_noon = (now + timedelta(days=1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )

        forecast_data = {
            "properties": {
                "timeseries": [
                    {
                        "time": tomorrow_noon.isoformat(),
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 15.0,
                                    "wind_speed": 3.0,
                                    "cloud_area_fraction": 20.0,
                                }
                            },
                            "next_1_hours": {"details": {"precipitation_amount": 0}},
                        },
                    }
                ]
            }
        }

        with patch(
            "projects.hikes.update_forecast.update.fetch_weather_forecast",
            return_value=forecast_data,
        ):
            result = process_walk(sample_walk)

            assert result["walk"] == sample_walk
            assert len(result["windows"]) >= 1

    def test_process_walk_no_forecast(self, sample_walk):
        """Walk without forecast data returns empty windows."""
        with patch(
            "projects.hikes.update_forecast.update.fetch_weather_forecast",
            return_value=None,
        ):
            result = process_walk(sample_walk)

            assert result["walk"] == sample_walk
            assert result["windows"] == []


class TestCreateBundle:
    """Tests for bundle creation."""

    def test_create_empty_bundle(self):
        result = create_bundle([])

        assert result["v"] == 2
        assert "g" in result  # Generated timestamp
        assert result["d"] == []

    def test_create_bundle_with_walks(self):
        walk = Walk(
            uuid="test-uuid",
            name="Test Walk",
            url="https://example.com",
            distance_km=10.5,
            ascent_m=500,
            duration_h=4.0,
            summary="A test walk",
            latitude=56.7969,
            longitude=-5.0035,
        )

        walks_data = [{"walk": walk, "windows": [[1710500000, 15.0, 0, 10, 20]]}]

        result = create_bundle(walks_data)

        assert result["v"] == 2
        assert len(result["d"]) == 1

        entry = result["d"][0]
        assert entry[0] == "test-uuid"  # uuid
        assert entry[1] == pytest.approx(56.7969, rel=1e-4)  # lat
        assert entry[2] == pytest.approx(-5.0035, rel=1e-4)  # lng
        assert entry[3] == 4.0  # duration
        assert entry[4] == 10.5  # distance
        assert entry[5] == 500  # ascent
        assert entry[6] == "Test Walk"  # name
        assert entry[7] == "https://example.com"  # url
        assert entry[8] == "A test walk"  # summary
        assert len(entry[9]) == 1  # windows


class TestLoadWalksFromDb:
    """Tests for database loading."""

    def test_load_walks_missing_db(self, tmp_path, monkeypatch):
        """Missing database causes system exit."""
        # Patch the db_path to point to non-existent file
        with patch("projects.hikes.update_forecast.update.Path") as mock_path:
            mock_path.return_value.parent.__truediv__.return_value.__truediv__.return_value = (
                tmp_path / "nonexistent.db"
            )
            mock_path.return_value.parent = tmp_path

            with pytest.raises(SystemExit):
                load_walks_from_db()
