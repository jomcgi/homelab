"""Tests for the _tick branch where session.get(ScheduledJob, job_name) returns None."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

from shared.scheduler import (
    ScheduledJob,
    _complete_job,
    _fail_job,
    _registry,
    _release_lock,
    _tick,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure a clean handler registry for each test."""
    _registry.clear()
    yield
    _registry.clear()


class TestTickMissingJob:
    @pytest.mark.asyncio
    async def test_returns_early_when_job_row_not_found(self):
        """When _claim_next_job returns a name but session.get returns None, _tick returns early
        without calling any of _complete_job, _fail_job, or _release_lock."""
        handler = AsyncMock()
        _registry["ghost-job"] = handler

        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None  # job row disappeared after claiming

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value="ghost-job"),
            patch("shared.scheduler._complete_job") as mock_complete,
            patch("shared.scheduler._fail_job") as mock_fail,
            patch("shared.scheduler._release_lock") as mock_release,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await _tick()

        # The row vanished — no state transitions should occur
        mock_complete.assert_not_called()
        mock_fail.assert_not_called()
        mock_release.assert_not_called()
        # Handler should not run either
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_when_job_row_missing(self):
        """_tick with a missing job row must not propagate any exception."""
        mock_session = MagicMock(spec=Session)
        mock_session.get.return_value = None

        with (
            patch("shared.scheduler.get_engine"),
            patch("shared.scheduler.Session") as mock_session_cls,
            patch("shared.scheduler._claim_next_job", return_value="no-such-job"),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should complete silently
            await _tick()
