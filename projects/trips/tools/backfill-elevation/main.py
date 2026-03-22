#!/usr/bin/env python3
"""
Backfill Elevation Data

Replays all trip points from NATS, enriches with elevation data from
Natural Resources Canada's CDEM API, and re-publishes to NATS.

Usage:
    # Preview what would be updated (dry run)
    python main.py --dry-run

    # Backfill all points
    python main.py

    # Backfill with custom NATS URL
    NATS_URL=nats://localhost:4222 python main.py
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import nats
import typer
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)
from rich.console import Console

from projects.trips.tools.elevation import ElevationClient, ElevationCache

# Configuration
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

app = typer.Typer(
    help="Backfill elevation data for trip points", invoke_without_command=True
)
console = Console()
logger = logging.getLogger(__name__)


@dataclass
class TripPoint:
    """Trip point from NATS stream."""

    id: str
    lat: float
    lng: float
    timestamp: str
    image: str | None
    source: str
    tags: list[str]
    elevation: float | None = None
    deleted: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "TripPoint":
        return cls(
            id=data.get("id", ""),
            lat=data.get("lat", 0.0),
            lng=data.get("lng", 0.0),
            timestamp=data.get("timestamp", ""),
            image=data.get("image"),
            source=data.get("source", "unknown"),
            tags=data.get("tags", []),
            elevation=data.get("elevation"),
            deleted=data.get("deleted", False),
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "lat": self.lat,
            "lng": self.lng,
            "timestamp": self.timestamp,
            "image": self.image,
            "source": self.source,
            "tags": self.tags,
        }
        if self.elevation is not None:
            d["elevation"] = self.elevation
        return d


async def replay_stream(js) -> list[TripPoint]:
    """Replay all messages from the trips stream."""
    points: dict[str, TripPoint] = {}

    try:
        consumer = await js.pull_subscribe(
            "trips.>",
            stream="trips",
            config=nats.js.api.ConsumerConfig(
                deliver_policy=nats.js.api.DeliverPolicy.ALL,
                ack_policy=nats.js.api.AckPolicy.NONE,
            ),
        )

        while True:
            try:
                msgs = await consumer.fetch(batch=100, timeout=1)
                for msg in msgs:
                    try:
                        data = json.loads(msg.data.decode())
                        point = TripPoint.from_dict(data)

                        # Handle tombstone messages
                        if point.deleted or data.get("deleted"):
                            point_id = data.get("id")
                            if point_id and point_id in points:
                                del points[point_id]
                        elif point.id:
                            points[point.id] = point
                    except Exception as e:
                        logger.warning("Could not parse NATS message: %s", e)
                        console.print(f"[yellow]Warning: Could not parse message: {e}")
            except nats.errors.TimeoutError:
                break

        await consumer.unsubscribe()

    except nats.js.errors.NotFoundError:
        console.print("[red]Error: Stream 'trips' not found")
        return []

    return list(points.values())


async def publish_point(js, point: TripPoint) -> None:
    """Publish a point to NATS."""
    await js.publish("trips.point", json.dumps(point.to_dict()).encode())


async def run_backfill(dry_run: bool = False, force: bool = False) -> None:
    """Main backfill logic."""
    console.print(f"[cyan]Connecting to NATS at {NATS_URL}...")
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()
    console.print("[green]Connected")

    try:
        # Step 1: Replay all points from stream
        console.print("\n[cyan]Replaying trip points from stream...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            progress.add_task("Loading points...", total=None)
            points = await replay_stream(js)

        console.print(f"[green]Loaded {len(points)} points")

        if not points:
            console.print("[yellow]No points to process")
            return

        # Step 2: Filter points that need elevation
        if force:
            needs_elevation = points
        else:
            needs_elevation = [p for p in points if p.elevation is None]

        already_have = len(points) - len(needs_elevation)
        console.print(
            f"[cyan]Points needing elevation: {len(needs_elevation)} "
            f"(already have: {already_have})"
        )

        if not needs_elevation:
            console.print("[green]All points already have elevation data!")
            return

        # Show preview of points
        console.print("\n[cyan]Sample points to process:")
        for p in needs_elevation[:5]:
            elev_str = f"{p.elevation}m" if p.elevation else "none"
            console.print(
                f"  {p.id[:12]}... ({p.lat:.4f}, {p.lng:.4f}) "
                f"elev={elev_str} source={p.source}"
            )
        if len(needs_elevation) > 5:
            console.print(f"  ... and {len(needs_elevation) - 5} more")

        if dry_run:
            console.print("\n[yellow][DRY RUN] Would fetch elevation and re-publish")
            return

        # Step 3: Fetch elevation data
        console.print("\n[cyan]Fetching elevation data from NRCan API...")
        coords = [(p.lat, p.lng) for p in needs_elevation]

        async with ElevationClient() as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task("Fetching elevations...", total=len(coords))

                def update_progress(completed, total):
                    progress.update(task, completed=completed)

                results = await client.get_elevations(
                    coords, progress_callback=update_progress
                )

        # Show cache stats
        stats = client.cache.stats()
        console.print(
            f"[dim]Cache stats: {stats['total']} total, "
            f"{stats['with_data']} with data, {stats['no_data']} no data"
        )

        # Count results
        fetched = sum(1 for r in results if r.elevation is not None)
        cached = sum(1 for r in results if r.cached)
        console.print(
            f"[green]Fetched {fetched}/{len(results)} elevations ({cached} from cache)"
        )

        # Step 4: Update points with elevation
        for point, result in zip(needs_elevation, results):
            point.elevation = result.elevation

        # Step 5: Re-publish all points with elevation
        console.print("\n[cyan]Re-publishing points with elevation...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Publishing...", total=len(needs_elevation))

            for point in needs_elevation:
                await publish_point(js, point)
                progress.advance(task)

        console.print(f"[green]Published {len(needs_elevation)} points with elevation")

        # Summary
        with_elevation = sum(1 for p in needs_elevation if p.elevation is not None)
        console.print(
            f"\n[green]Done! {with_elevation}/{len(needs_elevation)} points now have elevation"
        )

    finally:
        await nc.close()


@app.callback(invoke_without_command=True)
def backfill(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview changes without publishing"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Re-fetch elevation even for points that have it"
        ),
    ] = False,
) -> None:
    """
    Backfill elevation data for all trip points.

    Replays the NATS stream, fetches elevation from NRCan CDEM API,
    and re-publishes points with elevation data.

    Examples:
        # Preview what would be updated
        python main.py --dry-run

        # Backfill all points missing elevation
        python main.py

        # Force re-fetch all elevations (useful if API data improved)
        python main.py --force
    """
    # Only run backfill if no subcommand was invoked
    if ctx.invoked_subcommand is None:
        asyncio.run(run_backfill(dry_run=dry_run, force=force))


@app.command()
def cache_stats() -> None:
    """Show elevation cache statistics."""
    cache = ElevationCache()
    stats = cache.stats()

    console.print("[cyan]Elevation Cache Statistics")
    console.print(f"  Total entries:  {stats['total']}")
    console.print(f"  With elevation: {stats['with_data']}")
    console.print(f"  No data:        {stats['no_data']}")


if __name__ == "__main__":
    app()
