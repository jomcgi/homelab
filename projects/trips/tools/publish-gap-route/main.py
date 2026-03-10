"""
Publish Gap Route

Parses a KML file (e.g., from Google Maps directions) and publishes gap points
to fill in missing route segments where no images exist.

Gap points:
- Have no image (image: null)
- Are used only for map route rendering
- Are not selectable in the timeline
- Rendered with lower opacity on the map
"""

import asyncio
import json
import uuid
import defusedxml.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

import nats
import typer

# NATS configuration
import os

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

# Namespace UUID for deterministic gap point ID generation
GAP_KEY_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f23456789012")

app = typer.Typer(help="Publish gap route points from KML files")


def parse_kml_coordinates(kml_path: Path) -> list[tuple[float, float]]:
    """Parse KML file and extract coordinates from LineString elements.

    Returns list of (lat, lng) tuples.
    """
    tree = ET.parse(kml_path)
    root = tree.getroot()

    # Handle KML namespace
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    coordinates = []

    # Find all LineString elements (route paths)
    for linestring in root.findall(".//kml:LineString/kml:coordinates", ns):
        if linestring.text:
            # Coordinates are space-separated, each coord is "lng,lat,alt"
            for coord_str in linestring.text.strip().split():
                parts = coord_str.split(",")
                if len(parts) >= 2:
                    lng = float(parts[0])
                    lat = float(parts[1])
                    coordinates.append((lat, lng))

    return coordinates


def sample_coordinates(
    coords: list[tuple[float, float]], max_points: int = 100
) -> list[tuple[float, float]]:
    """Sample coordinates to reduce density while preserving route shape.

    Uses simple uniform sampling. For a more accurate representation,
    could use Douglas-Peucker line simplification.
    """
    if len(coords) <= max_points:
        return coords

    # Calculate step size to get approximately max_points
    step = len(coords) / max_points

    sampled = []
    for i in range(max_points):
        idx = int(i * step)
        sampled.append(coords[idx])

    # Always include the last point
    if sampled[-1] != coords[-1]:
        sampled.append(coords[-1])

    return sampled


def generate_gap_id(lat: float, lng: float, timestamp: str) -> str:
    """Generate deterministic ID for a gap point."""
    identity = f"gap:{lat:.5f}:{lng:.5f}:{timestamp}"
    key_uuid = uuid.uuid5(GAP_KEY_NAMESPACE, identity)
    return f"gap_{key_uuid.hex[:12]}"


async def get_jetstream() -> tuple:
    """Connect to NATS and return (connection, jetstream) tuple."""
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()

    # Ensure stream exists
    try:
        await js.stream_info("trips")
    except nats.js.errors.NotFoundError:
        await js.add_stream(name="trips", subjects=["trips.>"])

    return nc, js


async def publish_gap_points(
    js,
    coords: list[tuple[float, float]],
    start_time: datetime,
) -> int:
    """Publish gap points to NATS.

    Timestamps are sequential milliseconds after start_time,
    purely for ordering (not displayed).
    """
    count = 0

    for i, (lat, lng) in enumerate(coords):
        # Generate sequential timestamp for ordering
        # Each point is 1 millisecond apart - enough for sorting
        timestamp = (start_time + timedelta(milliseconds=i)).isoformat()

        point_id = generate_gap_id(lat, lng, timestamp)

        point = {
            "id": point_id,
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "timestamp": timestamp,
            "image": None,  # Gap points have no image
            "source": "gap",
            "tags": ["gap", "car"],
        }

        await js.publish("trips.point", json.dumps(point).encode())
        count += 1

    return count


@app.command()
def publish(
    kml_file: Annotated[
        Path,
        typer.Argument(help="KML file to parse (e.g., from Google Maps directions)"),
    ],
    start_time: Annotated[
        str,
        typer.Argument(
            help="Start time for ordering (ISO format, e.g., '2025-01-03T10:28:00')"
        ),
    ],
    max_points: Annotated[
        int,
        typer.Option("--max-points", "-m", help="Maximum number of points to publish"),
    ] = 100,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Parse and show points, don't publish"),
    ] = False,
) -> None:
    """
    Publish gap route points from a KML file.

    Gap points fill in missing route segments where no images exist
    (e.g., GoPro ran out of space or wasn't recording).

    Example:
        # Publish gap route starting at 10:28 AM on Jan 3
        python main.py example.kml "2025-01-03T10:28:00"

        # Preview without publishing
        python main.py example.kml "2025-01-03T10:28:00" --dry-run

        # Limit to 50 points for a shorter segment
        python main.py example.kml "2025-01-03T10:28:00" --max-points 50
    """
    if not kml_file.exists():
        print(f"Error: KML file not found: {kml_file}")
        raise typer.Exit(1)

    # Parse start time
    try:
        start_dt = datetime.fromisoformat(start_time)
    except ValueError as e:
        print(f"Error: Invalid start time format: {e}")
        print("Expected ISO format, e.g., '2025-01-03T10:28:00'")
        raise typer.Exit(1)

    # Parse KML
    print(f"Parsing {kml_file}...")
    coords = parse_kml_coordinates(kml_file)

    if not coords:
        print("Error: No coordinates found in KML file")
        raise typer.Exit(1)

    print(f"Found {len(coords)} coordinates")

    # Sample if needed
    if len(coords) > max_points:
        coords = sample_coordinates(coords, max_points)
        print(f"Sampled to {len(coords)} points")

    # Show preview
    print(f"\nRoute preview:")
    print(f"  Start: ({coords[0][0]:.5f}, {coords[0][1]:.5f})")
    print(f"  End:   ({coords[-1][0]:.5f}, {coords[-1][1]:.5f})")
    print(f"  Points: {len(coords)}")
    print(f"  Start time: {start_dt.isoformat()}")

    if dry_run:
        print("\n[DRY RUN] Would publish the following points:")
        for i, (lat, lng) in enumerate(coords[:5]):
            ts = (start_dt + timedelta(milliseconds=i)).isoformat()
            print(f"  {i + 1}. ({lat:.5f}, {lng:.5f}) @ {ts}")
        if len(coords) > 5:
            print(f"  ... and {len(coords) - 5} more")
        return

    # Publish to NATS
    async def _publish():
        print("\nConnecting to NATS...")
        nc, js = await get_jetstream()
        try:
            print("Publishing gap points...")
            count = await publish_gap_points(js, coords, start_dt)
            print(f"Published {count} gap points")
        finally:
            await nc.close()

    asyncio.run(_publish())
    print("Done!")


@app.command()
def preview(
    kml_file: Annotated[
        Path,
        typer.Argument(help="KML file to parse"),
    ],
) -> None:
    """Preview coordinates in a KML file without publishing."""
    if not kml_file.exists():
        print(f"Error: KML file not found: {kml_file}")
        raise typer.Exit(1)

    coords = parse_kml_coordinates(kml_file)

    if not coords:
        print("No coordinates found")
        return

    print(f"Found {len(coords)} coordinates:")
    print(f"  Start: ({coords[0][0]:.5f}, {coords[0][1]:.5f})")
    print(f"  End:   ({coords[-1][0]:.5f}, {coords[-1][1]:.5f})")

    # Show first and last few points
    print("\nFirst 5 points:")
    for i, (lat, lng) in enumerate(coords[:5]):
        print(f"  {i + 1}. ({lat:.5f}, {lng:.5f})")

    if len(coords) > 10:
        print(f"\n  ... {len(coords) - 10} more points ...")

    print("\nLast 5 points:")
    for i, (lat, lng) in enumerate(coords[-5:]):
        print(f"  {len(coords) - 4 + i}. ({lat:.5f}, {lng:.5f})")


if __name__ == "__main__":
    app()
