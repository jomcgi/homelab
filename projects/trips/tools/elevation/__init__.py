"""
Elevation Module

Fetches elevation data from Natural Resources Canada's Canadian Digital Elevation Model (CDEM).
- ~20m resolution ground-level elevation
- Covers all of Canada
- Includes SQLite caching (elevation doesn't change)
"""

from .client import ElevationClient, fetch_elevation, batch_fetch_elevation

__all__ = ["ElevationClient", "fetch_elevation", "batch_fetch_elevation"]
