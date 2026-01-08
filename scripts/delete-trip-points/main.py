"""
Delete Trip Points

Publishes tombstone messages to NATS to delete trip points.
Points are deleted by publishing {"id": "point_id", "deleted": true} messages.
"""

import asyncio
import json
import os
from typing import Annotated

import httpx
import nats
import typer

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
API_URL = os.getenv("TRIPS_API_URL", "https://api.jomcgi.dev/trips")

app = typer.Typer(help="Delete trip points via NATS tombstone messages")


async def get_jetstream() -> tuple:
    """Connect to NATS and return (connection, jetstream) tuple."""
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()
    return nc, js


async def publish_delete(js, point_id: str) -> None:
    """Publish a tombstone message to delete a point."""
    tombstone = {"id": point_id, "deleted": True}
    await js.publish("trips.delete", json.dumps(tombstone).encode())


@app.command()
def by_date(
    date: Annotated[
        str,
        typer.Argument(help="Date to delete gap points for (YYYY-MM-DD format)"),
    ],
    source: Annotated[
        str,
        typer.Option("--source", "-s", help="Filter by source (e.g., 'gap')"),
    ] = "gap",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be deleted"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Delete all points for a specific date and source."""

    async def _delete():
        print(f"Fetching points from {API_URL}...")
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_URL}/api/points", timeout=30)
            resp.raise_for_status()
            data = resp.json()

        # Filter points by date and source
        to_delete = [
            p
            for p in data["points"]
            if p["timestamp"].startswith(date) and p["source"] == source
        ]

        if not to_delete:
            print(f"No {source} points found for {date}")
            return

        print(f"Found {len(to_delete)} {source} points for {date}")

        # Show sample
        print("\nSample points to delete:")
        for p in to_delete[:5]:
            print(f"  {p['id']}: ({p['lat']}, {p['lng']}) @ {p['timestamp']}")
        if len(to_delete) > 5:
            print(f"  ... and {len(to_delete) - 5} more")

        if dry_run:
            print("\n[DRY RUN] No points deleted")
            return

        # Confirm
        if not yes:
            confirm = typer.confirm(f"\nDelete {len(to_delete)} points?")
            if not confirm:
                print("Cancelled")
                return

        # Connect to NATS and publish tombstones
        print("\nConnecting to NATS...")
        nc, js = await get_jetstream()

        try:
            print("Publishing delete messages...")
            for i, p in enumerate(to_delete):
                await publish_delete(js, p["id"])
                if (i + 1) % 50 == 0:
                    print(f"  Deleted {i + 1}/{len(to_delete)}...")

            print(f"Deleted {len(to_delete)} points")
        finally:
            await nc.close()

    asyncio.run(_delete())


@app.command()
def by_id(
    point_ids: Annotated[
        list[str],
        typer.Argument(help="Point IDs to delete"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be deleted"),
    ] = False,
) -> None:
    """Delete specific points by ID."""

    async def _delete():
        print(f"Deleting {len(point_ids)} points...")

        if dry_run:
            for pid in point_ids:
                print(f"  Would delete: {pid}")
            print("\n[DRY RUN] No points deleted")
            return

        nc, js = await get_jetstream()

        try:
            for pid in point_ids:
                await publish_delete(js, pid)
                print(f"  Deleted: {pid}")

            print(f"\nDeleted {len(point_ids)} points")
        finally:
            await nc.close()

    asyncio.run(_delete())


@app.command()
def list_gaps(
    date: Annotated[
        str,
        typer.Argument(help="Date to list gap points for (YYYY-MM-DD format)"),
    ] = None,
) -> None:
    """List gap points, optionally filtered by date."""

    async def _list():
        print(f"Fetching points from {API_URL}...")
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_URL}/api/points", timeout=30)
            resp.raise_for_status()
            data = resp.json()

        gaps = [p for p in data["points"] if p["source"] == "gap"]

        if date:
            gaps = [p for p in gaps if p["timestamp"].startswith(date)]

        if not gaps:
            print("No gap points found")
            return

        # Group by date
        by_date = {}
        for p in gaps:
            d = p["timestamp"][:10]
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(p)

        print(f"\nFound {len(gaps)} gap points:")
        for d in sorted(by_date.keys()):
            points = by_date[d]
            first = points[0]
            print(f"\n  {d}: {len(points)} points")
            print(f"    Start: ({first['lat']}, {first['lng']})")
            print(f"    Sample ID: {first['id']}")

    asyncio.run(_list())


if __name__ == "__main__":
    app()
