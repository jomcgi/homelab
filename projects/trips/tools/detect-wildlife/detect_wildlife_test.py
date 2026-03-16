"""Tests for detect-wildlife/main.py."""

import signal
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import (
    CaptureQueue,
    CaptureRecord,
    DownloadStatus,
    GracefulShutdown,
    PerfStats,
)


# ---------------------------------------------------------------------------
# TestCaptureQueue
# ---------------------------------------------------------------------------


class TestCaptureQueue:
    @pytest.fixture
    def queue(self, tmp_path):
        return CaptureQueue(tmp_path / "test_queue.db")

    def test_add_returns_row_id(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "out" / "photo.jpg")
        assert isinstance(rid, int)
        assert rid > 0

    def test_add_multiple_returns_incrementing_ids(self, queue, tmp_path):
        id1 = queue.add("A.JPG", tmp_path / "a.jpg")
        id2 = queue.add("B.JPG", tmp_path / "b.jpg")
        assert id2 > id1

    def test_new_record_is_pending(self, queue, tmp_path):
        queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == DownloadStatus.PENDING

    def test_get_pending_excludes_completed(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_completed(rid)
        assert queue.get_pending() == []

    def test_get_pending_excludes_downloading(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_downloading(rid)
        pending = queue.get_pending()
        # Downloading is in-progress; not returned as pending
        assert all(r.id != rid for r in pending)

    def test_get_pending_includes_retryable_failures(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_failed(rid, "network error")
        pending = queue.get_pending()
        assert any(r.id == rid for r in pending)

    def test_get_pending_excludes_exhausted_failures(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        # Exhaust all retries
        for _ in range(CaptureQueue.MAX_RETRIES):
            queue.mark_failed(rid, "persistent error")
        pending = queue.get_pending()
        assert all(r.id != rid for r in pending)

    def test_mark_completed_sets_completed_at(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_completed(rid)
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 1

    def test_mark_failed_increments_retry_count(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_failed(rid, "error 1")
        queue.mark_failed(rid, "error 2")
        # Check retry_count via get_pending
        pending = queue.get_pending()
        record = next(r for r in pending if r.id == rid)
        assert record.retry_count == 2

    def test_mark_failed_stores_error_message(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_failed(rid, "connection refused")
        pending = queue.get_pending()
        record = next(r for r in pending if r.id == rid)
        assert record.error_message == "connection refused"

    def test_reset_downloading_returns_count(self, queue, tmp_path):
        rid1 = queue.add("A.JPG", tmp_path / "a.jpg")
        rid2 = queue.add("B.JPG", tmp_path / "b.jpg")
        queue.mark_downloading(rid1)
        queue.mark_downloading(rid2)
        count = queue.reset_downloading()
        assert count == 2

    def test_reset_downloading_moves_to_pending(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_downloading(rid)
        queue.reset_downloading()
        pending = queue.get_pending()
        assert any(r.id == rid for r in pending)

    def test_reset_downloading_does_not_affect_completed(self, queue, tmp_path):
        rid = queue.add("GOPR0001.JPG", tmp_path / "photo.jpg")
        queue.mark_completed(rid)
        queue.reset_downloading()
        assert queue.get_stats().get(DownloadStatus.COMPLETED.value, 0) == 1

    def test_get_stats_empty_db(self, queue):
        stats = queue.get_stats()
        assert stats == {}

    def test_get_stats_counts_by_status(self, queue, tmp_path):
        rid1 = queue.add("A.JPG", tmp_path / "a.jpg")
        rid2 = queue.add("B.JPG", tmp_path / "b.jpg")
        rid3 = queue.add("C.JPG", tmp_path / "c.jpg")
        queue.mark_completed(rid1)
        queue.mark_failed(rid2, "err")
        # rid3 stays pending
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 1
        assert stats.get(DownloadStatus.FAILED.value, 0) == 1
        assert stats.get(DownloadStatus.PENDING.value, 0) == 1

    def test_schema_created_on_init(self, tmp_path):
        db_path = tmp_path / "new.db"
        CaptureQueue(db_path)
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "captures" in tables

    def test_second_init_is_idempotent(self, tmp_path):
        """Calling CaptureQueue twice on same DB should not error."""
        db_path = tmp_path / "idempotent.db"
        CaptureQueue(db_path)
        CaptureQueue(db_path)  # Should not raise

    def test_ordered_by_created_at_ascending(self, queue, tmp_path):
        """get_pending returns records in insertion order."""
        ids = [queue.add(f"IMG_{i}.JPG", tmp_path / f"{i}.jpg") for i in range(5)]
        pending = queue.get_pending()
        assert [r.id for r in pending] == ids


# ---------------------------------------------------------------------------
# TestGracefulShutdown
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    def test_initial_state_not_requested(self):
        gs = GracefulShutdown()
        assert gs.shutdown_requested is False

    def test_context_manager_restores_handlers(self):
        """Signals should be restored when exiting the context manager."""
        original_sigint = signal.getsignal(signal.SIGINT)
        with GracefulShutdown():
            pass  # enters and exits cleanly
        assert signal.getsignal(signal.SIGINT) is original_sigint

    def test_first_signal_sets_flag(self):
        with GracefulShutdown() as gs:
            # Simulate a SIGINT
            gs._handler(signal.SIGINT, None)
            assert gs.shutdown_requested is True

    def test_second_signal_raises_system_exit(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGINT, None)  # first — sets flag
            with pytest.raises(SystemExit):
                gs._handler(signal.SIGINT, None)  # second — force quit


# ---------------------------------------------------------------------------
# TestPerfStats
# ---------------------------------------------------------------------------


class TestPerfStats:
    def test_summary_with_no_data(self):
        stats = PerfStats()
        summary = stats.summary()
        assert "PERFORMANCE SUMMARY" in summary
        assert "Photos captured: 0" in summary
        assert "Photos downloaded: 0" in summary

    def test_add_capture_increments_count(self):
        stats = PerfStats()
        stats.add_capture(1.5)
        stats.add_capture(2.0)
        assert len(stats.capture_times) == 2

    def test_add_download_increments_count(self):
        stats = PerfStats()
        stats.add_download(3.0, 4.5)
        assert len(stats.download_times) == 1
        assert len(stats.download_sizes) == 1

    def test_summary_includes_capture_stats(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        stats.add_capture(3.0)
        summary = stats.summary()
        assert "Capture time:" in summary
        assert "avg=2.00s" in summary
        assert "min=1.00s" in summary
        assert "max=3.00s" in summary

    def test_summary_includes_download_stats(self):
        stats = PerfStats()
        stats.add_download(2.0, 10.0)
        stats.add_download(4.0, 20.0)
        summary = stats.summary()
        assert "Download time:" in summary
        assert "File size:" in summary
        assert "Throughput:" in summary

    def test_summary_shows_photos_captured_count(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        stats.add_capture(1.5)
        stats.add_capture(0.8)
        summary = stats.summary()
        assert "Photos captured: 3" in summary

    def test_summary_shows_photos_downloaded_count(self):
        stats = PerfStats()
        stats.add_download(2.0, 5.0)
        summary = stats.summary()
        assert "Photos downloaded: 1" in summary

    def test_throughput_calculation(self):
        stats = PerfStats()
        # 10 MB in 2 seconds = 5 MB/s
        stats.add_download(2.0, 10.0)
        summary = stats.summary()
        assert "5.0 MB/s" in summary

    def test_effective_rate_shown_when_captures_exist(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        summary = stats.summary()
        assert "Effective rate:" in summary
        assert "photos/min" in summary
