import asyncio
import os
import signal
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from open_gopro import WiredGoPro
from open_gopro.models import constants, proto

# Monkey-patch: SDK hardcodes port 8080, but Hero 13 firmware uses port 80
# See: https://github.com/gopro/OpenGoPro/issues/XXX (port mismatch)
WiredGoPro._BASE_ENDPOINT = "http://{ip}:80/"

# Defaults
OUTPUT_DIR = Path(__file__).parent / "tmp"
DB_PATH = Path(__file__).parent / "capture_queue.db"
TEST_CAPTURE_COUNT = 20
DEFAULT_INTERVAL = 30  # seconds between captures

app = typer.Typer(help="GoPro wildlife detection camera control")


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CaptureRecord:
    id: int
    camera_filename: str
    local_jpg_path: str
    status: DownloadStatus
    retry_count: int
    error_message: str | None
    created_at: str
    completed_at: str | None


class CaptureQueue:
    """Persistent queue for tracking photo captures and downloads."""

    MAX_RETRIES = 3

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_filename TEXT NOT NULL,
                    local_jpg_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON captures(status)
            """)
            conn.commit()

    def add(self, camera_filename: str, local_jpg_path: Path) -> int:
        """Add a new capture to the queue. Returns the record ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO captures (camera_filename, local_jpg_path, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    camera_filename,
                    str(local_jpg_path),
                    DownloadStatus.PENDING.value,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_pending(self) -> list[CaptureRecord]:
        """Get all pending downloads (including retryable failures)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM captures
                WHERE status = ? OR (status = ? AND retry_count < ?)
                ORDER BY created_at ASC
                """,
                (
                    DownloadStatus.PENDING.value,
                    DownloadStatus.FAILED.value,
                    self.MAX_RETRIES,
                ),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def mark_downloading(self, record_id: int) -> None:
        """Mark a record as currently downloading."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE captures SET status = ? WHERE id = ?",
                (DownloadStatus.DOWNLOADING.value, record_id),
            )
            conn.commit()

    def mark_completed(self, record_id: int) -> None:
        """Mark a record as successfully downloaded."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE captures SET status = ?, completed_at = ? WHERE id = ?",
                (DownloadStatus.COMPLETED.value, datetime.now().isoformat(), record_id),
            )
            conn.commit()

    def mark_failed(self, record_id: int, error: str) -> None:
        """Mark a record as failed and increment retry count."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE captures
                SET status = ?, error_message = ?, retry_count = retry_count + 1
                WHERE id = ?
                """,
                (DownloadStatus.FAILED.value, error, record_id),
            )
            conn.commit()

    def reset_downloading(self) -> int:
        """Reset any 'downloading' records to 'pending' (for restart recovery)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE captures SET status = ? WHERE status = ?",
                (DownloadStatus.PENDING.value, DownloadStatus.DOWNLOADING.value),
            )
            conn.commit()
            return cursor.rowcount

    def get_stats(self) -> dict[str, int]:
        """Get count of records by status."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM captures GROUP BY status"
            ).fetchall()
            return {row[0]: row[1] for row in rows}

    def _row_to_record(self, row: sqlite3.Row) -> CaptureRecord:
        return CaptureRecord(
            id=row["id"],
            camera_filename=row["camera_filename"],
            local_jpg_path=row["local_jpg_path"],
            status=DownloadStatus(row["status"]),
            retry_count=row["retry_count"],
            error_message=row["error_message"],
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
        print("\nShutdown requested - finishing current operations...")
        self.shutdown_requested = True


class PerfStats:
    """Track performance statistics for test mode."""

    def __init__(self):
        self.capture_times: list[float] = []
        self.download_times: list[float] = []
        self.download_sizes: list[float] = []  # MB
        self.start_time = time.perf_counter()

    def add_capture(self, duration: float) -> None:
        self.capture_times.append(duration)

    def add_download(self, duration: float, size_mb: float) -> None:
        self.download_times.append(duration)
        self.download_sizes.append(size_mb)

    def summary(self) -> str:
        elapsed = time.perf_counter() - self.start_time
        lines = [
            "",
            "=" * 60,
            "PERFORMANCE SUMMARY",
            "=" * 60,
            f"Total time: {elapsed:.1f}s",
            f"Photos captured: {len(self.capture_times)}",
            f"Photos downloaded: {len(self.download_times)}",
            "",
        ]

        if self.capture_times:
            avg_cap = sum(self.capture_times) / len(self.capture_times)
            min_cap = min(self.capture_times)
            max_cap = max(self.capture_times)
            lines.append(
                f"Capture time: avg={avg_cap:.2f}s min={min_cap:.2f}s max={max_cap:.2f}s"
            )

        if self.download_times:
            avg_dl = sum(self.download_times) / len(self.download_times)
            min_dl = min(self.download_times)
            max_dl = max(self.download_times)
            avg_size = sum(self.download_sizes) / len(self.download_sizes)
            total_size = sum(self.download_sizes)
            throughput = (
                total_size / sum(self.download_times) if self.download_times else 0
            )
            lines.extend(
                [
                    f"Download time: avg={avg_dl:.2f}s min={min_dl:.2f}s max={max_dl:.2f}s",
                    f"File size: avg={avg_size:.1f}MB total={total_size:.1f}MB",
                    f"Throughput: {throughput:.1f} MB/s",
                ]
            )

        if self.capture_times and elapsed > 0:
            rate = len(self.capture_times) / (elapsed / 60)
            lines.append(f"Effective rate: {rate:.1f} photos/min")

        lines.append("=" * 60)
        return "\n".join(lines)


async def configure_gopro(gopro: WiredGoPro, *, test_mode: bool = False) -> None:
    """Configure camera for high-resolution photo capture with RAW."""
    if test_mode:
        print("[DEBUG] Configuring camera...")

    # Set PRO mode (required for full resolution control)
    await gopro.http_setting.control_mode.set(constants.settings.ControlMode.PRO)

    # Load photo preset group
    await gopro.http_command.load_preset_group(
        group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO
    )

    # Set high-resolution lens (27MP wide - required for RAW)
    lens_options = [
        constants.settings.PhotoLens.WIDE_27_MP,
        constants.settings.PhotoLens.WIDE_23_MP,
        constants.settings.PhotoLens.WIDE_12_MP,
    ]
    for lens in lens_options:
        result = await gopro.http_setting.photo_lens.set(lens)
        if result.ok:
            if test_mode:
                print(f"[DEBUG] Lens set to {lens}")
            break

    # Enable RAW mode (GPR files stay on SD card, we only download JPG)
    result = await gopro.http_setting.photo_output.set(
        constants.settings.PhotoOutput.RAW
    )
    if result.ok:
        print("RAW mode enabled (GPR stays on SD, downloading JPG only)")
    else:
        print("Warning: Could not enable RAW mode, using standard")

    # Disable photo interval (single shot mode)
    await gopro.http_setting.photo_single_interval.set(
        constants.settings.PhotoSingleInterval.OFF
    )

    # Enable GPS for location tagging
    result = await gopro.http_setting.gps.set(constants.settings.Gps.ON)
    if result.ok:
        print("GPS enabled")
    else:
        print("Warning: Could not enable GPS")


async def download_worker(
    gopro: WiredGoPro,
    queue: CaptureQueue,
    shutdown: GracefulShutdown,
    download_event: asyncio.Event,
    stats: PerfStats | None = None,
) -> None:
    """Background worker that downloads JPG photos from the queue."""
    while not shutdown.shutdown_requested:
        try:
            await asyncio.wait_for(download_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        download_event.clear()

        pending = queue.get_pending()
        for record in pending:
            if shutdown.shutdown_requested:
                break

            queue.mark_downloading(record.id)

            try:
                t0 = time.perf_counter()
                await gopro.http_command.download_file(
                    camera_file=record.camera_filename,
                    local_file=record.local_jpg_path,
                )
                duration = time.perf_counter() - t0
                size_mb = os.path.getsize(record.local_jpg_path) / 1024 / 1024

                queue.mark_completed(record.id)

                if stats:
                    stats.add_download(duration, size_mb)
                    print(
                        f"  [DL] {record.camera_filename}: {size_mb:.1f}MB in {duration:.1f}s ({size_mb / duration:.1f} MB/s)"
                    )
                else:
                    print(
                        f"  [DL] {Path(record.local_jpg_path).name} ({size_mb:.1f}MB)"
                    )

            except Exception as e:
                error_msg = str(e)
                queue.mark_failed(record.id, error_msg)
                retry_info = f"retry {record.retry_count + 1}/{queue.MAX_RETRIES}"
                print(
                    f"  [DL] Failed {record.camera_filename} ({retry_info}): {error_msg}"
                )

                if record.retry_count < queue.MAX_RETRIES - 1:
                    backoff = 2 ** (record.retry_count + 1)
                    await asyncio.sleep(backoff)


async def capture_photo(
    gopro: WiredGoPro,
    queue: CaptureQueue,
    output_dir: Path,
    media_before: set,
    download_event: asyncio.Event,
    stats: PerfStats | None = None,
) -> tuple[set, float]:
    """Capture a photo and queue JPG for download. Returns (new_media_set, capture_time)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Take photo with retry
    t0 = time.perf_counter()
    for attempt in range(3):
        try:
            await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)
            break
        except Exception as e:
            if attempt < 2:
                print(f"  Shutter busy, retrying in 2s... ({e})")
                await asyncio.sleep(2)
            else:
                raise
    capture_time = time.perf_counter() - t0

    if stats:
        stats.add_capture(capture_time)

    # Wait for camera to finish writing
    await asyncio.sleep(0.5)

    # Find the new photo
    media_after = set((await gopro.http_command.get_media_list()).data.files)
    new_photos = media_after.difference(media_before)

    if not new_photos:
        raise RuntimeError("No new photo captured")

    photo = new_photos.pop()
    jpg_path = output_dir / f"{timestamp}.jpg"

    # Queue JPG for download (RAW stays on SD card)
    record_id = queue.add(photo.filename, jpg_path)
    download_event.set()

    if stats:
        print(f"[CAP] #{record_id} {photo.filename} in {capture_time:.2f}s")
    else:
        print(f"[CAP] {photo.filename}")

    return media_after, capture_time


@asynccontextmanager
async def connect_gopro(test_mode: bool = False):
    """Connect to GoPro with retry logic."""
    gopro = WiredGoPro()
    for attempt in range(5):
        try:
            if test_mode:
                print(f"[DEBUG] Connecting (attempt {attempt + 1}/5)...")
            else:
                print(f"Connecting to camera (attempt {attempt + 1}/5)...")
            await gopro.open(timeout=15, retries=3)
            break
        except Exception as e:
            if attempt < 4:
                print(f"Connection failed: {e}")
                print("Waiting 5s for camera to wake up...")
                await asyncio.sleep(5)
            else:
                print("Failed to connect after 5 attempts.")
                print("Try: unplug USB, wait 5s, plug back in")
                raise

    try:
        yield gopro
    finally:
        await gopro.close()


async def _run(
    output_dir: Path,
    db_path: Path,
    interval: int,
    test_mode: bool,
    max_captures: int | None,
) -> None:
    """Main capture loop."""
    output_dir.mkdir(exist_ok=True)
    queue = CaptureQueue(db_path)
    stats = PerfStats() if test_mode else None

    # Recovery: reset interrupted downloads
    reset_count = queue.reset_downloading()
    if reset_count:
        print(f"Resumed {reset_count} interrupted downloads")

    # Show queue status if there's history
    queue_stats = queue.get_stats()
    if queue_stats:
        pending = queue_stats.get(DownloadStatus.PENDING.value, 0)
        failed = queue_stats.get(DownloadStatus.FAILED.value, 0)
        if pending or failed:
            print(f"Queue: {pending} pending, {failed} failed (will retry)")

    with GracefulShutdown() as shutdown:
        async with connect_gopro(test_mode) as gopro:
            await configure_gopro(gopro, test_mode=test_mode)
            print()

            # Start download worker
            download_event = asyncio.Event()
            download_task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event, stats)
            )

            # Process any pending downloads from previous run
            if queue.get_pending():
                download_event.set()

            captured = 0
            media_set = set((await gopro.http_command.get_media_list()).data.files)

            # Main capture loop
            while not shutdown.shutdown_requested:
                try:
                    captured += 1
                    if max_captures:
                        print(f"\n[{captured}/{max_captures}]")
                    else:
                        print(f"\n[{captured}]")

                    media_set, capture_time = await capture_photo(
                        gopro, queue, output_dir, media_set, download_event, stats
                    )

                except Exception as e:
                    print(f"Capture error: {e}")

                # Check stop conditions
                if max_captures and captured >= max_captures:
                    print(f"\nCompleted {max_captures} test captures")
                    break

                # Wait for next capture (interruptible)
                for _ in range(interval):
                    if shutdown.shutdown_requested:
                        break
                    await asyncio.sleep(1)

            # Drain download queue
            print("\nWaiting for downloads to complete...")
            while queue.get_pending() and not shutdown.shutdown_requested:
                await asyncio.sleep(0.5)

            shutdown.shutdown_requested = True
            await download_task

            # Show stats in test mode
            if stats:
                print(stats.summary())

            # Final status
            final_stats = queue.get_stats()
            failed = final_stats.get(DownloadStatus.FAILED.value, 0)
            if failed:
                print(
                    f"\nWarning: {failed} downloads failed - run 'retry' command to retry"
                )


@app.command()
def run(
    output_dir: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory for photos")
    ] = OUTPUT_DIR,
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to capture queue database")
    ] = DB_PATH,
    interval: Annotated[
        int, typer.Option("--interval", "-i", help="Seconds between captures")
    ] = DEFAULT_INTERVAL,
    test: Annotated[
        bool,
        typer.Option(
            "--test",
            "-t",
            help=f"Test mode: verbose logs, {TEST_CAPTURE_COUNT} captures only",
        ),
    ] = False,
) -> None:
    """
    Run the wildlife camera in continuous capture mode.

    By default, runs forever capturing photos at the specified interval.
    Use --test for a quick test run with performance metrics.
    """
    max_captures = TEST_CAPTURE_COUNT if test else None

    if test:
        print(f"TEST MODE: Capturing {TEST_CAPTURE_COUNT} photos with verbose logging")
    else:
        print(f"Starting continuous capture (interval: {interval}s)")
        print("Press Ctrl+C to stop gracefully, twice to force quit")

    asyncio.run(_run(output_dir, db_path, interval, test, max_captures))


@app.command()
def status(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to capture queue database")
    ] = DB_PATH,
) -> None:
    """Show capture queue status."""
    if not db_path.exists():
        print("No capture history found")
        return

    queue = CaptureQueue(db_path)
    stats = queue.get_stats()

    total = sum(stats.values())
    print(f"Total captures: {total}")
    print(f"  Completed:   {stats.get(DownloadStatus.COMPLETED.value, 0)}")
    print(f"  Pending:     {stats.get(DownloadStatus.PENDING.value, 0)}")
    print(f"  Downloading: {stats.get(DownloadStatus.DOWNLOADING.value, 0)}")
    print(f"  Failed:      {stats.get(DownloadStatus.FAILED.value, 0)}")

    # Show failed records
    pending = queue.get_pending()
    failed = [r for r in pending if r.status == DownloadStatus.FAILED]
    if failed:
        print("\nFailed downloads:")
        for r in failed:
            print(f"  #{r.id} {r.camera_filename}: {r.error_message}")


@app.command()
def retry(
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to capture queue database")
    ] = DB_PATH,
) -> None:
    """Retry failed downloads without capturing new photos."""
    if not db_path.exists():
        print("No capture history found")
        return

    queue = CaptureQueue(db_path)
    pending = queue.get_pending()

    if not pending:
        print("No pending downloads")
        return

    print(f"Retrying {len(pending)} downloads...")
    asyncio.run(_run(OUTPUT_DIR, db_path, interval=30, test_mode=False, max_captures=0))


if __name__ == "__main__":
    app()
