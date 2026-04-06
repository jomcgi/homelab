"""Additional tests for scoring module: ScoredForecast model and boundary conditions."""

import pytest

from projects.stargazer.backend.scoring import (
    ScoredForecast,
    WeatherData,
    calculate_astronomy_score,
)


class TestScoredForecastModel:
    """Tests for ScoredForecast Pydantic model — previously untested."""

    def test_scored_forecast_basic_creation(self):
        """Test basic ScoredForecast creation with required fields."""
        forecast = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=85.0,
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=8.0,
            dew_spread=4.0,
            air_pressure=1020.0,
        )
        assert forecast.time == "2024-01-15T22:00:00Z"
        assert forecast.score == 85.0
        assert forecast.cloud_area_fraction == 10.0
        assert forecast.relative_humidity == 60.0
        assert forecast.fog_area_fraction == 0.0
        assert forecast.wind_speed == 3.0
        assert forecast.air_temperature == 8.0
        assert forecast.dew_spread == 4.0
        assert forecast.air_pressure == 1020.0

    def test_scored_forecast_symbol_defaults_to_empty_string(self):
        """Test that symbol defaults to empty string when not provided."""
        forecast = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=90.0,
            cloud_area_fraction=5.0,
            relative_humidity=55.0,
            fog_area_fraction=0.0,
            wind_speed=2.0,
            air_temperature=10.0,
            dew_spread=6.0,
            air_pressure=1022.0,
        )
        assert forecast.symbol == ""

    def test_scored_forecast_symbol_can_be_set(self):
        """Test that symbol can be set explicitly."""
        forecast = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=88.0,
            cloud_area_fraction=8.0,
            relative_humidity=58.0,
            fog_area_fraction=0.0,
            wind_speed=2.5,
            air_temperature=9.0,
            dew_spread=5.0,
            air_pressure=1019.0,
            symbol="clearsky_night",
        )
        assert forecast.symbol == "clearsky_night"

    def test_scored_forecast_score_min_boundary(self):
        """Test that score accepts 0.0 (minimum valid value)."""
        forecast = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=0.0,
            cloud_area_fraction=100.0,
            relative_humidity=100.0,
            fog_area_fraction=100.0,
            wind_speed=30.0,
            air_temperature=5.0,
            dew_spread=0.0,
            air_pressure=980.0,
        )
        assert forecast.score == 0.0

    def test_scored_forecast_score_max_boundary(self):
        """Test that score accepts 100.0 (maximum valid value)."""
        forecast = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=100.0,
            cloud_area_fraction=0.0,
            relative_humidity=30.0,
            fog_area_fraction=0.0,
            wind_speed=1.0,
            air_temperature=15.0,
            dew_spread=10.0,
            air_pressure=1030.0,
        )
        assert forecast.score == 100.0

    def test_scored_forecast_score_below_min_raises(self):
        """Test that score below 0 raises validation error."""
        with pytest.raises(ValueError):
            ScoredForecast(
                time="2024-01-15T22:00:00Z",
                score=-1.0,
                cloud_area_fraction=50.0,
                relative_humidity=70.0,
                fog_area_fraction=0.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_spread=3.0,
                air_pressure=1013.0,
            )

    def test_scored_forecast_score_above_max_raises(self):
        """Test that score above 100 raises validation error."""
        with pytest.raises(ValueError):
            ScoredForecast(
                time="2024-01-15T22:00:00Z",
                score=101.0,
                cloud_area_fraction=0.0,
                relative_humidity=30.0,
                fog_area_fraction=0.0,
                wind_speed=1.0,
                air_temperature=15.0,
                dew_spread=10.0,
                air_pressure=1030.0,
            )

    def test_scored_forecast_accepts_negative_air_temperature(self):
        """Test that negative temperatures (frost) are accepted."""
        forecast = ScoredForecast(
            time="2024-01-15T02:00:00Z",
            score=75.0,
            cloud_area_fraction=15.0,
            relative_humidity=65.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=-5.0,
            dew_spread=8.0,
            air_pressure=1025.0,
        )
        assert forecast.air_temperature == -5.0

    def test_scored_forecast_accepts_negative_dew_spread(self):
        """Test that negative dew spread (condensation certain) is accepted."""
        forecast = ScoredForecast(
            time="2024-01-15T02:00:00Z",
            score=20.0,
            cloud_area_fraction=70.0,
            relative_humidity=95.0,
            fog_area_fraction=30.0,
            wind_speed=8.0,
            air_temperature=4.0,
            dew_spread=-1.0,
            air_pressure=1005.0,
        )
        assert forecast.dew_spread == -1.0


class TestCloudScoreBoundaries:
    """Tests for exact cloud coverage boundary conditions in calculate_astronomy_score."""

    def _make_weather(self, cloud: float) -> WeatherData:
        """Helper: create weather with only cloud varying, all others optimal."""
        return WeatherData(
            cloud_area_fraction=cloud,
            relative_humidity=0.0,  # best humidity (< 70 → score=100)
            fog_area_fraction=0.0,  # no fog (< 5 → score=100)
            wind_speed=0.0,  # no wind (< 5 → score=100)
            air_temperature=15.0,
            dew_point_temperature=5.0,  # spread=10 > 5 → score=100
            air_pressure_at_sea_level=1013.25,  # no pressure bonus
        )

    def test_cloud_at_zero_gives_maximum_cloud_score(self):
        """Cloud = 0% → cloud_score = 100."""
        w = self._make_weather(0.0)
        score = calculate_astronomy_score(w)
        # cloud contributes 100*0.5 + 100*0.5 (other factors) = 100
        assert score == pytest.approx(100.0, abs=1.0)

    def test_cloud_just_below_20_still_max_cloud_score(self):
        """Cloud = 19.9% → cloud_score = 100 (first branch)."""
        below = self._make_weather(19.9)
        at_20 = self._make_weather(20.0)
        # Both should produce same score (20.0 enters linear branch but (20-20)*1.67=0)
        assert calculate_astronomy_score(below) == pytest.approx(
            calculate_astronomy_score(at_20), abs=0.1
        )

    def test_cloud_at_20_enters_linear_region_but_score_unchanged(self):
        """Cloud = 20% → enters linear formula but (20-20)*1.67=0, score still 100."""
        w = self._make_weather(20.0)
        score = calculate_astronomy_score(w)
        # cloud_score = 100 - 0 = 100, all others 100
        assert score == pytest.approx(100.0, abs=1.0)

    def test_cloud_at_35_midpoint_linear_region(self):
        """Cloud = 35% → cloud_score = 100 - (35-20)*1.67 = 100 - 25.05 = 74.95."""
        w = self._make_weather(35.0)
        score = calculate_astronomy_score(w)
        expected_cloud_score = 100 - (35 - 20) * 1.67  # ≈ 74.95
        # Total = cloud*0.5 + 100*0.5 (other factors)
        expected_total = expected_cloud_score * 0.5 + 50.0
        assert score == pytest.approx(expected_total, abs=0.5)

    def test_cloud_at_50_enters_step_region(self):
        """Cloud = 50% → cloud_score = max(0, 50 - (50-50)) = 50."""
        w = self._make_weather(50.0)
        score = calculate_astronomy_score(w)
        expected_cloud_score = 50.0  # max(0, 50 - 0)
        expected_total = expected_cloud_score * 0.5 + 50.0
        assert score == pytest.approx(expected_total, abs=0.5)

    def test_cloud_at_100_gives_zero_cloud_score(self):
        """Cloud = 100% → cloud_score = max(0, 50 - 50) = 0."""
        w = self._make_weather(100.0)
        score = calculate_astronomy_score(w)
        expected_cloud_score = 0.0  # max(0, 50 - 50)
        expected_total = expected_cloud_score * 0.5 + 50.0
        assert score == pytest.approx(expected_total, abs=0.5)


class TestHumidityScoreBoundaries:
    """Tests for exact humidity boundary conditions in calculate_astronomy_score."""

    def _make_weather(self, humidity: float) -> WeatherData:
        """Helper: create weather with only humidity varying."""
        return WeatherData(
            cloud_area_fraction=0.0,  # no cloud (< 20 → score=100)
            relative_humidity=humidity,
            fog_area_fraction=0.0,
            wind_speed=0.0,
            air_temperature=15.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1013.25,
        )

    def test_humidity_below_70_gives_max_humidity_score(self):
        """Humidity = 50% → humidity_score = 100."""
        w = self._make_weather(50.0)
        score = calculate_astronomy_score(w)
        # cloud=100*0.5, humidity=100*0.15, fog=100*0.1, wind=100*0.1, dew=100*0.15 = 100
        assert score == pytest.approx(100.0, abs=1.0)

    def test_humidity_at_70_enters_linear_region_with_zero_penalty(self):
        """Humidity = 70% → humidity_score = 100 - 0 = 100 (boundary, no penalty)."""
        w = self._make_weather(70.0)
        score = calculate_astronomy_score(w)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_humidity_at_85_enters_third_region(self):
        """Humidity = 85% → enters max(0,...) region. Score = 100 - (85-70)*3.33 ≈ 50."""
        w = self._make_weather(85.0)
        score = calculate_astronomy_score(w)
        expected_humidity = 100 - (85 - 70) * 3.33  # ≈ 50.05
        # all other scores = 100
        expected = 100 * 0.5 + expected_humidity * 0.15 + 100 * 0.1 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_humidity_at_100_gives_low_humidity_score(self):
        """Humidity = 100% → humidity_score = max(0, 50 - (100-85)*3.33) = max(0, 0.05) ≈ 0."""
        w = self._make_weather(100.0)
        score = calculate_astronomy_score(w)
        expected_humidity = max(0, 50 - (100 - 85) * 3.33)  # max(0, 0.05)
        expected = 100 * 0.5 + expected_humidity * 0.15 + 100 * 0.1 + 100 * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=1.0)


class TestWindScoreBoundaries:
    """Tests for exact wind speed boundary conditions."""

    def _make_weather(self, wind: float) -> WeatherData:
        """Helper: create weather with only wind varying."""
        return WeatherData(
            cloud_area_fraction=0.0,
            relative_humidity=0.0,
            fog_area_fraction=0.0,
            wind_speed=wind,
            air_temperature=15.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1013.25,
        )

    def test_wind_below_5_gives_max_wind_score(self):
        """Wind < 5 m/s → wind_score = 100."""
        w = self._make_weather(4.9)
        score = calculate_astronomy_score(w)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_wind_at_5_enters_linear_region_no_penalty(self):
        """Wind = 5 m/s → wind_score = 100 - 0 = 100."""
        w = self._make_weather(5.0)
        score = calculate_astronomy_score(w)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_wind_at_7_5_midpoint(self):
        """Wind = 7.5 m/s → wind_score = 100 - (7.5-5)*10 = 75."""
        w = self._make_weather(7.5)
        score = calculate_astronomy_score(w)
        expected_wind = 100 - (7.5 - 5) * 10  # 75
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + expected_wind * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_wind_at_10_enters_step_region(self):
        """Wind = 10 m/s → wind_score = max(0, 50 - 0) = 50."""
        w = self._make_weather(10.0)
        score = calculate_astronomy_score(w)
        expected_wind = 50.0
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + expected_wind * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_wind_at_20_gives_zero_wind_score(self):
        """Wind = 20 m/s → wind_score = max(0, 50 - 10*5) = 0."""
        w = self._make_weather(20.0)
        score = calculate_astronomy_score(w)
        expected_wind = max(0, 50 - (20 - 10) * 5)  # 0
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + expected_wind * 0.1 + 100 * 0.15
        assert score == pytest.approx(expected, abs=1.0)


class TestDewSpreadBoundaries:
    """Tests for dew spread boundary conditions in calculate_astronomy_score."""

    def _make_weather(self, temp: float, dew: float) -> WeatherData:
        """Helper: create weather with specific temp/dew_point spread."""
        return WeatherData(
            cloud_area_fraction=0.0,
            relative_humidity=0.0,
            fog_area_fraction=0.0,
            wind_speed=0.0,
            air_temperature=temp,
            dew_point_temperature=dew,
            air_pressure_at_sea_level=1013.25,
        )

    def test_dew_spread_above_5_gives_max_dew_score(self):
        """Dew spread > 5 → dew_score = 100."""
        w = self._make_weather(15.0, 5.0)  # spread = 10 > 5
        score = calculate_astronomy_score(w)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_dew_spread_exactly_5_uses_middle_formula_no_penalty(self):
        """Dew spread = 5 → middle formula: 100 - (5-5)*16.67 = 100."""
        w = self._make_weather(15.0, 10.0)  # spread = 5.0
        score = calculate_astronomy_score(w)
        expected_dew = 100 - (5 - 5) * 16.67  # 100
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + 100 * 0.1 + expected_dew * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_dew_spread_at_3_5_midpoint(self):
        """Dew spread = 3.5 → dew_score = 100 - (5-3.5)*16.67 = 75."""
        w = self._make_weather(13.5, 10.0)  # spread = 3.5
        score = calculate_astronomy_score(w)
        expected_dew = 100 - (5 - 3.5) * 16.67  # ≈ 75
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + 100 * 0.1 + expected_dew * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_dew_spread_exactly_2_enters_low_region(self):
        """Dew spread = 2 → third formula: max(0, 50 - 0) = 50."""
        w = self._make_weather(12.0, 10.0)  # spread = 2.0
        score = calculate_astronomy_score(w)
        expected_dew = max(0, 50 - (2 - 2) * 25)  # 50
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + 100 * 0.1 + expected_dew * 0.15
        assert score == pytest.approx(expected, abs=1.0)

    def test_dew_spread_negative_gives_zero_dew_score(self):
        """Dew spread < 0 (dew point above temp) → dew_score = max(0,...) = 0."""
        w = self._make_weather(5.0, 8.0)  # spread = -3 (condensation certain)
        score = calculate_astronomy_score(w)
        expected_dew = max(0, 50 - (2 - (-3)) * 25)  # max(0, 50 - 125) = 0
        expected = 100 * 0.5 + 100 * 0.15 + 100 * 0.1 + 100 * 0.1 + expected_dew * 0.15
        assert score == pytest.approx(expected, abs=1.0)


class TestPressureBonusBoundariesAndCap:
    """Tests for pressure bonus boundary and cap behavior."""

    def _make_weather(self, pressure: float) -> WeatherData:
        """Helper: create weather with 50% cloud cover (base score ≈ 75) and varying pressure.

        Using 50% cloud cover deliberately lowers the base score to ≈ 75 so that
        pressure bonus points are not swallowed by the max(0, min(100, ...)) ceiling.
        """
        return WeatherData(
            cloud_area_fraction=50.0,  # cloud_score = 50 → base ≈ 75, leaving room for bonus
            relative_humidity=0.0,
            fog_area_fraction=0.0,
            wind_speed=0.0,
            air_temperature=15.0,
            dew_point_temperature=5.0,  # spread = 10 > 5 → dew_score = 100
            air_pressure_at_sea_level=pressure,
        )

    def test_pressure_at_exactly_1015_gives_no_bonus(self):
        """Pressure = 1015 hPa → NOT > 1015, bonus = 0."""
        no_bonus = self._make_weather(1013.25)  # standard pressure, no bonus
        at_threshold = self._make_weather(1015.0)  # exactly at threshold, still no bonus
        # Both should give same base score (no bonus)
        assert calculate_astronomy_score(no_bonus) == pytest.approx(
            calculate_astronomy_score(at_threshold), abs=0.1
        )

    def test_pressure_just_above_1015_gives_small_bonus(self):
        """Pressure = 1016 hPa → bonus = (1016-1015)*2 = 2."""
        low = self._make_weather(1015.0)   # no bonus
        high = self._make_weather(1016.0)  # bonus = 2
        diff = calculate_astronomy_score(high) - calculate_astronomy_score(low)
        # base ≈ 75, so 75 + 2 = 77 — well below 100 ceiling
        assert diff == pytest.approx(2.0, abs=0.1)

    def test_pressure_bonus_capped_at_10(self):
        """Pressure >= 1020 hPa → bonus capped at 10 regardless of higher pressure."""
        at_cap = self._make_weather(1020.0)     # (1020-1015)*2 = 10 → at cap
        above_cap = self._make_weather(1030.0)  # (1030-1015)*2 = 30 → still 10
        # Scores should be equal because bonus is capped at 10
        assert calculate_astronomy_score(at_cap) == pytest.approx(
            calculate_astronomy_score(above_cap), abs=0.01
        )

    def test_pressure_bonus_at_cap_adds_exactly_10(self):
        """Pressure = 1020 hPa → bonus = exactly 10 points over no-bonus case."""
        no_bonus = self._make_weather(1015.0)
        max_bonus = self._make_weather(1020.0)
        diff = calculate_astronomy_score(max_bonus) - calculate_astronomy_score(no_bonus)
        # base ≈ 75, so 75 + 10 = 85 — below 100 ceiling, full 10-point bonus applies
        assert diff == pytest.approx(10.0, abs=0.1)
