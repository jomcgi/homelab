"""Tests for the preprocessing module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.preprocessing import (
    ROAD_HIGHWAY_TYPES,
    clip_dem,
    extract_palette,
    extract_roads,
    georeference_raster,
)


class TestGeoreferenceRaster:
    """Tests for georeference_raster function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that georeferencing is skipped if output exists."""
        output_path = settings.processed_dir / "scotland_lp_2024.tif"
        output_path.touch()

        result = georeference_raster(settings)

        assert result == output_path

    def test_calls_gdal_translate(self, settings: Settings):
        """Test that gdal_translate is called with correct arguments."""
        # Create input PNG
        input_png = settings.raw_dir / "Europe2024.png"
        input_png.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            georeference_raster(settings)

        # Verify gdal_translate was called
        calls = mock_run.call_args_list
        assert len(calls) >= 1

        # First call should be gdal_translate
        first_call_args = calls[0][0][0]
        assert first_call_args[0] == "gdal_translate"
        assert "-a_srs" in first_call_args
        assert "EPSG:4326" in first_call_args
        assert "-expand" in first_call_args
        assert "rgb" in first_call_args

    def test_calls_gdalwarp_for_clipping(self, settings: Settings):
        """Test that gdalwarp is called to clip to Scotland bounds."""
        input_png = settings.raw_dir / "Europe2024.png"
        input_png.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            georeference_raster(settings)

        # Verify gdalwarp was called
        calls = mock_run.call_args_list
        assert len(calls) >= 2

        # Second call should be gdalwarp
        second_call_args = calls[1][0][0]
        assert second_call_args[0] == "gdalwarp"
        assert "-te" in second_call_args

    def test_uses_correct_bounds(self, settings: Settings):
        """Test that correct bounds are used for georeferencing."""
        input_png = settings.raw_dir / "Europe2024.png"
        input_png.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            georeference_raster(settings)

        # Check Europe bounds in gdal_translate call
        first_call_args = mock_run.call_args_list[0][0][0]
        assert str(settings.europe_bounds.west) in first_call_args
        assert str(settings.europe_bounds.north) in first_call_args
        assert str(settings.europe_bounds.east) in first_call_args
        assert str(settings.europe_bounds.south) in first_call_args

        # Check Scotland bounds in gdalwarp call
        second_call_args = mock_run.call_args_list[1][0][0]
        assert str(settings.bounds.west) in second_call_args
        assert str(settings.bounds.south) in second_call_args
        assert str(settings.bounds.east) in second_call_args
        assert str(settings.bounds.north) in second_call_args


class TestExtractPalette:
    """Tests for extract_palette function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that extraction is skipped if output exists."""
        output_path = settings.processed_dir / "color_palette.json"
        output_path.touch()

        result = extract_palette(settings)

        assert result == output_path

    def test_extracts_colors_from_image(self, settings: Settings):
        """Test that colors are extracted from colorbar image."""
        # Create a test colorbar image (gradient)
        colorbar_path = settings.raw_dir / "colorbar.png"
        img = Image.new("RGB", (50, 180), color="black")

        # Add some color bands for zones
        for i in range(9):
            y_start = i * 20
            y_end = (i + 1) * 20
            gray = i * 25
            for y in range(y_start, y_end):
                for x in range(50):
                    img.putpixel((x, y), (gray, gray, gray))

        img.save(colorbar_path)

        result = extract_palette(settings)

        assert result.exists()

        with open(result) as f:
            palette = json.load(f)

        # Should have 9 zones
        assert len(palette) == 9

        # Each entry should have required fields
        for entry in palette:
            assert "rgb" in entry
            assert "zone" in entry
            assert "lpi_range" in entry
            assert len(entry["rgb"]) == 3

    def test_zones_have_correct_order(self, settings: Settings):
        """Test that zones are in correct order from darkest to brightest."""
        colorbar_path = settings.raw_dir / "colorbar.png"
        img = Image.new("RGB", (50, 180), color="black")
        img.save(colorbar_path)

        result = extract_palette(settings)

        with open(result) as f:
            palette = json.load(f)

        zones = [entry["zone"] for entry in palette]
        expected_zones = ["0", "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"]
        assert zones == expected_zones


class TestExtractRoads:
    """Tests for extract_roads function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that extraction is skipped if output exists."""
        output_path = settings.processed_dir / "scotland-roads.geojson"
        output_path.touch()

        result = extract_roads(settings)

        assert result == output_path

    def test_road_highway_types_include_expected_types(self):
        """Test that ROAD_HIGHWAY_TYPES includes expected road types."""
        expected_types = [
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "track",
        ]
        for road_type in expected_types:
            assert road_type in ROAD_HIGHWAY_TYPES

    def test_road_highway_types_exclude_paths(self):
        """Test that ROAD_HIGHWAY_TYPES excludes pedestrian paths."""
        excluded_types = ["footway", "path", "cycleway", "service", "bridleway"]
        for road_type in excluded_types:
            assert road_type not in ROAD_HIGHWAY_TYPES

    def test_calls_ogr2ogr_for_conversion(self, settings: Settings):
        """Test that ogr2ogr is called to convert to GeoJSON."""
        input_pbf = settings.raw_dir / "scotland-latest.osm.pbf"
        input_pbf.touch()

        with patch("osmium.BackReferenceWriter") as mock_writer:
            mock_writer_instance = MagicMock()
            mock_writer.return_value = mock_writer_instance
            mock_writer_instance.__enter__ = MagicMock()
            mock_writer_instance.__exit__ = MagicMock(return_value=False)

            with patch("osmium.FileProcessor", return_value=[]):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)

                    extract_roads(settings)

        # Verify ogr2ogr was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ogr2ogr"
        assert "-f" in call_args
        assert "GeoJSON" in call_args


class TestClipDem:
    """Tests for clip_dem function."""

    def test_returns_placeholder_path(self, settings: Settings):
        """Test that clip_dem returns placeholder path (not implemented)."""
        result = clip_dem(settings)

        assert result == settings.processed_dir / "scotland-dem.tif"

    def test_logs_warning(self, settings: Settings):
        """Test that clip_dem logs a warning about not being implemented."""
        with patch("projects.stargazer.backend.preprocessing.logger") as mock_logger:
            clip_dem(settings)

        mock_logger.warning.assert_called_once()
        assert "not yet implemented" in mock_logger.warning.call_args[0][0].lower()


class TestBoundsConfig:
    """Tests for bounds configuration usage in preprocessing."""

    def test_scotland_bounds_default_values(self, settings: Settings):
        """Test Scotland bounds have correct default values."""
        assert settings.bounds.north == 60.86  # Shetland
        assert settings.bounds.south == 54.63  # Scottish Borders
        assert settings.bounds.west == -8.65  # Outer Hebrides
        assert settings.bounds.east == -0.76  # Aberdeenshire coast

    def test_europe_bounds_default_values(self, settings: Settings):
        """Test Europe bounds have correct default values."""
        assert settings.europe_bounds.north == 75.0
        assert settings.europe_bounds.south == 34.0
        assert settings.europe_bounds.west == -32.0
        assert settings.europe_bounds.east == 70.0

    def test_scotland_within_europe_bounds(self, settings: Settings):
        """Test that Scotland bounds are within Europe bounds."""
        assert settings.bounds.north <= settings.europe_bounds.north
        assert settings.bounds.south >= settings.europe_bounds.south
        assert settings.bounds.west >= settings.europe_bounds.west
        assert settings.bounds.east <= settings.europe_bounds.east
