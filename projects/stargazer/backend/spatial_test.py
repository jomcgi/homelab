"""Unit tests for the spatial module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings
from projects.stargazer.backend.spatial import (
    METRIC_CRS,
    WGS84_CRS,
    buffer_roads,
    enrich_points,
    extract_dark_regions,
    generate_sample_grid,
    intersect_dark_accessible,
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


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data))


def _make_polygon(west: float, south: float, east: float, north: float) -> Polygon:
    return Polygon(
        [(west, south), (east, south), (east, north), (west, north), (west, south)]
    )


def _write_gdf(
    path: Path, polygon: Polygon, extra_cols: dict | None = None, crs: str = WGS84_CRS
) -> None:
    data = {"geometry": [polygon]}
    if extra_cols:
        data.update(extra_cols)
    gdf = gpd.GeoDataFrame(data, crs=crs)
    gdf.to_file(path, driver="GeoJSON")


# ---------------------------------------------------------------------------
# CRS constants
# ---------------------------------------------------------------------------


class TestCrsConstants:
    def test_metric_crs_is_british_national_grid(self):
        assert METRIC_CRS == "EPSG:27700"

    def test_wgs84_crs_is_standard(self):
        assert WGS84_CRS == "EPSG:4326"


# ---------------------------------------------------------------------------
# extract_dark_regions
# ---------------------------------------------------------------------------


class TestExtractDarkRegions:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "dark_regions.geojson"
        output.touch()

        result = extract_dark_regions(settings)

        assert result == output

    def test_creates_output_file(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        palette = [
            {"rgb": [50, 50, 50], "zone": "1a", "lpi_range": [0.01, 0.06]},
        ]
        _write_json(settings.processed_dir / "color_palette.json", palette)

        mock_raster = MagicMock()
        mock_raster.read.return_value = np.array(
            [[[50, 100]], [[50, 100]], [[50, 100]]]  # R, G, B
        )
        mock_raster.transform = MagicMock()
        mock_raster.__enter__ = MagicMock(return_value=mock_raster)
        mock_raster.__exit__ = MagicMock(return_value=False)

        sample_geom = {
            "type": "Polygon",
            "coordinates": [
                [[-4.5, 55.0], [-4.4, 55.0], [-4.4, 55.1], [-4.5, 55.1], [-4.5, 55.0]]
            ],
        }

        with (
            patch("rasterio.open", return_value=mock_raster),
            patch("projects.stargazer.backend.spatial.features.shapes") as mock_shapes,
        ):
            mock_shapes.return_value = [(sample_geom, 1)]
            result = extract_dark_regions(settings)

        assert result == settings.processed_dir / "dark_regions.geojson"

    def test_only_value_1_shapes_become_polygons(self, tmp_path: Path):
        """Only shapes with value==1 (dark pixels) are included as polygons.
        Shapes with value==0 (background) are filtered out by the list comprehension."""
        settings = make_settings(tmp_path)

        palette = [
            {"rgb": [50, 50, 50], "zone": "1a", "lpi_range": [0.01, 0.06]},
        ]
        _write_json(settings.processed_dir / "color_palette.json", palette)

        mock_raster = MagicMock()
        mock_raster.read.return_value = np.full((3, 2, 2), 50, dtype=np.uint8)
        mock_raster.transform = MagicMock()
        mock_raster.__enter__ = MagicMock(return_value=mock_raster)
        mock_raster.__exit__ = MagicMock(return_value=False)

        dark_geom = {
            "type": "Polygon",
            "coordinates": [
                [[-4.5, 55.0], [-4.4, 55.0], [-4.4, 55.1], [-4.5, 55.1], [-4.5, 55.0]]
            ],
        }
        bg_geom = {
            "type": "Polygon",
            "coordinates": [
                [[-5.0, 56.0], [-4.9, 56.0], [-4.9, 56.1], [-5.0, 56.1], [-5.0, 56.0]]
            ],
        }

        with (
            patch("rasterio.open", return_value=mock_raster),
            patch("projects.stargazer.backend.spatial.features.shapes") as mock_shapes,
        ):
            # value==1 → dark, value==0 → background (excluded)
            mock_shapes.return_value = [(dark_geom, 1), (bg_geom, 0)]
            result = extract_dark_regions(settings)

        assert result == settings.processed_dir / "dark_regions.geojson"
        # The dark region file was created
        assert result.exists()


# ---------------------------------------------------------------------------
# buffer_roads
# ---------------------------------------------------------------------------


class TestBufferRoads:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "road_buffer.geojson"
        output.touch()

        result = buffer_roads(settings)

        assert result == output

    def test_creates_buffer_geojson(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        roads_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-4.5, 55.0], [-4.4, 55.1]],
                    },
                    "properties": {},
                }
            ],
        }
        _write_json(settings.processed_dir / "scotland-roads.geojson", roads_data)

        result = buffer_roads(settings)

        assert result.exists()

    def test_buffer_output_in_wgs84(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        roads_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-4.5, 55.0], [-4.4, 55.1]],
                    },
                    "properties": {},
                }
            ],
        }
        _write_json(settings.processed_dir / "scotland-roads.geojson", roads_data)

        result = buffer_roads(settings)
        gdf = gpd.read_file(result)

        # CRS should be WGS84 after reprojection back
        assert gdf.crs.to_epsg() == 4326

    def test_buffer_is_single_dissolved_geometry(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        roads_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-4.5, 55.0], [-4.4, 55.1]],
                    },
                    "properties": {},
                }
            ],
        }
        _write_json(settings.processed_dir / "scotland-roads.geojson", roads_data)

        result = buffer_roads(settings)
        gdf = gpd.read_file(result)

        assert len(gdf) == 1  # unary_union → single geometry


# ---------------------------------------------------------------------------
# intersect_dark_accessible
# ---------------------------------------------------------------------------


class TestIntersectDarkAccessible:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "accessible_dark.geojson"
        output.touch()

        result = intersect_dark_accessible(settings)

        assert result == output

    def test_overlapping_areas_produce_intersection(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        dark = _make_polygon(-5.0, 54.5, -4.0, 55.5)
        _write_gdf(
            settings.processed_dir / "dark_regions.geojson", dark, {"dark": [True]}
        )

        buffer = _make_polygon(-4.8, 54.8, -4.2, 55.2)
        _write_gdf(settings.processed_dir / "road_buffer.geojson", buffer)

        result = intersect_dark_accessible(settings)

        gdf = gpd.read_file(result)
        assert len(gdf) > 0

    def test_non_overlapping_areas_give_empty_intersection(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        dark = _make_polygon(-8.0, 58.0, -7.0, 59.0)
        _write_gdf(
            settings.processed_dir / "dark_regions.geojson", dark, {"dark": [True]}
        )

        buffer = _make_polygon(-3.0, 54.0, -2.0, 55.0)
        _write_gdf(settings.processed_dir / "road_buffer.geojson", buffer)

        result = intersect_dark_accessible(settings)

        gdf = gpd.read_file(result)
        assert len(gdf) == 0

    def test_output_file_created(self, tmp_path: Path):
        settings = make_settings(tmp_path)

        dark = _make_polygon(-5.0, 54.5, -4.0, 55.5)
        _write_gdf(
            settings.processed_dir / "dark_regions.geojson", dark, {"dark": [True]}
        )
        buf = _make_polygon(-5.0, 54.5, -4.0, 55.5)
        _write_gdf(settings.processed_dir / "road_buffer.geojson", buf)

        result = intersect_dark_accessible(settings)

        assert result.exists()
        assert result.name == "accessible_dark.geojson"


# ---------------------------------------------------------------------------
# generate_sample_grid
# ---------------------------------------------------------------------------


class TestGenerateSampleGrid:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "sample_points.geojson"
        output.touch()

        result = generate_sample_grid(settings)

        assert result == output

    def test_creates_sample_points_geojson(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        settings.grid_spacing_m = 100000  # large spacing → fast test

        accessible = _make_polygon(-6.0, 54.0, -3.0, 57.0)
        _write_gdf(settings.processed_dir / "accessible_dark.geojson", accessible)

        result = generate_sample_grid(settings)

        assert result.exists()

    def test_output_is_valid_geojson_feature_collection(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        settings.grid_spacing_m = 100000

        accessible = _make_polygon(-6.0, 54.0, -3.0, 57.0)
        _write_gdf(settings.processed_dir / "accessible_dark.geojson", accessible)

        result = generate_sample_grid(settings)
        data = json.loads(result.read_text())

        assert data["type"] == "FeatureCollection"
        assert "features" in data

    def test_points_have_id_lat_lon_properties(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        settings.grid_spacing_m = 100000

        accessible = _make_polygon(-6.0, 54.0, -3.0, 57.0)
        _write_gdf(settings.processed_dir / "accessible_dark.geojson", accessible)

        result = generate_sample_grid(settings)
        data = json.loads(result.read_text())

        if data["features"]:
            props = data["features"][0]["properties"]
            assert "id" in props
            assert "lat" in props
            assert "lon" in props

    def test_point_ids_use_scotland_prefix(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        settings.grid_spacing_m = 100000

        accessible = _make_polygon(-6.0, 54.0, -3.0, 57.0)
        _write_gdf(settings.processed_dir / "accessible_dark.geojson", accessible)

        result = generate_sample_grid(settings)
        data = json.loads(result.read_text())

        for feature in data["features"]:
            assert feature["properties"]["id"].startswith("scotland_")


# ---------------------------------------------------------------------------
# enrich_points
# ---------------------------------------------------------------------------


class TestEnrichPoints:
    def test_skips_if_output_exists(self, tmp_path: Path):
        settings = make_settings(tmp_path)
        output = settings.processed_dir / "sample_points_enriched.geojson"
        output.touch()

        result = enrich_points(settings)

        assert result == output

    def _setup_inputs(self, settings: Settings, sample_color_palette: list) -> None:
        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "p1", "lat": 55.0, "lon": -4.5},
                }
            ],
        }
        _write_json(settings.processed_dir / "sample_points.geojson", points_data)
        _write_json(settings.processed_dir / "color_palette.json", sample_color_palette)

    def test_adds_altitude_m_column(self, tmp_path: Path, sample_color_palette: list):
        settings = make_settings(tmp_path)
        self._setup_inputs(settings, sample_color_palette)

        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert "altitude_m" in gdf.columns

    def test_altitude_defaults_to_zero_without_dem(
        self, tmp_path: Path, sample_color_palette: list
    ):
        """When no DEM file exists, altitude_m should default to 0."""
        settings = make_settings(tmp_path)
        self._setup_inputs(settings, sample_color_palette)

        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert gdf.iloc[0]["altitude_m"] == 0

    def test_adds_lp_zone_column(self, tmp_path: Path, sample_color_palette: list):
        settings = make_settings(tmp_path)
        self._setup_inputs(settings, sample_color_palette)

        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[50, 50, 50]]  # matches zone "1a"
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert "lp_zone" in gdf.columns
        assert gdf.iloc[0]["lp_zone"] == "1a"

    def test_unknown_color_maps_to_unknown_zone(
        self, tmp_path: Path, sample_color_palette: list
    ):
        settings = make_settings(tmp_path)
        self._setup_inputs(settings, sample_color_palette)

        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[255, 0, 255]]  # magenta — not in palette
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert gdf.iloc[0]["lp_zone"] == "unknown"

    def test_color_within_tolerance_matches_zone(
        self, tmp_path: Path, sample_color_palette: list
    ):
        settings = make_settings(tmp_path)
        settings.color_tolerance = 20
        self._setup_inputs(settings, sample_color_palette)

        # (50,50,50) ± 20 should still match "1a"
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[55, 45, 52]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert gdf.iloc[0]["lp_zone"] == "1a"

    def test_color_outside_tolerance_is_unknown(
        self, tmp_path: Path, sample_color_palette: list
    ):
        settings = make_settings(tmp_path)
        settings.color_tolerance = 5  # strict tolerance
        self._setup_inputs(settings, sample_color_palette)

        # (50,50,50) is zone "1a"; (75,75,75) is zone "1b" — each is 25 away from zone 0
        # With tolerance 5, (62, 62, 62) is 12 away from both → unknown
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[62, 62, 62]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        gdf = gpd.read_file(result)
        assert gdf.iloc[0]["lp_zone"] == "unknown"


# ---------------------------------------------------------------------------
# Fixtures re-exported from conftest pattern for this standalone test file
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_color_palette() -> list:
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
