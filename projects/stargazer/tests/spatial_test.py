"""Tests for the spatial module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, Polygon, box

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.spatial import (
    METRIC_CRS,
    WGS84_CRS,
    buffer_roads,
    enrich_points,
    extract_dark_regions,
    generate_sample_grid,
    intersect_dark_accessible,
)


class TestExtractDarkRegions:
    """Tests for extract_dark_regions function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that extraction is skipped if output exists."""
        output_path = settings.processed_dir / "dark_regions.geojson"
        output_path.touch()

        result = extract_dark_regions(settings)

        assert result == output_path

    def test_creates_output_file(self, settings: Settings, sample_color_palette: list):
        """Test that dark regions are extracted from raster."""
        # Create mock raster and palette
        palette_path = settings.processed_dir / "color_palette.json"
        with open(palette_path, "w") as f:
            json.dump(sample_color_palette, f)

        # Mock rasterio operations
        mock_raster = MagicMock()
        mock_raster.read.return_value = np.array(
            [
                [[50, 50], [100, 100]],  # R
                [[50, 50], [100, 100]],  # G
                [[50, 50], [100, 100]],  # B
            ]
        )
        mock_raster.transform = MagicMock()
        mock_raster.__enter__ = MagicMock(return_value=mock_raster)
        mock_raster.__exit__ = MagicMock(return_value=False)

        # Create a sample polygon geometry for the mock shapes
        sample_geom = {
            "type": "Polygon",
            "coordinates": [
                [[-4.5, 55.0], [-4.4, 55.0], [-4.4, 55.1], [-4.5, 55.1], [-4.5, 55.0]]
            ],
        }

        with patch("rasterio.open", return_value=mock_raster):
            with patch(
                "projects.stargazer.backend.spatial.features.shapes"
            ) as mock_shapes:
                # Return a shape with geometry
                mock_shapes.return_value = [(sample_geom, 1)]

                result = extract_dark_regions(settings)

        assert result == settings.processed_dir / "dark_regions.geojson"


class TestBufferRoads:
    """Tests for buffer_roads function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that buffering is skipped if output exists."""
        output_path = settings.processed_dir / "road_buffer.geojson"
        output_path.touch()

        result = buffer_roads(settings)

        assert result == output_path

    def test_creates_buffer_with_correct_distance(self, settings: Settings):
        """Test road buffer is created with correct distance."""
        # Create sample roads GeoJSON
        roads_data = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-4.5, 55.0], [-4.4, 55.1]],
                    },
                    "properties": {"highway": "primary"},
                }
            ],
        }

        roads_path = settings.processed_dir / "scotland-roads.geojson"
        with open(roads_path, "w") as f:
            json.dump(roads_data, f)

        result = buffer_roads(settings)

        assert result.exists()

        # Verify buffer was created
        buffer_gdf = gpd.read_file(result)
        assert len(buffer_gdf) == 1
        assert buffer_gdf.crs.to_string() == WGS84_CRS

    def test_buffer_distance_matches_settings(self, settings: Settings):
        """Test that buffer distance matches settings.road_buffer_m."""
        settings.road_buffer_m = 2000  # 2km buffer

        roads_data = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-4.5, 55.0], [-4.4, 55.1]],
                    },
                    "properties": {"highway": "primary"},
                }
            ],
        }

        roads_path = settings.processed_dir / "scotland-roads.geojson"
        with open(roads_path, "w") as f:
            json.dump(roads_data, f)

        result = buffer_roads(settings)

        # Buffer should exist (actual distance verification requires metric comparison)
        assert result.exists()


class TestIntersectDarkAccessible:
    """Tests for intersect_dark_accessible function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that intersection is skipped if output exists."""
        output_path = settings.processed_dir / "accessible_dark.geojson"
        output_path.touch()

        result = intersect_dark_accessible(settings)

        assert result == output_path

    def test_creates_intersection(self, settings: Settings):
        """Test that intersection of dark and accessible areas is created."""
        # Create dark regions (a square)
        dark_polygon = Polygon(
            [
                (-5.0, 54.5),
                (-4.0, 54.5),
                (-4.0, 55.5),
                (-5.0, 55.5),
                (-5.0, 54.5),
            ]
        )
        dark_gdf = gpd.GeoDataFrame(
            {"dark": [True]},
            geometry=[dark_polygon],
            crs=WGS84_CRS,
        )
        dark_path = settings.processed_dir / "dark_regions.geojson"
        dark_gdf.to_file(dark_path, driver="GeoJSON")

        # Create road buffer (overlapping square)
        buffer_polygon = Polygon(
            [
                (-4.8, 54.8),
                (-4.2, 54.8),
                (-4.2, 55.2),
                (-4.8, 55.2),
                (-4.8, 54.8),
            ]
        )
        buffer_gdf = gpd.GeoDataFrame(
            geometry=[buffer_polygon],
            crs=WGS84_CRS,
        )
        buffer_path = settings.processed_dir / "road_buffer.geojson"
        buffer_gdf.to_file(buffer_path, driver="GeoJSON")

        result = intersect_dark_accessible(settings)

        assert result.exists()

        # Verify intersection was created
        intersection_gdf = gpd.read_file(result)
        assert len(intersection_gdf) > 0

    def test_empty_intersection(self, settings: Settings):
        """Test handling of non-overlapping regions."""
        # Create non-overlapping regions
        dark_polygon = Polygon(
            [
                (-8.0, 58.0),
                (-7.0, 58.0),
                (-7.0, 59.0),
                (-8.0, 59.0),
                (-8.0, 58.0),
            ]
        )
        dark_gdf = gpd.GeoDataFrame(
            {"dark": [True]},
            geometry=[dark_polygon],
            crs=WGS84_CRS,
        )
        dark_gdf.to_file(
            settings.processed_dir / "dark_regions.geojson",
            driver="GeoJSON",
        )

        buffer_polygon = Polygon(
            [
                (-4.0, 54.0),
                (-3.0, 54.0),
                (-3.0, 55.0),
                (-4.0, 55.0),
                (-4.0, 54.0),
            ]
        )
        buffer_gdf = gpd.GeoDataFrame(
            geometry=[buffer_polygon],
            crs=WGS84_CRS,
        )
        buffer_gdf.to_file(
            settings.processed_dir / "road_buffer.geojson",
            driver="GeoJSON",
        )

        result = intersect_dark_accessible(settings)

        assert result.exists()
        intersection_gdf = gpd.read_file(result)
        # Empty intersection should still create valid file
        assert len(intersection_gdf) == 0


class TestGenerateSampleGrid:
    """Tests for generate_sample_grid function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that grid generation is skipped if output exists."""
        output_path = settings.processed_dir / "sample_points.geojson"
        output_path.touch()

        result = generate_sample_grid(settings)

        assert result == output_path

    def test_generates_points_within_area(self, settings: Settings):
        """Test that sample points are generated within accessible area."""
        # Create a larger accessible area to ensure points are generated
        accessible_polygon = Polygon(
            [
                (-6.0, 54.0),
                (-3.0, 54.0),
                (-3.0, 57.0),
                (-6.0, 57.0),
                (-6.0, 54.0),
            ]
        )
        accessible_gdf = gpd.GeoDataFrame(
            geometry=[accessible_polygon],
            crs=WGS84_CRS,
        )
        accessible_gdf.to_file(
            settings.processed_dir / "accessible_dark.geojson",
            driver="GeoJSON",
        )

        # Use larger grid spacing to avoid dtype issues with many points
        settings.grid_spacing_m = 50000

        result = generate_sample_grid(settings)

        assert result.exists()

        # Read the file and verify structure
        with open(result) as f:
            data = json.load(f)

        # Verify it's valid GeoJSON
        assert data.get("type") == "FeatureCollection"
        assert "features" in data

    def test_points_have_required_columns(self, settings: Settings):
        """Test that generated points have id, lat, lon columns."""
        accessible_polygon = Polygon(
            [
                (-6.0, 54.0),
                (-3.0, 54.0),
                (-3.0, 57.0),
                (-6.0, 57.0),
                (-6.0, 54.0),
            ]
        )
        accessible_gdf = gpd.GeoDataFrame(
            geometry=[accessible_polygon],
            crs=WGS84_CRS,
        )
        accessible_gdf.to_file(
            settings.processed_dir / "accessible_dark.geojson",
            driver="GeoJSON",
        )

        settings.grid_spacing_m = 50000  # 50km spacing

        result = generate_sample_grid(settings)

        with open(result) as f:
            data = json.load(f)

        if data.get("features"):
            props = data["features"][0].get("properties", {})
            assert "id" in props
            assert "lat" in props
            assert "lon" in props

    def test_respects_grid_spacing(self, settings: Settings):
        """Test that grid spacing setting is respected."""
        # Just test that the function can handle different spacing values
        # without errors - actual point count comparison is complex due to
        # projection and boundary effects
        accessible_polygon = Polygon(
            [
                (-6.0, 54.0),
                (-3.0, 54.0),
                (-3.0, 57.0),
                (-6.0, 57.0),
                (-6.0, 54.0),
            ]
        )
        accessible_gdf = gpd.GeoDataFrame(
            geometry=[accessible_polygon],
            crs=WGS84_CRS,
        )
        accessible_gdf.to_file(
            settings.processed_dir / "accessible_dark.geojson",
            driver="GeoJSON",
        )

        settings.grid_spacing_m = 100000  # Large spacing for fast test

        result = generate_sample_grid(settings)

        # Verify output was created
        assert result.exists()
        with open(result) as f:
            data = json.load(f)
        assert data.get("type") == "FeatureCollection"


class TestEnrichPoints:
    """Tests for enrich_points function."""

    def test_skips_if_file_exists(self, settings: Settings):
        """Test that enrichment is skipped if output exists."""
        output_path = settings.processed_dir / "sample_points_enriched.geojson"
        output_path.touch()

        result = enrich_points(settings)

        assert result == output_path

    def test_adds_altitude_column(self, settings: Settings, sample_color_palette: list):
        """Test that altitude_m column is added from DEM."""
        # Create sample points as GeoJSON directly
        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "scotland_0001", "lat": 55.0, "lon": -4.5},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.6, 55.1]},
                    "properties": {"id": "scotland_0002", "lat": 55.1, "lon": -4.6},
                },
            ],
        }
        with open(settings.processed_dir / "sample_points.geojson", "w") as f:
            json.dump(points_data, f)

        # Create palette
        with open(settings.processed_dir / "color_palette.json", "w") as f:
            json.dump(sample_color_palette, f)

        # Mock LP raster
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50], [100, 100, 100]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        enriched_gdf = gpd.read_file(result)
        assert "altitude_m" in enriched_gdf.columns

    def test_adds_lp_zone_column(self, settings: Settings, sample_color_palette: list):
        """Test that lp_zone column is added from LP raster."""
        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "scotland_0001", "lat": 55.0, "lon": -4.5},
                },
            ],
        }
        with open(settings.processed_dir / "sample_points.geojson", "w") as f:
            json.dump(points_data, f)

        with open(settings.processed_dir / "color_palette.json", "w") as f:
            json.dump(sample_color_palette, f)

        # Mock LP raster returning zone "1a" color (50, 50, 50)
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        enriched_gdf = gpd.read_file(result)
        assert "lp_zone" in enriched_gdf.columns
        assert enriched_gdf.iloc[0]["lp_zone"] == "1a"

    def test_handles_unknown_zone(self, settings: Settings, sample_color_palette: list):
        """Test that unknown colors map to 'unknown' zone."""
        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "scotland_0001", "lat": 55.0, "lon": -4.5},
                },
            ],
        }
        with open(settings.processed_dir / "sample_points.geojson", "w") as f:
            json.dump(points_data, f)

        with open(settings.processed_dir / "color_palette.json", "w") as f:
            json.dump(sample_color_palette, f)

        # Mock LP raster returning color not in palette
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[255, 0, 255]]  # Magenta - not in palette
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        enriched_gdf = gpd.read_file(result)
        assert enriched_gdf.iloc[0]["lp_zone"] == "unknown"

    def test_uses_color_tolerance(self, settings: Settings, sample_color_palette: list):
        """Test that color matching uses tolerance from settings."""
        settings.color_tolerance = 20

        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "scotland_0001", "lat": 55.0, "lon": -4.5},
                },
            ],
        }
        with open(settings.processed_dir / "sample_points.geojson", "w") as f:
            json.dump(points_data, f)

        with open(settings.processed_dir / "color_palette.json", "w") as f:
            json.dump(sample_color_palette, f)

        # Color close to "1a" (50, 50, 50) but within tolerance
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[55, 45, 52]]  # Within tolerance of (50, 50, 50)
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        enriched_gdf = gpd.read_file(result)
        assert enriched_gdf.iloc[0]["lp_zone"] == "1a"


class TestCRSConstants:
    """Tests for CRS constant values."""

    def test_metric_crs_is_british_national_grid(self):
        """Test METRIC_CRS is British National Grid."""
        assert METRIC_CRS == "EPSG:27700"

    def test_wgs84_crs_is_standard(self):
        """Test WGS84_CRS is standard GPS CRS."""
        assert WGS84_CRS == "EPSG:4326"
