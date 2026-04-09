"""Unit tests for the config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from projects.stargazer.backend.config import (
    BoundsConfig,
    EuropeBoundsConfig,
    Settings,
)


class TestBoundsConfig:
    """Tests for BoundsConfig defaults and environment overrides."""

    def test_default_north_is_shetland(self):
        """Northern bound should cover Shetland (~60.86°N)."""
        b = BoundsConfig()
        assert b.north == pytest.approx(60.86)

    def test_default_south_is_scottish_borders(self):
        """Southern bound should cover Scottish Borders (~54.63°N)."""
        b = BoundsConfig()
        assert b.south == pytest.approx(54.63)

    def test_default_west_is_outer_hebrides(self):
        """Western bound should cover Outer Hebrides (~-8.65°E)."""
        b = BoundsConfig()
        assert b.west == pytest.approx(-8.65)

    def test_default_east_is_aberdeenshire(self):
        """Eastern bound should cover Aberdeenshire coast (~-0.76°E)."""
        b = BoundsConfig()
        assert b.east == pytest.approx(-0.76)

    def test_env_var_overrides_north(self):
        """BOUNDS_NORTH env var should override north."""
        with patch.dict(os.environ, {"BOUNDS_NORTH": "61.5"}):
            b = BoundsConfig()
        assert b.north == pytest.approx(61.5)

    def test_env_var_overrides_south(self):
        """BOUNDS_SOUTH env var should override south."""
        with patch.dict(os.environ, {"BOUNDS_SOUTH": "55.0"}):
            b = BoundsConfig()
        assert b.south == pytest.approx(55.0)

    def test_env_var_overrides_west(self):
        """BOUNDS_WEST env var should override west."""
        with patch.dict(os.environ, {"BOUNDS_WEST": "-9.0"}):
            b = BoundsConfig()
        assert b.west == pytest.approx(-9.0)

    def test_env_var_overrides_east(self):
        """BOUNDS_EAST env var should override east."""
        with patch.dict(os.environ, {"BOUNDS_EAST": "-1.0"}):
            b = BoundsConfig()
        assert b.east == pytest.approx(-1.0)

    def test_north_greater_than_south(self):
        """Sanity: north > south."""
        b = BoundsConfig()
        assert b.north > b.south

    def test_west_less_than_east(self):
        """Sanity: west < east (both negative, west more negative)."""
        b = BoundsConfig()
        assert b.west < b.east


class TestEuropeBoundsConfig:
    """Tests for EuropeBoundsConfig defaults."""

    def test_default_north(self):
        b = EuropeBoundsConfig()
        assert b.north == pytest.approx(75.0)

    def test_default_south(self):
        b = EuropeBoundsConfig()
        assert b.south == pytest.approx(34.0)

    def test_default_west(self):
        b = EuropeBoundsConfig()
        assert b.west == pytest.approx(-32.0)

    def test_default_east(self):
        b = EuropeBoundsConfig()
        assert b.east == pytest.approx(70.0)

    def test_covers_portugal(self):
        """Western extent should include Portugal (~-9°)."""
        b = EuropeBoundsConfig()
        assert b.west <= -9.0

    def test_covers_scandinavia(self):
        """Northern extent should include Scandinavia (>70°N)."""
        b = EuropeBoundsConfig()
        assert b.north >= 70.0

    def test_covers_mediterranean(self):
        """Southern extent should include Mediterranean (<36°N)."""
        b = EuropeBoundsConfig()
        assert b.south <= 36.0

    def test_north_greater_than_south(self):
        b = EuropeBoundsConfig()
        assert b.north > b.south


class TestSettingsPaths:
    """Tests for Settings directory properties."""

    def test_raw_dir_is_under_data_dir(self, tmp_path):
        s = Settings(data_dir=tmp_path)
        assert s.raw_dir == tmp_path / "raw"

    def test_processed_dir_is_under_data_dir(self, tmp_path):
        s = Settings(data_dir=tmp_path)
        assert s.processed_dir == tmp_path / "processed"

    def test_cache_dir_is_under_data_dir(self, tmp_path):
        s = Settings(data_dir=tmp_path)
        assert s.cache_dir == tmp_path / "cache"

    def test_output_dir_is_under_data_dir(self, tmp_path):
        s = Settings(data_dir=tmp_path)
        assert s.output_dir == tmp_path / "output"

    def test_default_data_dir(self):
        s = Settings()
        assert s.data_dir == Path("/data")

    def test_data_dir_from_env(self, tmp_path):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            s = Settings()
        assert s.data_dir == tmp_path


class TestSettingsDefaults:
    """Tests for Settings scalar defaults."""

    def test_default_color_tolerance(self):
        assert Settings().color_tolerance == 15

    def test_default_road_buffer_m(self):
        assert Settings().road_buffer_m == 1000

    def test_default_grid_spacing_m(self):
        assert Settings().grid_spacing_m == 5000

    def test_default_min_astronomy_score(self):
        assert Settings().min_astronomy_score == 60

    def test_default_forecast_hours(self):
        assert Settings().forecast_hours == 72

    def test_default_cache_ttl_hours(self):
        assert Settings().cache_ttl_hours == 1

    def test_default_met_norway_rate_limit(self):
        assert Settings().met_norway_rate_limit == 15

    def test_default_otel_enabled(self):
        assert Settings().otel_enabled is True

    def test_default_otel_service_name(self):
        assert Settings().otel_service_name == "stargazer"

    def test_default_otel_endpoint_empty(self):
        assert Settings().otel_exporter_otlp_endpoint == ""

    def test_acceptable_zones_defaults(self):
        expected = ["0", "1a", "1b", "2a", "2b", "3a", "3b"]
        assert Settings().acceptable_zones == expected

    def test_lp_source_url_is_https(self):
        assert Settings().lp_source_url.startswith("https://")

    def test_colorbar_url_is_https(self):
        assert Settings().colorbar_url.startswith("https://")

    def test_osm_source_url_is_https(self):
        assert Settings().osm_source_url.startswith("https://")

    def test_lp_source_url_contains_djlorenz(self):
        assert "djlorenz" in Settings().lp_source_url

    def test_osm_source_url_contains_geofabrik(self):
        assert "geofabrik" in Settings().osm_source_url

    def test_met_norway_user_agent_identifies_project(self):
        ua = Settings().met_norway_user_agent
        assert "stargazer" in ua

    def test_met_norway_rate_limit_within_safe_bounds(self):
        """Rate limit should be positive and within MET Norway guidance."""
        rl = Settings().met_norway_rate_limit
        assert 0 < rl <= 20

    def test_color_tolerance_within_rgb_range(self):
        """Color tolerance should be a sensible fraction of 255."""
        ct = Settings().color_tolerance
        assert 0 < ct <= 50

    def test_grid_spacing_reasonable_for_scotland(self):
        """Grid spacing should be between 1km and 50km."""
        gs = Settings().grid_spacing_m
        assert 1000 <= gs <= 50000


class TestSettingsEnvOverrides:
    """Tests that environment variables override defaults."""

    def test_min_astronomy_score_env_override(self):
        with patch.dict(os.environ, {"MIN_ASTRONOMY_SCORE": "75"}):
            s = Settings()
        assert s.min_astronomy_score == 75

    def test_grid_spacing_env_override(self):
        with patch.dict(os.environ, {"GRID_SPACING_M": "10000"}):
            s = Settings()
        assert s.grid_spacing_m == 10000

    def test_forecast_hours_env_override(self):
        with patch.dict(os.environ, {"FORECAST_HOURS": "48"}):
            s = Settings()
        assert s.forecast_hours == 48

    def test_otel_enabled_env_override_false(self):
        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            s = Settings()
        assert s.otel_enabled is False


class TestSettingsNestedConfig:
    """Tests for nested BoundsConfig and EuropeBoundsConfig in Settings."""

    def test_bounds_is_bounds_config_instance(self):
        s = Settings()
        assert isinstance(s.bounds, BoundsConfig)

    def test_europe_bounds_is_europe_bounds_config_instance(self):
        s = Settings()
        assert isinstance(s.europe_bounds, EuropeBoundsConfig)

    def test_scotland_within_europe(self):
        """Scotland bounds must be fully contained in Europe bounds."""
        s = Settings()
        assert s.bounds.north <= s.europe_bounds.north
        assert s.bounds.south >= s.europe_bounds.south
        assert s.bounds.west >= s.europe_bounds.west
        assert s.bounds.east <= s.europe_bounds.east

    def test_custom_settings_instantiation(self):
        """Settings can be instantiated with custom values."""
        s = Settings(grid_spacing_m=10000, min_astronomy_score=70)
        assert s.grid_spacing_m == 10000
        assert s.min_astronomy_score == 70
