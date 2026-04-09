"""Unit tests for the preprocessing module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings
from projects.stargazer.backend.preprocessing import (
    ROAD_HIGHWAY_TYPES,
    clip_dem,
    extract_palette,
    extract_roads,
    georeference_raster,
)


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        data_dir=tmp_path,
        bounds=BoundsConfig(),
        europe_bounds=EuropeBoundsConfig(),
        otel_enabled=False,
    )
    for subdir in ("raw", "processed", "cache", "output"):
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
    return settings


# ---------------------------------------------------------------------------
# ROAD_HIGHWAY_TYPES constant
# ---------------------------------------------------------------------------


class TestRoadHighwayTypes:
    def test_is_frozen_set(self):
        assert isinstance(ROAD_HIGHWAY_TYPES, frozenset)

    def test_includes_motorway(self):
        assert "motorway" in ROAD_HIGHWAY_TYPES

    def test_includes_trunk(self):
        assert "trunk" in ROAD_HIGHWAY_TYPES

    def test_includes_primary(self):
        assert "primary" in ROAD_HIGHWAY_TYPES

    def test_includes_secondary(self):
        assert "secondary" in ROAD_HIGHWAY_TYPES

    def test_includes_tertiary(self):
        assert "tertiary" in ROAD_HIGHWAY_TYPES

    def test_includes_unclassified(self):
        assert "unclassified" in ROAD_HIGHWAY_TYPES

    def test_includes_residential(self):
        assert "residential" in ROAD_HIGHWAY_TYPES

    def test_includes_track(self):
        assert "track" in ROAD_HIGHWAY_TYPES

    def test_excludes_footway(self):
        assert "footway" not in ROAD_HIGHWAY_TYPES

    def test_excludes_cycleway(self):
        assert "cycleway" not in ROAD_HIGHWAY_TYPES

    def test_excludes_path(self):
        assert "path" not in ROAD_HIGHWAY_TYPES

    def test_excludes_service(self):
        assert "service" not in ROAD_HIGHWAY_TYPES

    def test_excludes_bridleway(self):
        assert "bridleway" not in ROAD_HIGHWAY_TYPES


# ---------------------------------------------------------------------------
# georeference_raster
# ---------------------------------------------------------------------------


class TestGeoreferenceRaster:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "scotland_lp_2024.tif"
        output.touch()

        result = georeference_raster(settings)

        assert result == output

    def test_invokes_gdal_translate(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        first_cmd = mock_run.call_args_list[0][0][0]
        assert first_cmd[0] == "gdal_translate"

    def test_invokes_gdalwarp(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        second_cmd = mock_run.call_args_list[1][0][0]
        assert second_cmd[0] == "gdalwarp"

    def test_gdal_translate_sets_epsg4326(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        cmd = mock_run.call_args_list[0][0][0]
        assert "EPSG:4326" in cmd

    def test_gdal_translate_expands_rgb(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        cmd = mock_run.call_args_list[0][0][0]
        assert "-expand" in cmd
        assert "rgb" in cmd

    def test_europe_bounds_passed_to_gdal_translate(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        cmd = mock_run.call_args_list[0][0][0]
        assert str(settings.europe_bounds.west) in cmd
        assert str(settings.europe_bounds.north) in cmd
        assert str(settings.europe_bounds.east) in cmd
        assert str(settings.europe_bounds.south) in cmd

    def test_scotland_bounds_passed_to_gdalwarp(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        cmd = mock_run.call_args_list[1][0][0]
        assert str(settings.bounds.west) in cmd
        assert str(settings.bounds.south) in cmd
        assert str(settings.bounds.east) in cmd
        assert str(settings.bounds.north) in cmd

    def test_check_true_passed_to_subprocess_run(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            georeference_raster(settings)

        for call in mock_run.call_args_list:
            assert call.kwargs.get("check") is True

    def test_returns_scotland_tif_path(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "Europe2024.png").touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = georeference_raster(settings)

        assert result == settings.processed_dir / "scotland_lp_2024.tif"


# ---------------------------------------------------------------------------
# extract_palette
# ---------------------------------------------------------------------------


def _make_colorbar(path: Path, mode: str = "RGB") -> None:
    """Create a minimal valid colorbar image with 9 distinct gray bands."""
    img = Image.new(mode, (30, 180), color=(0, 0, 0, 255) if mode == "RGBA" else (0, 0, 0))
    for i in range(9):
        gray = i * 25
        rgba = (gray, gray, gray, 255) if mode == "RGBA" else (gray, gray, gray)
        for y in range(i * 20, (i + 1) * 20):
            for x in range(30):
                img.putpixel((x, y), rgba)
    img.save(path)


class TestExtractPalette:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "color_palette.json"
        output.touch()

        result = extract_palette(settings)

        assert result == output

    def test_creates_palette_json(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        result = extract_palette(settings)

        assert result.exists()
        assert result.suffix == ".json"

    def test_palette_has_nine_entries(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        result = extract_palette(settings)
        palette = json.loads(result.read_text())

        assert len(palette) == 9

    def test_each_entry_has_rgb(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        palette = json.loads(extract_palette(settings).read_text())

        for entry in palette:
            assert "rgb" in entry
            assert len(entry["rgb"]) == 3

    def test_each_entry_has_zone(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        palette = json.loads(extract_palette(settings).read_text())

        for entry in palette:
            assert "zone" in entry

    def test_each_entry_has_lpi_range(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        palette = json.loads(extract_palette(settings).read_text())

        for entry in palette:
            assert "lpi_range" in entry

    def test_zones_in_expected_order(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        palette = json.loads(extract_palette(settings).read_text())
        zones = [e["zone"] for e in palette]

        assert zones == ["0", "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b"]

    def test_rgba_colorbar_works(self, tmp_path: Path):
        """RGBA images should be handled via [:3] slice — no crash."""
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png", mode="RGBA")

        result = extract_palette(settings)
        palette = json.loads(result.read_text())

        assert len(palette) == 9
        for entry in palette:
            assert len(entry["rgb"]) == 3

    def test_rgb_values_are_integers(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        _make_colorbar(settings.raw_dir / "colorbar.png")

        palette = json.loads(extract_palette(settings).read_text())

        for entry in palette:
            for val in entry["rgb"]:
                assert isinstance(val, int)
                assert 0 <= val <= 255


# ---------------------------------------------------------------------------
# extract_roads
# ---------------------------------------------------------------------------


class TestExtractRoads:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "scotland-roads.geojson"
        output.touch()

        result = extract_roads(settings)

        assert result == output

    def test_invokes_ogr2ogr(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        with patch("osmium.BackReferenceWriter") as mock_writer, \
             patch("osmium.FileProcessor", return_value=[]), \
             patch("subprocess.run") as mock_run:

            mock_writer_inst = MagicMock()
            mock_writer.return_value = mock_writer_inst
            mock_writer_inst.__enter__ = MagicMock()
            mock_writer_inst.__exit__ = MagicMock(return_value=False)
            mock_run.return_value = MagicMock(returncode=0)

            extract_roads(settings)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ogr2ogr"

    def test_ogr2ogr_outputs_geojson(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        with patch("osmium.BackReferenceWriter") as mock_writer, \
             patch("osmium.FileProcessor", return_value=[]), \
             patch("subprocess.run") as mock_run:

            mock_writer_inst = MagicMock()
            mock_writer.return_value = mock_writer_inst
            mock_writer_inst.__enter__ = MagicMock()
            mock_writer_inst.__exit__ = MagicMock(return_value=False)
            mock_run.return_value = MagicMock(returncode=0)

            extract_roads(settings)

        cmd = mock_run.call_args[0][0]
        assert "GeoJSON" in cmd

    def test_returns_geojson_path(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        with patch("osmium.BackReferenceWriter") as mock_writer, \
             patch("osmium.FileProcessor", return_value=[]), \
             patch("subprocess.run") as mock_run:

            mock_writer_inst = MagicMock()
            mock_writer.return_value = mock_writer_inst
            mock_writer_inst.__enter__ = MagicMock()
            mock_writer_inst.__exit__ = MagicMock(return_value=False)
            mock_run.return_value = MagicMock(returncode=0)

            result = extract_roads(settings)

        assert result == settings.processed_dir / "scotland-roads.geojson"

    def test_highway_ways_are_filtered_in(self, tmp_path: Path):
        """Ways with matching highway tags are added to the writer."""
        settings = make_settings(tmp_path)
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        added_ways: list = []

        class FakeWay:
            def is_way(self):
                return True

            class tags:
                @staticmethod
                def get(key):
                    return "primary"

        fake_way = FakeWay()

        with patch("osmium.BackReferenceWriter") as mock_writer, \
             patch("osmium.FileProcessor", return_value=[fake_way]), \
             patch("subprocess.run") as mock_run:

            mock_writer_inst = MagicMock()
            mock_writer.return_value = mock_writer_inst
            mock_writer_inst.__enter__ = MagicMock()
            mock_writer_inst.__exit__ = MagicMock(return_value=False)
            mock_run.return_value = MagicMock(returncode=0)

            extract_roads(settings)

        mock_writer_inst.add.assert_called_once_with(fake_way)

    def test_non_highway_ways_excluded(self, tmp_path: Path):
        """Ways with non-road highway types are excluded."""
        settings = make_settings(tmp_path)
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        class FootpathWay:
            def is_way(self):
                return True

            class tags:
                @staticmethod
                def get(key):
                    return "footway"

        footpath = FootpathWay()

        with patch("osmium.BackReferenceWriter") as mock_writer, \
             patch("osmium.FileProcessor", return_value=[footpath]), \
             patch("subprocess.run") as mock_run:

            mock_writer_inst = MagicMock()
            mock_writer.return_value = mock_writer_inst
            mock_writer_inst.__enter__ = MagicMock()
            mock_writer_inst.__exit__ = MagicMock(return_value=False)
            mock_run.return_value = MagicMock(returncode=0)

            extract_roads(settings)

        mock_writer_inst.add.assert_not_called()


# ---------------------------------------------------------------------------
# clip_dem
# ---------------------------------------------------------------------------


class TestClipDem:
    def test_returns_placeholder_path(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        result = clip_dem(settings)
        assert result == settings.processed_dir / "scotland-dem.tif"

    def test_logs_not_implemented_warning(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        with patch("projects.stargazer.backend.preprocessing.logger") as mock_log:
            clip_dem(settings)

        mock_log.warning.assert_called_once()
        assert "not yet implemented" in mock_log.warning.call_args[0][0].lower()

    def test_does_not_create_file(self, tmp_path: Path):
        """clip_dem returns a path but should NOT create the file."""
        settings = make_settings(tmp_path)
        result = clip_dem(settings)
        assert not result.exists()
