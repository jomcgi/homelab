"""Tests for _log_backfill_exception callback in chat router."""

import logging
from unittest.mock import MagicMock

from chat.router import _log_backfill_exception


class TestLogBackfillException:
    def test_logs_exception_when_task_has_one(self, caplog):
        """Task with unhandled exception logs an error with exc_info."""
        exc = RuntimeError("backfill exploded")
        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = exc

        with caplog.at_level(logging.ERROR, logger="chat.router"):
            _log_backfill_exception(task)

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.ERROR
        assert "Backfill task failed" in record.message
        assert record.exc_info[1] is exc

    def test_does_nothing_when_task_has_no_exception(self, caplog):
        """Task that completed successfully does not log anything."""
        task = MagicMock()
        task.cancelled.return_value = False
        task.exception.return_value = None

        with caplog.at_level(logging.ERROR, logger="chat.router"):
            _log_backfill_exception(task)

        assert caplog.records == []

    def test_does_nothing_when_task_is_cancelled(self, caplog):
        """Cancelled task does not log anything (no exception check)."""
        task = MagicMock()
        task.cancelled.return_value = True

        with caplog.at_level(logging.ERROR, logger="chat.router"):
            _log_backfill_exception(task)

        assert caplog.records == []
        # exception() should never be called on a cancelled task
        task.exception.assert_not_called()
