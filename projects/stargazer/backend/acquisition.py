"""Phase 1: Data Acquisition - download source data files."""

import logging
from pathlib import Path

import httpx

from projects.stargazer.backend.config import Settings

logger = logging.getLogger(__name__)


async def download_file(url: str, dest: Path, client: httpx.AsyncClient) -> Path:
    """Download a file if it doesn't already exist."""
    if dest.exists():
        logger.info(f"Skipping download, file exists: {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {url} -> {dest}")

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(dest, "wb") as f:
            async for chunk in response.aiter_bytes():
                f.write(chunk)

    logger.info(f"Downloaded {dest} ({dest.stat().st_size} bytes)")
    return dest


async def download_lp_atlas(settings: Settings, client: httpx.AsyncClient) -> Path:
    """Download DJ Lorenz 2024 Europe light pollution map (~15MB)."""
    dest = settings.raw_dir / "Europe2024.png"
    return await download_file(settings.lp_source_url, dest, client)


async def download_colorbar(settings: Settings, client: httpx.AsyncClient) -> Path:
    """Download color scale reference for zone classification (~5KB)."""
    dest = settings.raw_dir / "colorbar.png"
    return await download_file(settings.colorbar_url, dest, client)


async def download_osm_roads(settings: Settings, client: httpx.AsyncClient) -> Path:
    """Download OpenStreetMap road network for Scotland (~120MB)."""
    dest = settings.raw_dir / "scotland-latest.osm.pbf"
    return await download_file(settings.osm_source_url, dest, client)


async def download_dem(settings: Settings) -> Path:
    """
    Download SRTM DEM tiles for elevation data.

    Note: SRTM coverage ends at 60°N; Shetland (60.86°N) needs
    Copernicus DEM fallback or 0m assumption.
    """
    # TODO: Implement SRTM tile fetching based on bounds
    # For now, return placeholder path
    dest = settings.raw_dir / "srtm_tiles"
    dest.mkdir(parents=True, exist_ok=True)
    logger.warning("DEM download not yet implemented - using placeholder")
    return dest
