"""Tests for the scoring module."""

import pytest

from projects.stargazer.backend.scoring import (
    WeatherData,
    calculate_astronomy_score,
    is_dark_enough,
)


class TestWeatherDataModel:
    """Tests for WeatherData Pydantic model."""

    def test_valid_weather_data(self, sample_weather_data: WeatherData):
        """Test that valid weather data is accepted."""
        assert sample_weather_data.cloud_area_fraction == 10.0
        assert sample_weather_data.relative_humidity == 60.0
        assert sample_weather_data.wind_speed == 3.0

    def test_weather_data_with_defaults(self):
        """Test weather data uses correct defaults."""
        weather = WeatherData(
            cloud_area_fraction=50.0,
            relative_humidity=70.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert weather.fog_area_fraction == 0.0
        assert weather.air_pressure_at_sea_level == 1013.25

    def test_cloud_fraction_validation_min(self):
        """Test cloud fraction must be >= 0."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=-1.0,
                relative_humidity=50.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_cloud_fraction_validation_max(self):
        """Test cloud fraction must be <= 100."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=101.0,
                relative_humidity=50.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_humidity_validation(self):
        """Test humidity must be in valid range."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=50.0,
                relative_humidity=-5.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_wind_speed_validation(self):
        """Test wind speed must be >= 0."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=50.0,
                relative_humidity=50.0,
                wind_speed=-1.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )


class TestCalculateAstronomyScore:
    """Tests for calculate_astronomy_score function."""

    def test_ideal_conditions_high_score(self, ideal_weather_data: WeatherData):
        """Test that ideal conditions produce high score."""
        score = calculate_astronomy_score(ideal_weather_data)
        assert score >= 95.0
        assert score <= 100.0

    def test_clear_sky_good_score(self, sample_weather_data: WeatherData):
        """Test that clear sky conditions produce good score."""
        score = calculate_astronomy_score(sample_weather_data)
        assert score >= 80.0

    def test_cloudy_conditions_low_score(self, cloudy_weather_data: WeatherData):
        """Test that cloudy conditions produce low score."""
        score = calculate_astronomy_score(cloudy_weather_data)
        assert score < 50.0

    def test_score_bounds(self):
        """Test that score is always between 0 and 100."""
        # Worst conditions
        worst = WeatherData(
            cloud_area_fraction=100.0,
            relative_humidity=100.0,
            fog_area_fraction=100.0,
            wind_speed=50.0,
            air_temperature=0.0,
            dew_point_temperature=0.0,  # No dew spread
            air_pressure_at_sea_level=980.0,
        )
        score = calculate_astronomy_score(worst)
        assert 0.0 <= score <= 100.0

    def test_cloud_score_weight(self):
        """Test that clouds have the most impact on score."""
        clear = WeatherData(
            cloud_area_fraction=0.0,
            relative_humidity=70.0,
            fog_area_fraction=0.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        cloudy = WeatherData(
            cloud_area_fraction=100.0,
            relative_humidity=70.0,
            fog_area_fraction=0.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        clear_score = calculate_astronomy_score(clear)
        cloudy_score = calculate_astronomy_score(cloudy)

        # Cloud difference should cause at least 40 point difference (50% weight)
        assert clear_score - cloudy_score >= 40.0

    def test_pressure_bonus(self):
        """Test high pressure adds bonus points."""
        # Use conditions that won't hit the 100 ceiling
        low_pressure = WeatherData(
            cloud_area_fraction=30.0,  # Some clouds to lower base score
            relative_humidity=75.0,
            fog_area_fraction=5.0,
            wind_speed=6.0,
            air_temperature=10.0,
            dew_point_temperature=7.0,  # Smaller dew spread
            air_pressure_at_sea_level=1005.0,
        )
        high_pressure = WeatherData(
            cloud_area_fraction=30.0,
            relative_humidity=75.0,
            fog_area_fraction=5.0,
            wind_speed=6.0,
            air_temperature=10.0,
            dew_point_temperature=7.0,
            air_pressure_at_sea_level=1025.0,
        )
        low_score = calculate_astronomy_score(low_pressure)
        high_score = calculate_astronomy_score(high_pressure)

        # High pressure should give bonus (up to 10 points)
        assert high_score > low_score

    def test_dew_spread_impact(self):
        """Test that dew spread affects score."""
        good_spread = WeatherData(
            cloud_area_fraction=20.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=15.0,
            dew_point_temperature=5.0,  # 10 degree spread
            air_pressure_at_sea_level=1015.0,
        )
        poor_spread = WeatherData(
            cloud_area_fraction=20.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=9.0,  # 1 degree spread (condensation risk)
            air_pressure_at_sea_level=1015.0,
        )
        good_score = calculate_astronomy_score(good_spread)
        poor_score = calculate_astronomy_score(poor_spread)

        assert good_score > poor_score

    def test_wind_impact(self):
        """Test that high wind reduces score."""
        calm = WeatherData(
            cloud_area_fraction=20.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=2.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        windy = WeatherData(
            cloud_area_fraction=20.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=15.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        calm_score = calculate_astronomy_score(calm)
        windy_score = calculate_astronomy_score(windy)

        assert calm_score > windy_score

    def test_fog_impact(self):
        """Test that fog significantly reduces score."""
        no_fog = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        foggy = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=50.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1015.0,
        )
        no_fog_score = calculate_astronomy_score(no_fog)
        foggy_score = calculate_astronomy_score(foggy)

        assert no_fog_score > foggy_score


class TestIsDarkEnough:
    """Tests for is_dark_enough function."""

    def test_astronomical_darkness(self):
        """Test that sun at -18 or below is dark enough."""
        assert is_dark_enough(-18.0) is True
        assert is_dark_enough(-20.0) is True
        assert is_dark_enough(-25.0) is True

    def test_nautical_twilight(self):
        """Test that nautical twilight is not dark enough by default."""
        assert is_dark_enough(-12.0) is False
        assert is_dark_enough(-15.0) is False

    def test_civil_twilight(self):
        """Test that civil twilight is not dark enough."""
        assert is_dark_enough(-6.0) is False

    def test_daytime(self):
        """Test that daytime is not dark enough."""
        assert is_dark_enough(0.0) is False
        assert is_dark_enough(30.0) is False
        assert is_dark_enough(90.0) is False

    def test_custom_threshold(self):
        """Test custom darkness threshold."""
        # Using nautical darkness threshold (-12)
        assert is_dark_enough(-12.0, astronomical_darkness_threshold=-12.0) is True
        assert is_dark_enough(-10.0, astronomical_darkness_threshold=-12.0) is False

    def test_boundary_condition(self):
        """Test exact boundary at -18 degrees."""
        assert is_dark_enough(-18.0) is True
        assert is_dark_enough(-17.9) is False
