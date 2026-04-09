"""Unit tests for the scoring module."""

import pytest

from projects.stargazer.backend.scoring import (
    WeatherData,
    ScoredForecast,
    calculate_astronomy_score,
    is_dark_enough,
)


class TestWeatherDataValidation:
    """Tests for WeatherData model validation."""

    def test_accepts_valid_data(self):
        """WeatherData should accept valid input."""
        w = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.cloud_area_fraction == 10.0
        assert w.relative_humidity == 60.0

    def test_fog_defaults_to_zero(self):
        """fog_area_fraction defaults to 0."""
        w = WeatherData(
            cloud_area_fraction=50.0,
            relative_humidity=70.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.fog_area_fraction == 0.0

    def test_pressure_defaults_to_standard(self):
        """air_pressure_at_sea_level defaults to 1013.25."""
        w = WeatherData(
            cloud_area_fraction=50.0,
            relative_humidity=70.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.air_pressure_at_sea_level == 1013.25

    def test_rejects_negative_cloud_fraction(self):
        """Cloud fraction must be >= 0."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=-1.0,
                relative_humidity=50.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_rejects_cloud_fraction_over_100(self):
        """Cloud fraction must be <= 100."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=101.0,
                relative_humidity=50.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_rejects_negative_humidity(self):
        """Relative humidity must be >= 0."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=50.0,
                relative_humidity=-5.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_rejects_humidity_over_100(self):
        """Relative humidity must be <= 100."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=50.0,
                relative_humidity=105.0,
                wind_speed=5.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_rejects_negative_wind_speed(self):
        """Wind speed must be >= 0."""
        with pytest.raises(ValueError):
            WeatherData(
                cloud_area_fraction=50.0,
                relative_humidity=50.0,
                wind_speed=-1.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_accepts_zero_wind_speed(self):
        """Wind speed of zero (calm) is valid."""
        w = WeatherData(
            cloud_area_fraction=50.0,
            relative_humidity=50.0,
            wind_speed=0.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.wind_speed == 0.0

    def test_accepts_boundary_cloud_values(self):
        """Cloud fraction boundary values 0 and 100 are valid."""
        w_clear = WeatherData(
            cloud_area_fraction=0.0,
            relative_humidity=50.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w_clear.cloud_area_fraction == 0.0

        w_overcast = WeatherData(
            cloud_area_fraction=100.0,
            relative_humidity=50.0,
            wind_speed=5.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w_overcast.cloud_area_fraction == 100.0

    def test_negative_temperature_is_valid(self):
        """Air temperature can be negative (below freezing)."""
        w = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=50.0,
            wind_speed=3.0,
            air_temperature=-10.0,
            dew_point_temperature=-15.0,
        )
        assert w.air_temperature == -10.0


class TestScoredForecastModel:
    """Tests for ScoredForecast model."""

    def test_accepts_valid_scored_forecast(self):
        """ScoredForecast should accept valid data."""
        sf = ScoredForecast(
            time="2024-01-15T22:00:00Z",
            score=85.0,
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=8.0,
            dew_spread=5.0,
            air_pressure=1018.0,
        )
        assert sf.score == 85.0
        assert sf.symbol == ""  # default

    def test_score_must_be_0_to_100(self):
        """Score must be between 0 and 100."""
        with pytest.raises(ValueError):
            ScoredForecast(
                time="2024-01-15T22:00:00Z",
                score=101.0,
                cloud_area_fraction=10.0,
                relative_humidity=60.0,
                fog_area_fraction=0.0,
                wind_speed=3.0,
                air_temperature=8.0,
                dew_spread=5.0,
                air_pressure=1018.0,
            )


class TestCalculateAstronomyScore:
    """Tests for calculate_astronomy_score function."""

    def _make_weather(self, **kwargs) -> WeatherData:
        """Helper: create WeatherData with sensible defaults."""
        defaults = {
            "cloud_area_fraction": 0.0,
            "relative_humidity": 40.0,
            "fog_area_fraction": 0.0,
            "wind_speed": 2.0,
            "air_temperature": 15.0,
            "dew_point_temperature": 5.0,
            "air_pressure_at_sea_level": 1030.0,
        }
        defaults.update(kwargs)
        return WeatherData(**defaults)

    def test_score_always_in_0_to_100_range(self):
        """Score must always be clamped to [0, 100]."""
        worst = self._make_weather(
            cloud_area_fraction=100.0,
            relative_humidity=100.0,
            fog_area_fraction=100.0,
            wind_speed=100.0,
            air_temperature=0.0,
            dew_point_temperature=0.0,
            air_pressure_at_sea_level=900.0,
        )
        assert 0.0 <= calculate_astronomy_score(worst) <= 100.0

        best = self._make_weather()
        assert 0.0 <= calculate_astronomy_score(best) <= 100.0

    def test_ideal_conditions_score_near_100(self):
        """Near-perfect conditions should produce a very high score."""
        score = calculate_astronomy_score(self._make_weather())
        assert score >= 95.0

    def test_full_cloud_cover_penalises_heavily(self):
        """100% cloud cover should reduce score significantly (cloud = 50% weight)."""
        clear_score = calculate_astronomy_score(self._make_weather(cloud_area_fraction=0.0))
        cloudy_score = calculate_astronomy_score(self._make_weather(cloud_area_fraction=100.0))
        assert clear_score - cloudy_score >= 40.0

    def test_cloud_below_20_scores_100_cloud_component(self):
        """Cloud fraction < 20 is the perfect band — verify it produces higher score
        than cloud fraction of exactly 20."""
        score_10 = calculate_astronomy_score(self._make_weather(cloud_area_fraction=10.0))
        score_20 = calculate_astronomy_score(self._make_weather(cloud_area_fraction=20.0))
        # Both may be capped at 100 due to other components, but 10 should be >= 20
        assert score_10 >= score_20

    def test_cloud_between_20_and_50_linear_penalty(self):
        """Cloud fraction in [20, 50) should linearly degrade the cloud component."""
        score_25 = calculate_astronomy_score(self._make_weather(cloud_area_fraction=25.0))
        score_45 = calculate_astronomy_score(self._make_weather(cloud_area_fraction=45.0))
        assert score_25 > score_45

    def test_humidity_below_70_no_penalty(self):
        """Humidity < 70% should not penalise humidity component."""
        score_40 = calculate_astronomy_score(self._make_weather(relative_humidity=40.0))
        score_69 = calculate_astronomy_score(self._make_weather(relative_humidity=69.0))
        # Both should be max humidity component, so scores equal
        assert score_40 == pytest.approx(score_69, abs=0.1)

    def test_high_humidity_penalises_score(self):
        """Humidity >= 85 should penalise the score."""
        score_low_hum = calculate_astronomy_score(self._make_weather(relative_humidity=50.0))
        score_high_hum = calculate_astronomy_score(self._make_weather(relative_humidity=95.0))
        assert score_low_hum > score_high_hum

    def test_fog_below_5_no_penalty(self):
        """Fog < 5% should not penalise fog component."""
        score_no_fog = calculate_astronomy_score(self._make_weather(fog_area_fraction=0.0))
        score_low_fog = calculate_astronomy_score(self._make_weather(fog_area_fraction=4.9))
        assert score_no_fog == pytest.approx(score_low_fog, abs=0.1)

    def test_heavy_fog_penalises_score(self):
        """Heavy fog (>20%) should reduce score vs no fog, holding other conditions fixed
        at values that leave headroom below 100."""
        base = {
            "cloud_area_fraction": 30.0,  # some clouds to leave headroom
            "relative_humidity": 75.0,
            "wind_speed": 6.0,
            "air_temperature": 10.0,
            "dew_point_temperature": 7.0,
            "air_pressure_at_sea_level": 1013.0,
        }
        no_fog_score = calculate_astronomy_score(self._make_weather(fog_area_fraction=0.0, **base))
        heavy_fog_score = calculate_astronomy_score(self._make_weather(fog_area_fraction=50.0, **base))
        assert no_fog_score > heavy_fog_score

    def test_calm_wind_better_than_strong_wind(self):
        """Wind < 5 m/s is better than strong wind; use conditions below 100 ceiling."""
        base = {
            "cloud_area_fraction": 30.0,
            "relative_humidity": 75.0,
            "fog_area_fraction": 5.0,
            "air_temperature": 10.0,
            "dew_point_temperature": 7.0,
            "air_pressure_at_sea_level": 1013.0,
        }
        calm_score = calculate_astronomy_score(self._make_weather(wind_speed=2.0, **base))
        strong_score = calculate_astronomy_score(self._make_weather(wind_speed=20.0, **base))
        assert calm_score > strong_score

    def test_wind_between_5_and_10_linear_penalty(self):
        """Wind in [5, 10) should linearly degrade wind component."""
        base = {
            "cloud_area_fraction": 30.0,
            "relative_humidity": 75.0,
            "fog_area_fraction": 5.0,
            "air_temperature": 10.0,
            "dew_point_temperature": 7.0,
            "air_pressure_at_sea_level": 1013.0,
        }
        score_6 = calculate_astronomy_score(self._make_weather(wind_speed=6.0, **base))
        score_9 = calculate_astronomy_score(self._make_weather(wind_speed=9.0, **base))
        assert score_6 > score_9

    def test_good_dew_spread_scores_higher(self):
        """Dew spread > 5°C should yield maximum dew component."""
        good_spread = self._make_weather(air_temperature=15.0, dew_point_temperature=5.0)  # 10°C spread
        poor_spread = self._make_weather(air_temperature=10.0, dew_point_temperature=9.5)  # 0.5°C spread
        assert calculate_astronomy_score(good_spread) > calculate_astronomy_score(poor_spread)

    def test_negative_dew_spread_penalised(self):
        """Temperature below dew point (impossible but handled) — dew_spread < 0."""
        neg_spread = self._make_weather(air_temperature=5.0, dew_point_temperature=8.0)  # -3°C
        pos_spread = self._make_weather(air_temperature=15.0, dew_point_temperature=5.0)  # +10°C
        assert calculate_astronomy_score(pos_spread) > calculate_astronomy_score(neg_spread)

    def test_high_pressure_gives_bonus(self):
        """Pressure > 1015 hPa should add a bonus of up to 10 points."""
        low_p = self._make_weather(
            cloud_area_fraction=30.0,  # Not perfect, so bonus is visible
            air_pressure_at_sea_level=1005.0,
        )
        high_p = self._make_weather(
            cloud_area_fraction=30.0,
            air_pressure_at_sea_level=1025.0,
        )
        assert calculate_astronomy_score(high_p) > calculate_astronomy_score(low_p)

    def test_pressure_bonus_capped_at_10(self):
        """Pressure bonus should not exceed 10 points even at extreme pressure."""
        moderate_high_p = self._make_weather(
            cloud_area_fraction=50.0,
            air_pressure_at_sea_level=1020.0,  # +5 hPa → 10 point bonus (capped)
        )
        extreme_high_p = self._make_weather(
            cloud_area_fraction=50.0,
            air_pressure_at_sea_level=1100.0,  # Far above 1015
        )
        # Both have the maximum bonus, so scores should be equal
        assert calculate_astronomy_score(extreme_high_p) == pytest.approx(
            calculate_astronomy_score(moderate_high_p), abs=0.1
        )

    def test_pressure_at_1015_no_bonus(self):
        """Pressure exactly at 1015 hPa gives no bonus."""
        at_threshold = self._make_weather(
            cloud_area_fraction=50.0,
            air_pressure_at_sea_level=1015.0,
        )
        below_threshold = self._make_weather(
            cloud_area_fraction=50.0,
            air_pressure_at_sea_level=1010.0,
        )
        # 1015 gives 0 bonus; 1010 also gives 0 bonus — they should be equal
        assert calculate_astronomy_score(at_threshold) == pytest.approx(
            calculate_astronomy_score(below_threshold), abs=0.1
        )

    def test_score_capped_at_100(self):
        """Score should never exceed 100 even with all perfect conditions."""
        perfect = self._make_weather(air_pressure_at_sea_level=9999.0)
        assert calculate_astronomy_score(perfect) <= 100.0

    def test_score_clamped_at_0(self):
        """Score should never be negative."""
        terrible = WeatherData(
            cloud_area_fraction=100.0,
            relative_humidity=100.0,
            fog_area_fraction=100.0,
            wind_speed=100.0,
            air_temperature=0.0,
            dew_point_temperature=10.0,  # negative dew spread
            air_pressure_at_sea_level=900.0,
        )
        assert calculate_astronomy_score(terrible) >= 0.0

    def test_weighted_average_components(self):
        """Verify weight distribution: cloud 50%, humidity 15%, fog 10%, wind 10%, dew 15%."""
        # All perfect except clouds at 100% — should reduce score by ~50 points
        base = WeatherData(
            cloud_area_fraction=0.0,
            relative_humidity=40.0,
            fog_area_fraction=0.0,
            wind_speed=2.0,
            air_temperature=15.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1013.0,
        )
        all_cloud = WeatherData(
            cloud_area_fraction=100.0,
            relative_humidity=40.0,
            fog_area_fraction=0.0,
            wind_speed=2.0,
            air_temperature=15.0,
            dew_point_temperature=5.0,
            air_pressure_at_sea_level=1013.0,
        )
        diff = calculate_astronomy_score(base) - calculate_astronomy_score(all_cloud)
        # Cloud is 50% weight and score goes from 100 to 0 at full cloud: ~50 point diff
        assert 40.0 <= diff <= 60.0


class TestIsDarkEnough:
    """Tests for is_dark_enough function."""

    def test_sun_at_minus_18_is_dark(self):
        """Exactly at astronomical darkness threshold should be True."""
        assert is_dark_enough(-18.0) is True

    def test_sun_below_minus_18_is_dark(self):
        """Sun deeper below horizon → definitely dark."""
        assert is_dark_enough(-20.0) is True
        assert is_dark_enough(-30.0) is True
        assert is_dark_enough(-90.0) is True

    def test_sun_just_above_threshold_is_not_dark(self):
        """Sun at -17.9 is just above the default threshold → not dark."""
        assert is_dark_enough(-17.9) is False

    def test_nautical_twilight_not_dark(self):
        """Nautical twilight (-12°) is not dark by default."""
        assert is_dark_enough(-12.0) is False

    def test_civil_twilight_not_dark(self):
        """Civil twilight (-6°) is not dark."""
        assert is_dark_enough(-6.0) is False

    def test_daytime_not_dark(self):
        """Sun above horizon is never dark."""
        assert is_dark_enough(0.0) is False
        assert is_dark_enough(45.0) is False
        assert is_dark_enough(90.0) is False

    def test_custom_threshold_nautical(self):
        """Custom threshold of -12° for nautical darkness."""
        assert is_dark_enough(-12.0, astronomical_darkness_threshold=-12.0) is True
        assert is_dark_enough(-11.9, astronomical_darkness_threshold=-12.0) is False

    def test_custom_threshold_civil(self):
        """Custom threshold of -6° for civil darkness."""
        assert is_dark_enough(-6.0, astronomical_darkness_threshold=-6.0) is True
        assert is_dark_enough(-5.9, astronomical_darkness_threshold=-6.0) is False

    def test_at_exact_threshold_is_true(self):
        """Boundary condition: exactly equal to threshold should be True (<=)."""
        for threshold in [-6.0, -12.0, -18.0]:
            assert is_dark_enough(threshold, threshold) is True

    def test_just_above_threshold_is_false(self):
        """One hundredth of a degree above threshold should be False."""
        assert is_dark_enough(-17.99, -18.0) is False
