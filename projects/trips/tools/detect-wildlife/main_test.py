"""Tests for detect-wildlife main.py (CaptureQueue, GracefulShutdown, PerfStats)."""

import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import CaptureQueue, CaptureRecord, DownloadStatus, GracefulShutdown, PerfStats


# ---------------------------------------------------------------------------
# TestDownloadStatus
# ---------------------------------------------------------------------------


class TestDownloadStatus:
    def test_all_expected_values_exist(self):
        assert DownloadStatus.PENDING == "pending"
        assert DownloadStatus.DOWNLOADING == "downloading"
        assert DownloadStatus.COMPLETED == "completed"
        assert DownloadStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# TestCaptureQueue
# ---------------------------------------------------------------------------


class TestCaptureQueue:
    @pytest.fixture
    def queue(self, tmp_path) -> CaptureQueue:
        return CaptureQueue(tmp_path / "test_queue.db")

    def test_init_creates_database(self, tmp_path):
        db = tmp_path / "queue.db"
        CaptureQueue(db)
        assert db.exists()

    def test_add_returns_sequential_ids(self, queue, tmp_path):
        id1 = queue.add("GOPR0001.JPG", tmp_path / "out1.jpg")
        id2 = queue.add("GOPR0002.JPG", tmp_path / "out2.jpg")
        assert id2 > id1

    def test_add_stores_pending_status(self, queue, tmp_path):
        queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.PENDING.value, 0) == 1

    def test_get_pending_returns_pending_records(self, queue, tmp_path):
        queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == DownloadStatus.PENDING
        assert pending[0].camera_filename == "GOPR0001.JPG"

    def test_get_pending_excludes_completed(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_completed(record_id)
        pending = queue.get_pending()
        assert pending == []

    def test_get_pending_excludes_exceeded_retry_count(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        # Mark failed MAX_RETRIES times
        for _ in range(CaptureQueue.MAX_RETRIES):
            queue.mark_failed(record_id, "error")
        pending = queue.get_pending()
        assert pending == []

    def test_get_pending_includes_retryable_failures(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_failed(record_id, "transient error")
        pending = queue.get_pending()
        # Should still be returned since retry_count < MAX_RETRIES
        assert len(pending) == 1

    def test_mark_downloading_updates_status(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_downloading(record_id)
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.DOWNLOADING.value, 0) == 1

    def test_mark_completed_updates_status(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_completed(record_id)
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 1

    def test_mark_failed_increments_retry_count(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_failed(record_id, "network error")
        queue.mark_failed(record_id, "network error again")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 2

    def test_mark_failed_stores_error_message(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_failed(record_id, "timeout: 30s exceeded")
        pending = queue.get_pending()
        assert pending[0].error_message == "timeout: 30s exceeded"

    def test_reset_downloading_returns_to_pending(self, queue, tmp_path):
        record_id = queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        queue.mark_downloading(record_id)
        reset_count = queue.reset_downloading()
        assert reset_count == 1
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.PENDING.value, 0) == 1

    def test_reset_downloading_returns_count(self, queue, tmp_path):
        id1 = queue.add("GOPR0001.JPG", tmp_path / "out1.jpg")
        id2 = queue.add("GOPR0002.JPG", tmp_path / "out2.jpg")
        queue.mark_downloading(id1)
        queue.mark_downloading(id2)
        reset_count = queue.reset_downloading()
        assert reset_count == 2

    def test_reset_downloading_no_downloading_records(self, queue, tmp_path):
        queue.add("GOPR0001.JPG", tmp_path / "out.jpg")
        reset_count = queue.reset_downloading()
        assert reset_count == 0

    def test_get_stats_empty_queue(self, queue):
        stats = queue.get_stats()
        assert stats == {}

    def test_get_stats_reflects_all_statuses(self, queue, tmp_path):
        id1 = queue.add("GOPR0001.JPG", tmp_path / "out1.jpg")
        id2 = queue.add("GOPR0002.JPG", tmp_path / "out2.jpg")
        id3 = queue.add("GOPR0003.JPG", tmp_path / "out3.jpg")
        queue.mark_completed(id1)
        queue.mark_failed(id2, "error")
        # id3 stays pending
        stats = queue.get_stats()
        assert stats.get(DownloadStatus.COMPLETED.value, 0) == 1
        assert stats.get(DownloadStatus.FAILED.value, 0) == 1
        assert stats.get(DownloadStatus.PENDING.value, 0) == 1

    def test_get_pending_ordered_by_created_at(self, queue, tmp_path):
        """Pending records should be returned in insertion order."""
        queue.add("GOPR0001.JPG", tmp_path / "out1.jpg")
        queue.add("GOPR0002.JPG", tmp_path / "out2.jpg")
        pending = queue.get_pending()
        assert pending[0].camera_filename == "GOPR0001.JPG"
        assert pending[1].camera_filename == "GOPR0002.JPG"

    def test_max_retries_constant(self):
        assert CaptureQueue.MAX_RETRIES == 3


# ---------------------------------------------------------------------------
# TestGracefulShutdown
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    def test_shutdown_starts_false(self):
        gs = GracefulShutdown()
        assert gs.shutdown_requested is False

    def test_context_manager_installs_handlers(self):
        gs = GracefulShutdown()
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        with gs:
            # Handlers should be replaced
            assert signal.getsignal(signal.SIGINT) is not original_sigint
            assert signal.getsignal(signal.SIGTERM) is not original_sigterm

    def test_context_manager_restores_handlers(self):
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        gs = GracefulShutdown()
        with gs:
            pass

        assert signal.getsignal(signal.SIGINT) is original_sigint
        assert signal.getsignal(signal.SIGTERM) is original_sigterm

    def test_signal_sets_shutdown_flag(self):
        gs = GracefulShutdown()
        with gs:
            gs._handler(signal.SIGINT, None)
            assert gs.shutdown_requested is True

    def test_double_signal_raises_system_exit(self):
        gs = GracefulShutdown()
        with gs:
            gs._handler(signal.SIGINT, None)  # First: set flag
            with pytest.raises(SystemExit):
                gs._handler(signal.SIGINT, None)  # Second: force quit


# ---------------------------------------------------------------------------
# TestPerfStats
# ---------------------------------------------------------------------------


class TestPerfStats:
    def test_initial_state_empty(self):
        stats = PerfStats()
        assert stats.capture_times == []
        assert stats.download_times == []
        assert stats.download_sizes == []

    def test_add_capture_stores_duration(self):
        stats = PerfStats()
        stats.add_capture(1.5)
        stats.add_capture(2.0)
        assert stats.capture_times == [1.5, 2.0]

    def test_add_download_stores_duration_and_size(self):
        stats = PerfStats()
        stats.add_download(3.0, 5.2)
        assert stats.download_times == [3.0]
        assert stats.download_sizes == [5.2]

    def test_summary_with_no_data(self):
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
        assert "avg=2.00s" in summary
        assert "min=1.00s" in summary
        assert "max=3.00s" in summary

    def test_summary_with_downloads(self):
        stats = PerfStats()
        stats.add_download(2.0, 4.0)
        summary = stats.summary()
        assert "Download time:" in summary
        assert "File size:" in summary
        assert "Throughput:" in summary

    def test_summary_shows_total_time(self):
        stats = PerfStats()
        summary = stats.summary()
        assert "Total time:" in summary

    def test_summary_shows_photos_captured(self):
        stats = PerfStats()
        stats.add_capture(1.0)
        stats.add_capture(2.0)
        summary = stats.summary()
        assert "Photos captured: 2" in summary

    def test_summary_shows_photos_downloaded(self):
        stats = PerfStats()
        stats.add_download(1.0, 2.0)
        stats.add_download(2.0, 3.0)
        summary = stats.summary()
        assert "Photos downloaded: 2" in summary

    def test_summary_single_capture_min_max_equal(self):
        stats = PerfStats()
        stats.add_capture(2.5)
        summary = stats.summary()
        assert "min=2.50s" in summary
        assert "max=2.50s" in summary

    def test_effective_rate_computed_with_captures(self):
        """Rate line should appear when there are captures."""
        stats = PerfStats()
        stats.add_capture(1.0)
        summary = stats.summary()
        assert "Effective rate:" in summary

    def test_summary_no_rate_when_no_captures(self):
        stats = PerfStats()
        summary = stats.summary()
        assert "Effective rate:" not in summary
