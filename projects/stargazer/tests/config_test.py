"""Tests for the config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings


class TestBoundsConfig:
    """Tests for BoundsConfig."""

    def test_default_values(self):
        """Test BoundsConfig has correct Scotland defaults."""
        bounds = BoundsConfig()

        assert bounds.north == 60.86
        assert bounds.south == 54.63
        assert bounds.west == -8.65
        assert bounds.east == -0.76

    def test_env_override(self):
        """Test BoundsConfig can be overridden via environment."""
        with patch.dict(os.environ, {"BOUNDS_NORTH": "61.0"}):
            bounds = BoundsConfig()

        assert bounds.north == 61.0


class TestEuropeBoundsConfig:
    """Tests for EuropeBoundsConfig."""

    def test_default_values(self):
        """Test EuropeBoundsConfig has correct defaults."""
        bounds = EuropeBoundsConfig()

        assert bounds.north == 75.0
        assert bounds.south == 34.0
        assert bounds.west == -32.0
        assert bounds.east == 70.0

    def test_covers_europe(self):
        """Test bounds cover all of Europe."""
        bounds = EuropeBoundsConfig()

        # Western edge should include Portugal/Iceland
        assert bounds.west <= -10.0
        # Eastern edge should include Eastern Europe
        assert bounds.east >= 40.0
        # Northern edge should include Nordic countries
        assert bounds.north >= 70.0
        # Southern edge should include Mediterranean
        assert bounds.south <= 35.0


class TestSettings:
    """Tests for Settings configuration class."""

    def test_default_data_dir(self):
        """Test default data directory is /data."""
        settings = Settings()
        assert settings.data_dir == Path("/data")

    def test_acceptable_zones_default(self):
        """Test default acceptable LP zones."""
        settings = Settings()

        expected_zones = ["0", "1a", "1b", "2a", "2b", "3a", "3b"]
        assert settings.acceptable_zones == expected_zones

    def test_processing_parameters_defaults(self):
        """Test default processing parameters."""
        settings = Settings()

        assert settings.color_tolerance == 15
        assert settings.road_buffer_m == 1000
        assert settings.grid_spacing_m == 5000
        assert settings.min_astronomy_score == 60
        assert settings.forecast_hours == 72

    def test_met_norway_settings(self):
        """Test MET Norway API settings."""
        settings = Settings()

        assert "stargazer" in settings.met_norway_user_agent
        assert settings.met_norway_rate_limit == 15
        assert settings.cache_ttl_hours == 1

    def test_data_source_urls(self):
        """Test data source URLs are valid."""
        settings = Settings()

        assert settings.lp_source_url.startswith("https://")
        assert "djlorenz" in settings.lp_source_url
        assert settings.colorbar_url.startswith("https://")
        assert settings.osm_source_url.startswith("https://")
        assert "geofabrik" in settings.osm_source_url

    def test_otel_settings_defaults(self):
        """Test OpenTelemetry settings defaults."""
        settings = Settings()

        assert settings.otel_enabled is True
        assert settings.otel_service_name == "stargazer"
        assert settings.otel_exporter_otlp_endpoint == ""

    def test_raw_dir_property(self, temp_data_dir: Path):
        """Test raw_dir property returns correct path."""
        settings = Settings(data_dir=temp_data_dir)

        assert settings.raw_dir == temp_data_dir / "raw"

    def test_processed_dir_property(self, temp_data_dir: Path):
        """Test processed_dir property returns correct path."""
        settings = Settings(data_dir=temp_data_dir)

        assert settings.processed_dir == temp_data_dir / "processed"

    def test_cache_dir_property(self, temp_data_dir: Path):
        """Test cache_dir property returns correct path."""
        settings = Settings(data_dir=temp_data_dir)

        assert settings.cache_dir == temp_data_dir / "cache"

    def test_output_dir_property(self, temp_data_dir: Path):
        """Test output_dir property returns correct path."""
        settings = Settings(data_dir=temp_data_dir)

        assert settings.output_dir == temp_data_dir / "output"

    def test_env_override_data_dir(self, tmp_path: Path):
        """Test data_dir can be overridden via environment."""
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            settings = Settings()

        assert settings.data_dir == tmp_path

    def test_env_override_min_astronomy_score(self):
        """Test min_astronomy_score can be overridden via environment."""
        with patch.dict(os.environ, {"MIN_ASTRONOMY_SCORE": "75"}):
            settings = Settings()

        assert settings.min_astronomy_score == 75

    def test_nested_bounds_config(self):
        """Test that nested BoundsConfig is properly initialized."""
        settings = Settings()

        assert isinstance(settings.bounds, BoundsConfig)
        assert isinstance(settings.europe_bounds, EuropeBoundsConfig)

    def test_settings_immutability(self):
        """Test that settings values are properly set."""
        settings = Settings(
            grid_spacing_m=10000,
            min_astronomy_score=70,
        )

        assert settings.grid_spacing_m == 10000
        assert settings.min_astronomy_score == 70


class TestSettingsValidation:
    """Tests for Settings validation."""

    def test_acceptable_zones_are_valid(self):
        """Test that default acceptable zones are valid Bortle zones."""
        settings = Settings()

        valid_zones = {"0", "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"}
        for zone in settings.acceptable_zones:
            assert zone in valid_zones

    def test_rate_limit_is_reasonable(self):
        """Test that rate limit is within MET Norway guidelines."""
        settings = Settings()

        # MET Norway allows up to 20 requests/second for identified clients
        assert settings.met_norway_rate_limit <= 20
        assert settings.met_norway_rate_limit > 0

    def test_color_tolerance_is_reasonable(self):
        """Test that color tolerance is within valid RGB range."""
        settings = Settings()

        # Tolerance should be less than typical color band width
        assert 0 < settings.color_tolerance <= 50

    def test_grid_spacing_is_reasonable(self):
        """Test that grid spacing is reasonable for Scotland."""
        settings = Settings()

        # Should be at least 1km for manageable number of points
        assert settings.grid_spacing_m >= 1000
        # Should be at most 50km to not miss locations
        assert settings.grid_spacing_m <= 50000
