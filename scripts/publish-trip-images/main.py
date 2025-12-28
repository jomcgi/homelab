"""
Publish Trip Images

Scans a directory (e.g., SD card) for images, extracts EXIF metadata,
uploads to SeaweedFS, and publishes trip points to NATS.
"""

import asyncio
import json
import os
import signal
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated

import boto3
import nats
from botocore.config import Config
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import typer

# Defaults
DB_PATH = Path(__file__).parent / "publish_queue.db"
DEFAULT_BUCKET = "trips"

# SeaweedFS S3 endpoint (for local dev, use port-forward or external URL)
SEAWEEDFS_ENDPOINT = os.getenv("SEAWEEDFS_ENDPOINT", "http://localhost:8333")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

app = typer.Typer(help="Publish trip images to SeaweedFS and NATS")


class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ImageRecord:
    id: int
    source_path: str
    dest_key: str
    status: UploadStatus
    retry_count: int
    error_message: str | None
    lat: float | None
    lng: float | None
    timestamp: str | None
    created_at: str
    completed_at: str | None


class UploadQueue:
    """Persistent queue for tracking image uploads."""

    MAX_RETRIES = 3

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL UNIQUE,
                    dest_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    lat REAL,
                    lng REAL,
                    timestamp TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON images(status)")
            conn.commit()

    def add(
        self,
        source_path: Path,
        dest_key: str,
        lat: float | None,
        lng: float | None,
        timestamp: str | None,
    ) -> int | None:
        """Add image to queue. Returns ID or None if already exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO images (source_path, dest_key, lat, lng, timestamp, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(source_path),
                        dest_key,
                        lat,
                        lng,
                        timestamp,
                        UploadStatus.PENDING.value,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_pending(self) -> list[ImageRecord]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM images
                WHERE status = ? OR (status = ? AND retry_count < ?)
                ORDER BY id ASC
                """,
                (
                    UploadStatus.PENDING.value,
                    UploadStatus.FAILED.value,
                    self.MAX_RETRIES,
                ),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_completed(self) -> list[ImageRecord]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM images WHERE status = ? ORDER BY id ASC",
                (UploadStatus.COMPLETED.value,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def mark_uploading(self, record_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE images SET status = ? WHERE id = ?",
                (UploadStatus.UPLOADING.value, record_id),
            )
            conn.commit()

    def mark_completed(self, record_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE images SET status = ?, completed_at = ? WHERE id = ?",
                (UploadStatus.COMPLETED.value, datetime.now().isoformat(), record_id),
            )
            conn.commit()

    def mark_failed(self, record_id: int, error: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE images
                SET status = ?, error_message = ?, retry_count = retry_count + 1
                WHERE id = ?
                """,
                (UploadStatus.FAILED.value, error, record_id),
            )
            conn.commit()

    def reset_uploading(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE images SET status = ? WHERE status = ?",
                (UploadStatus.PENDING.value, UploadStatus.UPLOADING.value),
            )
            conn.commit()
            return cursor.rowcount

    def get_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM images GROUP BY status"
            ).fetchall()
            return {row[0]: row[1] for row in rows}

    def get_next_id(self) -> int:
        """Get the next image ID (max completed ID + 1)."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("SELECT MAX(id) FROM images").fetchone()
            return (result[0] or 0) + 1

    def _row_to_record(self, row: sqlite3.Row) -> ImageRecord:
        return ImageRecord(
            id=row["id"],
            source_path=row["source_path"],
            dest_key=row["dest_key"],
            status=UploadStatus(row["status"]),
            retry_count=row["retry_count"],
            error_message=row["error_message"],
            lat=row["lat"],
            lng=row["lng"],
            timestamp=row["timestamp"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


class GracefulShutdown:
    """Handle graceful shutdown on SIGINT/SIGTERM."""

    def __init__(self):
        self.shutdown_requested = False
        self._original_sigint = None
        self._original_sigterm = None

    def __enter__(self):
        self._original_sigint = signal.signal(signal.SIGINT, self._handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._handler)
        return self

    def __exit__(self, *args):
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handler(self, signum, frame):
        if self.shutdown_requested:
            print("\nForce quit - exiting immediately")
            raise SystemExit(1)
        print("\nShutdown requested - finishing current upload...")
        self.shutdown_requested = True


def get_gps_info(exif_data: dict) -> dict:
    """Extract GPS info from EXIF data."""
    gps_info = {}
    for key, val in exif_data.items():
        tag = GPSTAGS.get(key, key)
        gps_info[tag] = val
    return gps_info


def dms_to_decimal(dms: tuple, ref: str) -> float:
    """Convert GPS coordinates from DMS to decimal degrees."""
    degrees, minutes, seconds = dms
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_exif(image_path: Path) -> tuple[float | None, float | None, str | None]:
    """Extract GPS coordinates and timestamp from EXIF data."""
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()

        if not exif_data:
            return None, None, None

        lat = None
        lng = None
        timestamp = None

        # Build tag name lookup
        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = value

        # Extract GPS
        if "GPSInfo" in exif:
            gps = get_gps_info(exif["GPSInfo"])
            if "GPSLatitude" in gps and "GPSLongitude" in gps:
                lat = dms_to_decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
                lng = dms_to_decimal(
                    gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E")
                )

        # Extract timestamp (EXIF time is camera local time, not UTC)
        # Store without timezone suffix - frontend will display in Pacific
        if "DateTimeOriginal" in exif:
            dt = datetime.strptime(exif["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
            timestamp = dt.isoformat()
        elif "DateTime" in exif:
            dt = datetime.strptime(exif["DateTime"], "%Y:%m:%d %H:%M:%S")
            timestamp = dt.isoformat()

        return lat, lng, timestamp

    except Exception as e:
        print(f"  Warning: Could not extract EXIF from {image_path.name}: {e}")
        return None, None, None


def get_s3_client():
    """Create S3 client for SeaweedFS."""
    return boto3.client(
        "s3",
        endpoint_url=SEAWEEDFS_ENDPOINT,
        aws_access_key_id="any",  # SeaweedFS with auth disabled
        aws_secret_access_key="any",
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(s3_client, bucket: str) -> None:
    """Create bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=bucket)
    except s3_client.exceptions.ClientError:
        print(f"Creating bucket: {bucket}")
        s3_client.create_bucket(Bucket=bucket)


def upload_image(s3_client, bucket: str, source_path: Path, dest_key: str) -> None:
    """Upload image to SeaweedFS."""
    content_type = "image/jpeg"
    if source_path.suffix.lower() == ".png":
        content_type = "image/png"
    elif source_path.suffix.lower() in (".heic", ".heif"):
        content_type = "image/heic"

    s3_client.upload_file(
        str(source_path),
        bucket,
        dest_key,
        ExtraArgs={"ContentType": content_type},
    )


async def publish_to_nats(record: ImageRecord, image_id: int) -> None:
    """Publish trip point to NATS JetStream."""
    nc = await nats.connect(NATS_URL)
    js = nc.jetstream()

    # Ensure stream exists
    try:
        await js.stream_info("trips")
    except nats.js.errors.NotFoundError:
        await js.add_stream(name="trips", subjects=["trips.>"])

    # Build trip point message
    point = {
        "id": image_id,
        "lat": record.lat or 0.0,
        "lng": record.lng or 0.0,
        "timestamp": record.timestamp or datetime.now().isoformat(),
        "image_url": f"/trips/full/{record.dest_key}",
        "thumb_url": f"/trips/thumb/{record.dest_key}",
        "location": None,  # Could be reverse-geocoded later
        "animal": None,  # Could be detected later
    }

    await js.publish("trips.point", json.dumps(point).encode())
    await nc.close()


def scan_images(source_dir: Path) -> list[Path]:
    """Scan directory for image files (non-recursive)."""
    extensions = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
    images = []

    for path in sorted(source_dir.iterdir()):
        # Skip macOS resource fork files
        if path.name.startswith("._"):
            continue
        if path.is_file() and path.suffix.lower() in extensions:
            images.append(path)

    return images


def sample_images(images: list[Path], every_n: int) -> list[Path]:
    """Take every Nth image (assumes images are already sorted by filename/time)."""
    if every_n <= 1:
        return images
    return images[::every_n]


def generate_dest_key(image_path: Path, image_id: int) -> str:
    """Generate destination key for S3."""
    ext = image_path.suffix.lower()
    if ext in (".heic", ".heif"):
        ext = ".jpg"  # Will need conversion
    return f"img_{image_id:06d}{ext}"


async def _run_upload(
    source_dir: Path,
    db_path: Path,
    bucket: str,
    dry_run: bool,
    publish: bool,
    sample_interval: int = 1,
) -> None:
    """Main upload logic."""
    queue = UploadQueue(db_path)

    # Reset interrupted uploads
    reset_count = queue.reset_uploading()
    if reset_count:
        print(f"Reset {reset_count} interrupted uploads")

    # Scan for new images
    print(f"Scanning {source_dir}...")
    images = scan_images(source_dir)
    print(f"Found {len(images)} images")

    if not images:
        return

    # Sample every Nth image (e.g., every 60th for ~1/min from 1/sec captures)
    if sample_interval > 1:
        images = sample_images(images, sample_interval)
        print(f"Sampled every {sample_interval}th image: {len(images)} selected")

    if not images:
        return

    # Queue new images
    next_id = queue.get_next_id()
    new_count = 0
    for i, img_path in enumerate(images):
        dest_key = generate_dest_key(img_path, next_id + i)
        lat, lng, timestamp = extract_exif(img_path)

        record_id = queue.add(img_path, dest_key, lat, lng, timestamp)
        if record_id:
            new_count += 1
            gps_info = f"({lat:.4f}, {lng:.4f})" if lat and lng else "(no GPS)"
            print(f"  Queued: {img_path.name} -> {dest_key} {gps_info}")

    if new_count:
        print(f"Queued {new_count} new images")
    else:
        print("No new images to queue")

    # Show queue status
    stats = queue.get_stats()
    pending = stats.get(UploadStatus.PENDING.value, 0)
    completed = stats.get(UploadStatus.COMPLETED.value, 0)
    failed = stats.get(UploadStatus.FAILED.value, 0)
    print(f"Queue: {pending} pending, {completed} completed, {failed} failed")

    if dry_run:
        print("\n[DRY RUN] Would upload to SeaweedFS and publish to NATS")
        return

    if pending == 0:
        print("No pending uploads")
        return

    # Create S3 client and ensure bucket
    s3_client = get_s3_client()
    ensure_bucket(s3_client, bucket)

    # Process uploads
    with GracefulShutdown() as shutdown:
        pending_records = queue.get_pending()

        for record in pending_records:
            if shutdown.shutdown_requested:
                break

            queue.mark_uploading(record.id)
            source = Path(record.source_path)

            try:
                # Upload to S3
                print(f"[UPLOAD] {source.name} -> {record.dest_key}")
                upload_image(s3_client, bucket, source, record.dest_key)

                # Publish to NATS if requested
                if publish:
                    print(f"  [NATS] Publishing point {record.id}")
                    await publish_to_nats(record, record.id)

                queue.mark_completed(record.id)
                print(f"  [OK] Completed")

            except Exception as e:
                error_msg = str(e)
                queue.mark_failed(record.id, error_msg)
                retry_info = f"retry {record.retry_count + 1}/{queue.MAX_RETRIES}"
                print(f"  [FAIL] {error_msg} ({retry_info})")

    # Final stats
    final_stats = queue.get_stats()
    print(
        f"\nFinal: {final_stats.get(UploadStatus.COMPLETED.value, 0)} completed, "
        f"{final_stats.get(UploadStatus.FAILED.value, 0)} failed"
    )


@app.command()
def scan(
    source_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory to scan for images (e.g., /Volumes/SD_CARD/DCIM)"
        ),
    ],
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
    bucket: Annotated[
        str, typer.Option("--bucket", "-b", help="S3 bucket name")
    ] = DEFAULT_BUCKET,
    every_n: Annotated[
        int,
        typer.Option(
            "--every",
            "-e",
            help="Take every Nth image (e.g., 60 for ~1/min from 1/sec)",
        ),
    ] = 1,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Scan and queue only, don't upload")
    ] = False,
    publish: Annotated[
        bool, typer.Option("--publish", "-p", help="Publish to NATS after upload")
    ] = True,
) -> None:
    """
    Scan a single directory for images and upload to SeaweedFS.

    Only scans the specified directory (non-recursive). Images are processed
    in filename order. Use --every to take every Nth image.

    Example:
        # Upload all images
        publish-trip-images scan /Volumes/Untitled/DCIM/vancouver-to-kamloops

        # Take every 60th image (~1/min from 1/sec captures)
        publish-trip-images scan /Volumes/Untitled/DCIM/vancouver-to-kamloops --every 60

        # Preview what would be selected (dry run)
        publish-trip-images scan /path/to/trip --every 60 --dry-run
    """
    if not source_dir.exists():
        print(f"Error: Directory not found: {source_dir}")
        raise typer.Exit(1)

    asyncio.run(_run_upload(source_dir, db_path, bucket, dry_run, publish, every_n))


@app.command()
def status(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
) -> None:
    """Show upload queue status."""
    if not db_path.exists():
        print("No upload history found")
        return

    queue = UploadQueue(db_path)
    stats = queue.get_stats()

    total = sum(stats.values())
    print(f"Total images: {total}")
    print(f"  Completed:  {stats.get(UploadStatus.COMPLETED.value, 0)}")
    print(f"  Pending:    {stats.get(UploadStatus.PENDING.value, 0)}")
    print(f"  Uploading:  {stats.get(UploadStatus.UPLOADING.value, 0)}")
    print(f"  Failed:     {stats.get(UploadStatus.FAILED.value, 0)}")

    # Show failed records
    pending = queue.get_pending()
    failed = [r for r in pending if r.status == UploadStatus.FAILED]
    if failed:
        print("\nFailed uploads:")
        for r in failed:
            print(f"  #{r.id} {Path(r.source_path).name}: {r.error_message}")


@app.command()
def retry(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
    bucket: Annotated[
        str, typer.Option("--bucket", "-b", help="S3 bucket name")
    ] = DEFAULT_BUCKET,
    publish: Annotated[
        bool, typer.Option("--publish", "-p", help="Publish to NATS after upload")
    ] = True,
) -> None:
    """Retry failed uploads."""
    if not db_path.exists():
        print("No upload history found")
        return

    queue = UploadQueue(db_path)
    pending = queue.get_pending()

    if not pending:
        print("No pending uploads to retry")
        return

    print(f"Retrying {len(pending)} uploads...")
    # Use a dummy source dir since we're only retrying existing records
    asyncio.run(_run_upload(Path("."), db_path, bucket, dry_run=False, publish=publish))


@app.command()
def fix_timestamps(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
) -> None:
    """Fix timestamps by removing incorrect 'Z' suffix (EXIF times are local, not UTC)."""
    if not db_path.exists():
        print("No upload history found")
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE images SET timestamp = REPLACE(timestamp, 'Z', '') WHERE timestamp LIKE '%Z'"
        )
        conn.commit()
        print(f"Fixed {cursor.rowcount} timestamps")


@app.command()
def publish_all(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
) -> None:
    """Publish all completed uploads to NATS (useful for re-sync)."""
    if not db_path.exists():
        print("No upload history found")
        return

    queue = UploadQueue(db_path)
    completed = queue.get_completed()

    if not completed:
        print("No completed uploads to publish")
        return

    async def _publish_all():
        print(f"Publishing {len(completed)} points to NATS...")
        for record in completed:
            try:
                await publish_to_nats(record, record.id)
                print(f"  [NATS] Published point {record.id}")
            except Exception as e:
                print(f"  [FAIL] Point {record.id}: {e}")

    asyncio.run(_publish_all())
    print("Done")


if __name__ == "__main__":
    app()
