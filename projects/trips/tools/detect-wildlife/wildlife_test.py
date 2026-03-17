"""Tests for the detect-wildlife CaptureQueue, GracefulShutdown, and PerfStats."""

import signal
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from main import (
    CaptureQueue,
    CaptureRecord,
    DownloadStatus,
    GracefulShutdown,
    PerfStats,
)


# ---------------------------------------------------------------------------
# DownloadStatus tests
# ---------------------------------------------------------------------------


class TestDownloadStatus:
    """Enum values and string behaviour."""

    def test_enum_values(self):
        assert DownloadStatus.PENDING.value == "pending"
        assert DownloadStatus.DOWNLOADING.value == "downloading"
        assert DownloadStatus.COMPLETED.value == "completed"
        assert DownloadStatus.FAILED.value == "failed"

    def test_is_str_subclass(self):
        assert isinstance(DownloadStatus.PENDING, str)

    def test_roundtrip_from_value(self):
        assert DownloadStatus("pending") is DownloadStatus.PENDING
        assert DownloadStatus("completed") is DownloadStatus.COMPLETED


# ---------------------------------------------------------------------------
# CaptureQueue — initialisation
# ---------------------------------------------------------------------------


class TestCaptureQueueInit:
    """Database schema is created on construction."""

    def test_creates_captures_table(self, tmp_path):
        db = tmp_path / "q.db"
        CaptureQueue(db)
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='captures'"
            ).fetchall()
        assert len(rows) == 1

    def test_creates_status_index(self, tmp_path):
        db = tmp_path / "q.db"
        CaptureQueue(db)
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_status'"
            ).fetchall()
        assert len(rows) == 1

    def test_idempotent_init(self, tmp_path):
        """CREATE TABLE IF NOT EXISTS must not raise on second construction."""
        db = tmp_path / "q.db"
        CaptureQueue(db)
        CaptureQueue(db)  # should not raise


# ---------------------------------------------------------------------------
# CaptureQueue — add
# ---------------------------------------------------------------------------


class TestCaptureQueueAdd:
    """Adding records to the queue."""

    @pytest.fixture
    def queue(self, tmp_path):
        return CaptureQueue(tmp_path / "q.db")

    def test_returns_integer_id(self, queue, tmp_path):
        record_id = queue.add("GX010001.JPG", tmp_path / "output/img.jpg")
        assert isinstance(record_id, int)
        assert record_id >= 1

    def test_autoincrement_ids(self, queue, tmp_path):
        id1 = queue.add("GX010001.JPG", tmp_path / "a.jpg")
        id2 = queue.add("GX010002.JPG", tmp_path / "b.jpg")
        assert id2 == id1 + 1

    def test_record_starts_as_pending(self, queue, tmp_path):
        queue.add("GX010001.JPG", tmp_path / "img.jpg")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == DownloadStatus.PENDING

    def test_stores_camera_filename(self, queue, tmp_path):
        queue.add("MY_FILE.JPG", tmp_path / "img.jpg")
        pending = queue.get_pending()
        assert pending[0].camera_filename == "MY_FILE.JPG"

    def test_stores_local_path_as_string(self, queue, tmp_path):
        local = tmp_path / "photos" / "img.jpg"
        queue.add("f.JPG", local)
        pending = queue.get_pending()
        assert pending[0].local_jpg_path == str(local)

    def test_multiple_records_all_returned_as_pending(self, queue, tmp_path):
        for i in range(5):
            queue.add(f"GX01000{i}.JPG", tmp_path / f"{i}.jpg")
        assert len(queue.get_pending()) == 5


# ---------------------------------------------------------------------------
# CaptureQueue — state transitions
# ---------------------------------------------------------------------------


class TestCaptureQueueStateTransitions:
    """mark_downloading / mark_completed / mark_failed."""

    @pytest.fixture
    def queue_with_record(self, tmp_path):
        q = CaptureQueue(tmp_path / "q.db")
        record_id = q.add("GX010001.JPG", tmp_path / "img.jpg")
        return q, record_id

    def test_mark_downloading_changes_status(self, queue_with_record):
        q, record_id = queue_with_record
        q.mark_downloading(record_id)
        with sqlite3.connect(q.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM captures WHERE id = ?", (record_id,)
            ).fetchone()
        assert row[0] == DownloadStatus.DOWNLOADING.value

    def test_mark_completed_changes_status(self, queue_with_record):
        q, record_id = queue_with_record
        q.mark_completed(record_id)
        with sqlite3.connect(q.db_path) as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM captures WHERE id = ?", (record_id,)
            ).fetchone()
        assert row[0] == DownloadStatus.COMPLETED.value
        assert row[1] is not None  # completed_at was set

    def test_mark_failed_changes_status_and_stores_error(self, queue_with_record):
        q, record_id = queue_with_record
        q.mark_failed(record_id, "network timeout")
        with sqlite3.connect(q.db_path) as conn:
            row = conn.execute(
                "SELECT status, error_message, retry_count FROM captures WHERE id = ?",
                (record_id,),
            ).fetchone()
        assert row[0] == DownloadStatus.FAILED.value
        assert row[1] == "network timeout"
        assert row[2] == 1  # incremented from 0

    def test_mark_failed_increments_retry_count_each_time(self, queue_with_record):
        q, record_id = queue_with_record
        q.mark_failed(record_id, "err1")
        q.mark_failed(record_id, "err2")
        with sqlite3.connect(q.db_path) as conn:
            row = conn.execute(
                "SELECT retry_count FROM captures WHERE id = ?", (record_id,)
            ).fetchone()
        assert row[0] == 2


# ---------------------------------------------------------------------------
# CaptureQueue — get_pending
# ---------------------------------------------------------------------------


class TestCaptureQueueGetPending:
    """get_pending includes PENDING and retryable FAILED, not COMPLETED."""

    @pytest.fixture
    def queue(self, tmp_path):
        return CaptureQueue(tmp_path / "q.db")

    def test_empty_queue_returns_empty_list(self, queue):
        assert queue.get_pending() == []

    def test_pending_record_returned(self, queue, tmp_path):
        queue.add("f.JPG", tmp_path / "img.jpg")
        assert len(queue.get_pending()) == 1

    def test_completed_record_not_returned(self, queue, tmp_path):
        record_id = queue.add("f.JPG", tmp_path / "img.jpg")
        queue.mark_completed(record_id)
        assert queue.get_pending() == []

    def test_failed_record_within_retry_limit_returned(self, queue, tmp_path):
        record_id = queue.add("f.JPG", tmp_path / "img.jpg")
        # Mark failed once — retry_count = 1, MAX_RETRIES = 3, so still eligible
        queue.mark_failed(record_id, "err")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == DownloadStatus.FAILED

    def test_failed_record_at_max_retries_not_returned(self, queue, tmp_path):
        record_id = queue.add("f.JPG", tmp_path / "img.jpg")
        # Exhaust retries
        for i in range(CaptureQueue.MAX_RETRIES):
            queue.mark_failed(record_id, f"err{i}")
        assert queue.get_pending() == []

    def test_results_ordered_by_created_at_asc(self, queue, tmp_path):
        id1 = queue.add("first.JPG", tmp_path / "1.jpg")
        id2 = queue.add("second.JPG", tmp_path / "2.jpg")
        pending = queue.get_pending()
        assert pending[0].id == id1
        assert pending[1].id == id2


# ---------------------------------------------------------------------------
# CaptureQueue — reset_downloading
# ---------------------------------------------------------------------------


class TestCaptureQueueResetDownloading:
    """Recovery: interrupted downloads reset to pending."""

    @pytest.fixture
    def queue(self, tmp_path):
        return CaptureQueue(tmp_path / "q.db")

    def test_downloading_records_reset_to_pending(self, queue, tmp_path):
        record_id = queue.add("f.JPG", tmp_path / "img.jpg")
        queue.mark_downloading(record_id)
        count = queue.reset_downloading()
        assert count == 1
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == DownloadStatus.PENDING

    def test_returns_number_of_records_reset(self, queue, tmp_path):
        ids = [queue.add(f"f{i}.JPG", tmp_path / f"{i}.jpg") for i in range(3)]
        for rid in ids:
            queue.mark_downloading(rid)
        count = queue.reset_downloading()
        assert count == 3

    def test_no_downloading_records_returns_zero(self, queue, tmp_path):
        queue.add("f.JPG", tmp_path / "img.jpg")  # stays PENDING
        assert queue.reset_downloading() == 0

    def test_completed_records_not_affected(self, queue, tmp_path):
        record_id = queue.add("f.JPG", tmp_path / "img.jpg")
        queue.mark_completed(record_id)
        queue.reset_downloading()
        # Completed record should not reappear as pending
        assert queue.get_pending() == []


# ---------------------------------------------------------------------------
# CaptureQueue — get_stats
# ---------------------------------------------------------------------------


class TestCaptureQueueGetStats:
    """Status count aggregation."""

    @pytest.fixture
    def queue(self, tmp_path):
        return CaptureQueue(tmp_path / "q.db")

    def test_empty_queue_returns_empty_dict(self, queue):
        assert queue.get_stats() == {}

    def test_counts_by_status(self, queue, tmp_path):
        id1 = queue.add("a.JPG", tmp_path / "a.jpg")
        id2 = queue.add("b.JPG", tmp_path / "b.jpg")
        queue.add("c.JPG", tmp_path / "c.jpg")
        queue.mark_completed(id1)
        queue.mark_failed(id2, "err")

        stats = queue.get_stats()
        assert stats[DownloadStatus.COMPLETED.value] == 1
        assert stats[DownloadStatus.FAILED.value] == 1
        assert stats[DownloadStatus.PENDING.value] == 1

    def test_returns_only_present_statuses(self, queue, tmp_path):
        queue.add("a.JPG", tmp_path / "a.jpg")
        stats = queue.get_stats()
        assert DownloadStatus.COMPLETED.value not in stats


# ---------------------------------------------------------------------------
# CaptureQueue — _row_to_record
# ---------------------------------------------------------------------------


class TestCaptureQueueRowToRecord:
    """Round-trip: add a record and verify all fields come back intact."""

    def test_full_roundtrip(self, tmp_path):
        queue = CaptureQueue(tmp_path / "q.db")
        record_id = queue.add("GX010099.JPG", tmp_path / "out.jpg")
        pending = queue.get_pending()
        assert len(pending) == 1
        r = pending[0]
        assert isinstance(r, CaptureRecord)
        assert r.id == record_id
        assert r.camera_filename == "GX010099.JPG"
        assert r.local_jpg_path == str(tmp_path / "out.jpg")
        assert r.status == DownloadStatus.PENDING
        assert r.retry_count == 0
        assert r.error_message is None
        assert r.created_at is not None
        assert r.completed_at is None


# ---------------------------------------------------------------------------
# GracefulShutdown tests
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    """Signal handling context manager."""

    def test_initial_state_is_not_requested(self):
        gs = GracefulShutdown()
        assert gs.shutdown_requested is False

    def test_context_manager_restores_signals(self):
        original_sigint = signal.getsignal(signal.SIGINT)
        with GracefulShutdown():
            pass
        assert signal.getsignal(signal.SIGINT) is original_sigint

    def test_handler_sets_shutdown_requested(self):
        with GracefulShutdown() as gs:
            # Simulate receiving SIGINT by calling the handler directly
            gs._handler(signal.SIGINT, None)
            assert gs.shutdown_requested is True

    def test_second_signal_raises_system_exit(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGINT, None)  # first signal
            with pytest.raises(SystemExit):
                gs._handler(signal.SIGINT, None)  # second signal

    def test_sigterm_also_sets_shutdown_requested(self):
        with GracefulShutdown() as gs:
            gs._handler(signal.SIGTERM, None)
            assert gs.shutdown_requested is True

    def test_enter_returns_self(self):
        gs = GracefulShutdown()
        with gs as ctx:
            assert ctx is gs


# ---------------------------------------------------------------------------
# PerfStats tests
# ---------------------------------------------------------------------------


class TestPerfStats:
    """Performance statistics tracker."""

    def test_initial_lists_are_empty(self):
        stats = PerfStats()
        assert stats.capture_times == []
        assert stats.download_times == []
        assert stats.download_sizes == []

    def test_add_capture_appends_duration(self):
        stats = PerfStats()
        stats.add_capture(1.5)
        stats.add_capture(2.0)
        assert stats.capture_times == [1.5, 2.0]

    def test_add_download_appends_duration_and_size(self):
        stats = PerfStats()
        stats.add_download(3.0, 5.5)
        assert stats.download_times == [3.0]
        assert stats.download_sizes == [5.5]

    def test_summary_empty_stats(self):
        stats = PerfStats()
        summary = stats.summary()
        assert "PERFORMANCE SUMMARY" in summary
        assert "Photos captured: 0" in summary
        assert "Photos downloaded: 0" in summary

    def test_summary_with_captures(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        stats.add_capture(3.0)
        summary = stats.summary()
        assert "Capture time:" in summary
        assert "avg=2.00s" in summary
        assert "min=1.00s" in summary
        assert "max=3.00s" in summary

    def test_summary_with_downloads(self):
        stats = PerfStats()
        stats.add_download(2.0, 10.0)
        stats.add_download(4.0, 20.0)
        summary = stats.summary()
        assert "Download time:" in summary
        assert "avg=3.00s" in summary
        assert "File size:" in summary
        assert "total=30.0MB" in summary

    def test_summary_includes_throughput(self):
        stats = PerfStats()
        stats.add_download(2.0, 10.0)
        summary = stats.summary()
        assert "Throughput:" in summary
        assert "MB/s" in summary

    def test_summary_includes_effective_rate_with_captures(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        summary = stats.summary()
        assert "Effective rate:" in summary
        assert "photos/min" in summary

    def test_summary_no_download_stats_without_downloads(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        summary = stats.summary()
        assert "Download time:" not in summary

    def test_summary_separator_lines(self):
        stats = PerfStats()
        summary = stats.summary()
        assert "=" * 60 in summary

    def test_throughput_calculation(self):
        """10 MB / 2 s = 5 MB/s."""
        stats = PerfStats()
        stats.add_download(2.0, 10.0)
        summary = stats.summary()
        assert "5.0 MB/s" in summary
