"""Phase 3: Spatial Analysis - identify accessible dark sky locations."""

import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import Point, box

from projects.stargazer.backend.config import Settings

logger = logging.getLogger(__name__)

# British National Grid for metric operations
METRIC_CRS = "EPSG:27700"
WGS84_CRS = "EPSG:4326"


def extract_dark_regions(settings: Settings) -> Path:
    """
    Identify areas with acceptable light pollution levels.

    Reads the georeferenced LP raster and color palette,
    creates polygons for areas matching acceptable zones.
    """
    raster_path = settings.processed_dir / "scotland_lp_2024.tif"
    palette_path = settings.processed_dir / "color_palette.json"
    output_path = settings.processed_dir / "dark_regions.geojson"

    if output_path.exists():
        logger.info(f"Skipping dark region extraction, file exists: {output_path}")
        return output_path

    with open(palette_path) as f:
        palette = json.load(f)

    # Get RGB values for acceptable zones
    acceptable_rgbs = [
        p["rgb"] for p in palette if p["zone"] in settings.acceptable_zones
    ]

    with rasterio.open(raster_path) as src:
        rgb = src.read([1, 2, 3])  # Shape: (3, height, width)
        transform = src.transform

        # Create mask for acceptable zones
        mask = np.zeros(rgb.shape[1:], dtype=np.uint8)
        tolerance = settings.color_tolerance

        for target_rgb in acceptable_rgbs:
            r_match = np.abs(rgb[0] - target_rgb[0]) <= tolerance
            g_match = np.abs(rgb[1] - target_rgb[1]) <= tolerance
            b_match = np.abs(rgb[2] - target_rgb[2]) <= tolerance
            zone_mask = r_match & g_match & b_match
            mask = mask | zone_mask.astype(np.uint8)

        # Vectorize the mask to polygons
        shapes = features.shapes(mask, transform=transform)
        polygons = [
            {"geometry": geom, "properties": {"dark": True}}
            for geom, value in shapes
            if value == 1
        ]

    gdf = gpd.GeoDataFrame.from_features(polygons, crs=WGS84_CRS)
    gdf = gdf.dissolve()  # Merge adjacent polygons

    gdf.to_file(output_path, driver="GeoJSON")
    logger.info(f"Extracted dark regions to {output_path}")
    return output_path


def buffer_roads(settings: Settings) -> Path:
    """
    Create accessibility buffer around road network.

    Reprojects to metric CRS, buffers, then back to WGS84.
    """
    roads_path = settings.processed_dir / "scotland-roads.geojson"
    output_path = settings.processed_dir / "road_buffer.geojson"

    if output_path.exists():
        logger.info(f"Skipping road buffer, file exists: {output_path}")
        return output_path

    roads = gpd.read_file(roads_path)

    # Reproject to metric CRS for accurate buffering
    roads_metric = roads.to_crs(METRIC_CRS)
    buffer = roads_metric.buffer(settings.road_buffer_m)
    # Dissolve all road buffers into a single geometry
    buffer_gdf = gpd.GeoDataFrame(geometry=[buffer.unary_union], crs=METRIC_CRS)

    # Back to WGS84
    buffer_gdf = buffer_gdf.to_crs(WGS84_CRS)
    buffer_gdf.to_file(output_path, driver="GeoJSON")

    logger.info(f"Created {settings.road_buffer_m}m road buffer: {output_path}")
    return output_path


def intersect_dark_accessible(settings: Settings) -> Path:
    """Find areas that are both dark AND accessible (near roads)."""
    dark_path = settings.processed_dir / "dark_regions.geojson"
    buffer_path = settings.processed_dir / "road_buffer.geojson"
    output_path = settings.processed_dir / "accessible_dark.geojson"

    if output_path.exists():
        logger.info(f"Skipping intersection, file exists: {output_path}")
        return output_path

    dark = gpd.read_file(dark_path)
    buffer = gpd.read_file(buffer_path)

    # Geometric intersection
    intersection = gpd.overlay(dark, buffer, how="intersection")
    intersection.to_file(output_path, driver="GeoJSON")

    logger.info(f"Created accessible dark regions: {output_path}")
    return output_path


def generate_sample_grid(settings: Settings) -> Path:
    """
    Generate evenly-spaced sample points within accessible dark areas.

    Uses metric CRS for accurate spacing.
    """
    accessible_path = settings.processed_dir / "accessible_dark.geojson"
    output_path = settings.processed_dir / "sample_points.geojson"

    if output_path.exists():
        logger.info(f"Skipping grid generation, file exists: {output_path}")
        return output_path

    accessible = gpd.read_file(accessible_path)
    accessible_metric = accessible.to_crs(METRIC_CRS)

    # Get bounds and generate grid
    minx, miny, maxx, maxy = accessible_metric.total_bounds
    spacing = settings.grid_spacing_m

    points = []
    x = minx
    while x <= maxx:
        y = miny
        while y <= maxy:
            point = Point(x, y)
            # Only keep points within the accessible dark area
            if accessible_metric.contains(point).any():
                points.append(point)
            y += spacing
        x += spacing

    points_gdf = gpd.GeoDataFrame(geometry=points, crs=METRIC_CRS)
    points_gdf = points_gdf.to_crs(WGS84_CRS)

    # Add ID column
    points_gdf["id"] = [f"scotland_{i:04d}" for i in range(len(points_gdf))]
    points_gdf["lat"] = points_gdf.geometry.y
    points_gdf["lon"] = points_gdf.geometry.x

    points_gdf.to_file(output_path, driver="GeoJSON")
    logger.info(f"Generated {len(points_gdf)} sample points: {output_path}")
    return output_path


def enrich_points(settings: Settings) -> Path:
    """
    Add elevation and LP zone metadata to sample points.

    Samples values from DEM and LP rasters at each point location.
    """
    points_path = settings.processed_dir / "sample_points.geojson"
    dem_path = settings.processed_dir / "scotland-dem.tif"
    lp_path = settings.processed_dir / "scotland_lp_2024.tif"
    palette_path = settings.processed_dir / "color_palette.json"
    output_path = settings.processed_dir / "sample_points_enriched.geojson"

    if output_path.exists():
        logger.info(f"Skipping point enrichment, file exists: {output_path}")
        return output_path

    points = gpd.read_file(points_path)

    with open(palette_path) as f:
        palette = json.load(f)

    # Sample elevation (if DEM exists)
    if dem_path.exists():
        with rasterio.open(dem_path) as dem:
            coords = [(p.x, p.y) for p in points.geometry]
            elevations = [val[0] for val in dem.sample(coords)]
            points["altitude_m"] = elevations
    else:
        points["altitude_m"] = 0  # Default for missing DEM
        logger.warning("No DEM available, using 0m elevation")

    # Sample LP zone
    with rasterio.open(lp_path) as lp:
        coords = [(p.x, p.y) for p in points.geometry]
        rgb_values = list(lp.sample(coords))

        zones = []
        tolerance = settings.color_tolerance
        for rgb in rgb_values:
            zone = "unknown"
            for p in palette:
                if all(abs(rgb[i] - p["rgb"][i]) <= tolerance for i in range(3)):
                    zone = p["zone"]
                    break
            zones.append(zone)
        points["lp_zone"] = zones

    points.to_file(output_path, driver="GeoJSON")
    logger.info(f"Enriched {len(points)} points: {output_path}")
    return output_path
