"""Phase 2: Preprocessing - transform raw data into analysis-ready formats."""

import json
import logging
import subprocess
from pathlib import Path

import osmium
from PIL import Image

from projects.stargazer.backend.config import Settings

logger = logging.getLogger(__name__)


def georeference_raster(settings: Settings) -> Path:
    """
    Add spatial reference to the LP PNG and clip to Scotland bounds.

    Uses GDAL to:
    1. Assign EPSG:4326 CRS with Europe bounds
    2. Clip to Scotland bounds
    """
    input_png = settings.raw_dir / "Europe2024.png"
    europe_tif = settings.processed_dir / "europe_lp_2024.tif"
    scotland_tif = settings.processed_dir / "scotland_lp_2024.tif"

    if scotland_tif.exists():
        logger.info(f"Skipping georeference, file exists: {scotland_tif}")
        return scotland_tif

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    eb = settings.europe_bounds

    # Step 1: Assign CRS and bounds to PNG, expand palette to RGB
    logger.info("Georeferencing Europe LP atlas...")
    subprocess.run(
        [
            "gdal_translate",
            "-a_srs",
            "EPSG:4326",
            "-a_ullr",
            str(eb.west),
            str(eb.north),
            str(eb.east),
            str(eb.south),
            "-expand",
            "rgb",  # Expand paletted image to 3-band RGB
            str(input_png),
            str(europe_tif),
        ],
        check=True,
    )

    # Step 2: Clip to Scotland bounds
    b = settings.bounds
    logger.info("Clipping to Scotland bounds...")
    subprocess.run(
        [
            "gdalwarp",
            "-te",
            str(b.west),
            str(b.south),
            str(b.east),
            str(b.north),
            str(europe_tif),
            str(scotland_tif),
        ],
        check=True,
    )

    logger.info(f"Created georeferenced raster: {scotland_tif}")
    return scotland_tif


def extract_palette(settings: Settings) -> Path:
    """
    Extract RGB values from colorbar and map to zone names.

    Output format:
    [
        {"rgb": [R, G, B], "zone": "2a", "lpi_range": [0.11, 0.19]},
        ...
    ]
    """
    colorbar_path = settings.raw_dir / "colorbar.png"
    output_path = settings.processed_dir / "color_palette.json"

    if output_path.exists():
        logger.info(f"Skipping palette extraction, file exists: {output_path}")
        return output_path

    settings.processed_dir.mkdir(parents=True, exist_ok=True)

    # Zone definitions from DJ Lorenz
    zones = [
        {"zone": "0", "lpi_range": [0, 0.01], "mpsas_range": [21.99, 22.0]},
        {"zone": "1a", "lpi_range": [0.01, 0.06], "mpsas_range": [21.93, 21.99]},
        {"zone": "1b", "lpi_range": [0.06, 0.11], "mpsas_range": [21.89, 21.93]},
        {"zone": "2a", "lpi_range": [0.11, 0.19], "mpsas_range": [21.81, 21.89]},
        {"zone": "2b", "lpi_range": [0.19, 0.33], "mpsas_range": [21.69, 21.81]},
        {"zone": "3a", "lpi_range": [0.33, 0.58], "mpsas_range": [21.51, 21.69]},
        {"zone": "3b", "lpi_range": [0.58, 1.00], "mpsas_range": [21.25, 21.51]},
        {"zone": "4a", "lpi_range": [1.00, 1.74], "mpsas_range": [20.91, 21.25]},
        {"zone": "4b", "lpi_range": [1.74, 3.00], "mpsas_range": [20.49, 20.91]},
    ]

    # Sample colors from colorbar image
    img = Image.open(colorbar_path)
    width, height = img.size

    # Sample vertical strip (colorbar is typically vertical)
    palette = []
    num_zones = len(zones)
    for i, zone_def in enumerate(zones):
        # Sample from middle of each zone's region
        y = int((i + 0.5) * height / num_zones)
        x = width // 2
        r, g, b = img.getpixel((x, y))[:3]
        palette.append(
            {
                "rgb": [r, g, b],
                **zone_def,
            }
        )

    with open(output_path, "w") as f:
        json.dump(palette, f, indent=2)

    logger.info(f"Extracted {len(palette)} zone colors to {output_path}")
    return output_path


# Highway types to include for drivable road access
ROAD_HIGHWAY_TYPES = frozenset(
    [
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "track",
    ]
)


def extract_roads(settings: Settings) -> Path:
    """
    Extract drivable roads from OSM PBF using pyosmium.

    Includes: motorway, trunk, primary, secondary, tertiary, unclassified, residential, track
    Excludes: footway, path, cycleway, service, access=private
    """
    input_pbf = settings.raw_dir / "scotland-latest.osm.pbf"
    filtered_pbf = settings.processed_dir / "scotland-roads.osm.pbf"
    output_geojson = settings.processed_dir / "scotland-roads.geojson"

    if output_geojson.exists():
        logger.info(f"Skipping road extraction, file exists: {output_geojson}")
        return output_geojson

    settings.processed_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Filter roads with pyosmium
    # BackReferenceWriter ensures nodes referenced by ways are included
    logger.info("Filtering roads from OSM data...")

    writer = osmium.BackReferenceWriter(
        str(filtered_pbf),
        ref_src=str(input_pbf),
        overwrite=True,
    )

    # Process the file and filter ways with matching highway tags
    with writer:
        for obj in osmium.FileProcessor(str(input_pbf)):
            if obj.is_way():
                highway = obj.tags.get("highway")
                if highway in ROAD_HIGHWAY_TYPES:
                    writer.add(obj)

    logger.info(f"Filtered roads written to {filtered_pbf}")

    # Step 2: Convert to GeoJSON with ogr2ogr
    logger.info("Converting to GeoJSON...")
    subprocess.run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            str(output_geojson),
            str(filtered_pbf),
            "lines",
        ],
        check=True,
    )

    logger.info(f"Extracted roads to {output_geojson}")
    return output_geojson


def clip_dem(settings: Settings) -> Path:
    """Clip DEM to Scotland bounds using gdalwarp."""
    # TODO: Implement DEM clipping once download_dem is complete
    output_path = settings.processed_dir / "scotland-dem.tif"
    logger.warning("DEM clipping not yet implemented")
    return output_path
