"""
Elevation API Client

Fetches elevation from Natural Resources Canada's CDEM API with:
- SQLite caching (coordinates rounded to 5 decimal places ~1m)
- Rate limiting (be nice to the API)
- Batch processing with progress
"""

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import aiohttp

# NRCan CDEM API endpoint
API_BASE = "https://geogratis.gc.ca/services/elevation/cdem/altitude"

# Default cache location
DEFAULT_CACHE_PATH = Path(__file__).parent / "elevation_cache.db"

# Rate limiting
BATCH_SIZE = 50
BATCH_DELAY = 0.5  # seconds between batches


@dataclass
class ElevationResult:
    """Result from elevation lookup."""

    lat: float
    lng: float
    elevation: float | None  # meters, or None if not available
    cached: bool = False  # True if result came from cache


class ElevationCache:
    """SQLite cache for elevation data."""

    def __init__(self, db_path: Path = DEFAULT_CACHE_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS elevations (
                    lat_key TEXT NOT NULL,
                    lng_key TEXT NOT NULL,
                    elevation REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (lat_key, lng_key)
                )
            """)
            conn.commit()

    @staticmethod
    def _coord_key(coord: float) -> str:
        """Round coordinate to 5 decimal places (~1m precision) for cache key."""
        return f"{coord:.5f}"

    def get(self, lat: float, lng: float) -> float | None:
        """Get cached elevation, or None if not cached."""
        lat_key = self._coord_key(lat)
        lng_key = self._coord_key(lng)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT elevation FROM elevations WHERE lat_key = ? AND lng_key = ?",
                (lat_key, lng_key),
            ).fetchone()

            if row:
                return row[0]  # May be None if API returned no data
            return None  # Not in cache

    def get_many(
        self, coords: list[tuple[float, float]]
    ) -> dict[tuple[str, str], float | None]:
        """Get cached elevations for multiple coordinates.

        Returns dict mapping (lat_key, lng_key) -> elevation.
        Missing coordinates are not in the returned dict.
        """
        if not coords:
            return {}

        keys = [(self._coord_key(lat), self._coord_key(lng)) for lat, lng in coords]

        with sqlite3.connect(self.db_path) as conn:
            # Build query for all coordinates
            placeholders = ",".join(["(?, ?)"] * len(keys))
            flat_keys = [k for pair in keys for k in pair]

            rows = conn.execute(
                f"""
                SELECT lat_key, lng_key, elevation FROM elevations
                WHERE (lat_key, lng_key) IN (VALUES {placeholders})
                """,
                flat_keys,
            ).fetchall()

            return {(row[0], row[1]): row[2] for row in rows}

    def set(self, lat: float, lng: float, elevation: float | None) -> None:
        """Cache an elevation value."""
        lat_key = self._coord_key(lat)
        lng_key = self._coord_key(lng)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO elevations (lat_key, lng_key, elevation)
                VALUES (?, ?, ?)
                """,
                (lat_key, lng_key, elevation),
            )
            conn.commit()

    def set_many(self, results: list[tuple[float, float, float | None]]) -> None:
        """Cache multiple elevation values."""
        if not results:
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO elevations (lat_key, lng_key, elevation)
                VALUES (?, ?, ?)
                """,
                [
                    (self._coord_key(lat), self._coord_key(lng), elev)
                    for lat, lng, elev in results
                ],
            )
            conn.commit()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM elevations").fetchone()[0]
            with_data = conn.execute(
                "SELECT COUNT(*) FROM elevations WHERE elevation IS NOT NULL"
            ).fetchone()[0]
            return {
                "total": total,
                "with_data": with_data,
                "no_data": total - with_data,
            }


class ElevationClient:
    """Async client for fetching elevation data."""

    def __init__(self, cache_path: Path = DEFAULT_CACHE_PATH):
        self.cache = ElevationCache(cache_path)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def _fetch_one(self, lat: float, lng: float) -> float | None:
        """Fetch elevation for a single point from API."""
        if not self._session:
            raise RuntimeError("Client must be used as async context manager")

        url = f"{API_BASE}?lat={lat}&lon={lng}"

        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("altitude")
                return None
        except Exception:
            return None

    async def get_elevation(self, lat: float, lng: float) -> ElevationResult:
        """Get elevation for a single point (uses cache)."""
        # Check cache first
        cached = self.cache.get(lat, lng)
        if cached is not None:
            return ElevationResult(lat=lat, lng=lng, elevation=cached, cached=True)

        # Fetch from API
        elevation = await self._fetch_one(lat, lng)

        # Cache the result (even if None)
        self.cache.set(lat, lng, elevation)

        return ElevationResult(lat=lat, lng=lng, elevation=elevation, cached=False)

    async def get_elevations(
        self,
        coords: list[tuple[float, float]],
        batch_size: int = BATCH_SIZE,
        batch_delay: float = BATCH_DELAY,
        progress_callback=None,
    ) -> list[ElevationResult]:
        """Get elevations for multiple points with batching and rate limiting.

        Args:
            coords: List of (lat, lng) tuples
            batch_size: Number of concurrent requests per batch
            batch_delay: Seconds to wait between batches
            progress_callback: Optional callback(completed, total) for progress updates
        """
        if not coords:
            return []

        results: list[ElevationResult] = []

        # Check cache for all coordinates first
        cache_key = self.cache._coord_key
        cached = self.cache.get_many(coords)

        # Separate cached vs uncached
        uncached_coords: list[tuple[int, float, float]] = []  # (index, lat, lng)

        for i, (lat, lng) in enumerate(coords):
            key = (cache_key(lat), cache_key(lng))
            if key in cached:
                results.append(
                    ElevationResult(
                        lat=lat, lng=lng, elevation=cached[key], cached=True
                    )
                )
            else:
                results.append(
                    ElevationResult(lat=lat, lng=lng, elevation=None, cached=False)
                )
                uncached_coords.append((i, lat, lng))

        if progress_callback:
            progress_callback(len(coords) - len(uncached_coords), len(coords))

        if not uncached_coords:
            return results

        # Fetch uncached in batches
        to_cache: list[tuple[float, float, float | None]] = []

        for batch_start in range(0, len(uncached_coords), batch_size):
            batch = uncached_coords[batch_start : batch_start + batch_size]

            # Fetch batch concurrently
            tasks = [self._fetch_one(lat, lng) for _, lat, lng in batch]
            elevations = await asyncio.gather(*tasks)

            # Update results and prepare cache entries
            for (idx, lat, lng), elev in zip(batch, elevations):
                results[idx] = ElevationResult(
                    lat=lat, lng=lng, elevation=elev, cached=False
                )
                to_cache.append((lat, lng, elev))

            if progress_callback:
                completed = (
                    len(coords) - len(uncached_coords) + batch_start + len(batch)
                )
                progress_callback(completed, len(coords))

            # Rate limit between batches
            if batch_start + batch_size < len(uncached_coords):
                await asyncio.sleep(batch_delay)

        # Cache all fetched results
        self.cache.set_many(to_cache)

        return results


# Convenience functions for simple usage


async def fetch_elevation(lat: float, lng: float) -> float | None:
    """Fetch elevation for a single point."""
    async with ElevationClient() as client:
        result = await client.get_elevation(lat, lng)
        return result.elevation


async def batch_fetch_elevation(
    coords: list[tuple[float, float]],
    progress_callback=None,
) -> list[float | None]:
    """Fetch elevations for multiple points."""
    async with ElevationClient() as client:
        results = await client.get_elevations(
            coords, progress_callback=progress_callback
        )
        return [r.elevation for r in results]
