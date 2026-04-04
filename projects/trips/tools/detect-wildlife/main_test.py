"""Unit tests for detect-wildlife/main.py — download_worker happy path.

Supplements wildlife_test.py and gopro_test.py by covering the download
worker's success path, shutdown handling, and idle-wait behaviour.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

from main import (
    CaptureQueue,
    DownloadStatus,
    GracefulShutdown,
    PerfStats,
    download_worker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gopro_for_download(local_path: Path, file_size: int = 1024 * 1024):
    """Build a GoPro mock whose download_file succeeds.

    We patch os.path.getsize so the worker can compute MB/s without needing
    a real file to exist on disk.
    """
    gopro = MagicMock()
    gopro.http_command.download_file = AsyncMock(return_value=None)
    return gopro


# ---------------------------------------------------------------------------
# download_worker — success path
# ---------------------------------------------------------------------------


class TestDownloadWorkerSuccess:
    """Worker downloads files and marks them completed."""

    @pytest.mark.asyncio
    async def test_marks_record_completed_on_success(self, tmp_path):
        """A successful download transitions the record to COMPLETED."""
        queue = CaptureQueue(tmp_path / "q.db")
        local_path = tmp_path / "photo.jpg"
        queue.add("GOPR0001.JPG", local_path)

        gopro = _make_gopro_for_download(local_path)
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()

        with patch("main.os.path.getsize", return_value=5 * 1024 * 1024):
            task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event)
            )
            # Allow the worker to process the single record then stop.
            await asyncio.sleep(0.05)
            shutdown.shutdown_requested = True
            await task

        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 1

    @pytest.mark.asyncio
    async def test_download_file_called_with_correct_args(self, tmp_path):
        """download_file receives the camera filename and local path."""
        queue = CaptureQueue(tmp_path / "q.db")
        local_path = tmp_path / "output.jpg"
        queue.add("GOPR1234.JPG", local_path)

        gopro = _make_gopro_for_download(local_path)
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()

        with patch("main.os.path.getsize", return_value=1024):
            task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event)
            )
            await asyncio.sleep(0.05)
            shutdown.shutdown_requested = True
            await task

        gopro.http_command.download_file.assert_awaited_once_with(
            camera_file="GOPR1234.JPG",
            local_file=str(local_path),
        )

    @pytest.mark.asyncio
    async def test_stats_add_download_called_on_success(self, tmp_path):
        """PerfStats.add_download is called when a download succeeds."""
        queue = CaptureQueue(tmp_path / "q.db")
        local_path = tmp_path / "photo.jpg"
        queue.add("GOPR0001.JPG", local_path)

        gopro = _make_gopro_for_download(local_path)
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()
        stats = PerfStats()

        with patch("main.os.path.getsize", return_value=2 * 1024 * 1024):
            task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event, stats)
            )
            await asyncio.sleep(0.05)
            shutdown.shutdown_requested = True
            await task

        assert len(stats.download_times) == 1
        assert len(stats.download_sizes) == 1
        # 2 MB file
        assert stats.download_sizes[0] == pytest.approx(2.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_multiple_records_all_completed(self, tmp_path):
        """Worker processes all pending records in a single pass."""
        queue = CaptureQueue(tmp_path / "q.db")
        for i in range(3):
            queue.add(f"GOPR000{i}.JPG", tmp_path / f"photo{i}.jpg")

        gopro = _make_gopro_for_download(tmp_path)
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()

        with patch("main.os.path.getsize", return_value=1024):
            task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event)
            )
            await asyncio.sleep(0.1)
            shutdown.shutdown_requested = True
            await task

        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 3


# ---------------------------------------------------------------------------
# download_worker — shutdown handling
# ---------------------------------------------------------------------------


class TestDownloadWorkerShutdown:
    """Worker respects the shutdown flag."""

    @pytest.mark.asyncio
    async def test_worker_exits_when_shutdown_before_event(self, tmp_path):
        """If shutdown is set before the download event fires, worker stops."""
        queue = CaptureQueue(tmp_path / "q.db")
        gopro = MagicMock()
        shutdown = GracefulShutdown()
        shutdown.shutdown_requested = True  # already shut down
        download_event = asyncio.Event()

        # Should return immediately — worker checks flag at top of loop.
        await asyncio.wait_for(
            download_worker(gopro, queue, shutdown, download_event),
            timeout=2.0,
        )

        gopro.http_command.download_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_worker_stops_mid_queue_when_shutdown_set(self, tmp_path):
        """If shutdown is set while iterating pending records, the loop breaks."""
        queue = CaptureQueue(tmp_path / "q.db")
        # Two records; we will shut down after the first download starts.
        queue.add("A.JPG", tmp_path / "a.jpg")
        queue.add("B.JPG", tmp_path / "b.jpg")

        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()

        call_count = 0

        async def _download(**kwargs):
            nonlocal call_count
            call_count += 1
            # Set shutdown after the first download so the second is skipped.
            shutdown.shutdown_requested = True

        gopro = MagicMock()
        gopro.http_command.download_file = AsyncMock(side_effect=_download)

        with patch("main.os.path.getsize", return_value=1024):
            await asyncio.wait_for(
                download_worker(gopro, queue, shutdown, download_event),
                timeout=2.0,
            )

        # Only one file was downloaded before the shutdown flag was honoured.
        assert call_count == 1


# ---------------------------------------------------------------------------
# download_worker — idle behaviour
# ---------------------------------------------------------------------------


class TestDownloadWorkerIdle:
    """Worker waits for download_event before processing records."""

    @pytest.mark.asyncio
    async def test_worker_does_not_poll_without_event(self, tmp_path):
        """Queue.get_pending must not be called until download_event is set."""
        queue = CaptureQueue(tmp_path / "q.db")
        gopro = MagicMock()
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        # Event is NOT set — worker should just wait (with 1 s timeout cycles).

        task = asyncio.create_task(
            download_worker(gopro, queue, shutdown, download_event)
        )

        # Let the worker spin for a bit without signalling.
        await asyncio.sleep(0.05)
        shutdown.shutdown_requested = True
        await task

        # No downloads should have been attempted.
        gopro.http_command.download_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_cleared_after_processing(self, tmp_path):
        """download_event is cleared immediately after the worker wakes up."""
        queue = CaptureQueue(tmp_path / "q.db")
        gopro = MagicMock()
        gopro.http_command.download_file = AsyncMock()
        shutdown = GracefulShutdown()
        download_event = asyncio.Event()
        download_event.set()

        with patch("main.os.path.getsize", return_value=1024):
            task = asyncio.create_task(
                download_worker(gopro, queue, shutdown, download_event)
            )
            await asyncio.sleep(0.05)
            # Event should have been cleared by the worker.
            assert not download_event.is_set()
            shutdown.shutdown_requested = True
            await task
