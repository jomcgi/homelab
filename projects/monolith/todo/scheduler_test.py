import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from todo import scheduler

TZ = ZoneInfo("America/Vancouver")


@pytest.mark.asyncio
async def test_scheduler_calculates_next_midnight():
    """Verify scheduler sleeps until next midnight Vancouver time."""
    mock_now = datetime(2026, 3, 28, 22, 0, 0, tzinfo=TZ)
    expected_midnight = datetime.combine(
        mock_now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
    )
    expected_sleep = (expected_midnight - mock_now).total_seconds()

    with (
        patch.object(scheduler, "datetime") as mock_dt,
        patch.object(scheduler, "asyncio") as mock_asyncio,
        patch.object(scheduler, "archive_and_reset"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler()

        sleep_seconds = mock_asyncio.sleep.call_args_list[0][0][0]
        assert abs(sleep_seconds - expected_sleep) < 10  # ~7200s (2 hours)


@pytest.mark.asyncio
async def test_scheduler_exception_is_caught_and_loop_continues():
    """Exception inside the reset block is caught; the scheduler continues to the next cycle."""
    # Saturday 2026-03-28 at 22:00 — weekday 5, so daily reset
    mock_now = datetime(2026, 3, 28, 22, 0, 0, tzinfo=TZ)

    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(scheduler, "datetime") as mock_dt,
        patch.object(scheduler, "asyncio") as mock_asyncio,
        patch.object(
            scheduler,
            "archive_and_reset",
            side_effect=RuntimeError("DB connection failed"),
        ),
        patch.object(scheduler, "Session", return_value=mock_session_cm),
        patch.object(scheduler, "get_engine"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        # First sleep succeeds (reset runs, exception is caught), second raises CancelledError
        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler()

        # The loop must have continued past the exception into the second sleep call
        assert mock_asyncio.sleep.call_count == 2


@pytest.mark.asyncio
async def test_scheduler_triggers_weekly_reset_on_monday():
    """When the reset fires on a Monday, archive_and_reset is called with weekly_reset=True."""
    # 2026-03-30 is a Monday (weekday 0)
    mock_now = datetime(2026, 3, 30, 0, 0, 1, tzinfo=TZ)

    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(scheduler, "datetime") as mock_dt,
        patch.object(scheduler, "asyncio") as mock_asyncio,
        patch.object(scheduler, "archive_and_reset") as mock_reset,
        patch.object(scheduler, "Session", return_value=mock_session_cm),
        patch.object(scheduler, "get_engine"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler()

        mock_reset.assert_called_once_with(ANY, weekly_reset=True)


@pytest.mark.asyncio
async def test_scheduler_triggers_daily_reset_on_non_monday():
    """On a non-Monday, archive_and_reset is called with weekly_reset=False."""
    # 2026-03-31 is a Tuesday (weekday 1)
    mock_now = datetime(2026, 3, 31, 0, 0, 1, tzinfo=TZ)

    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(scheduler, "datetime") as mock_dt,
        patch.object(scheduler, "asyncio") as mock_asyncio,
        patch.object(scheduler, "archive_and_reset") as mock_reset,
        patch.object(scheduler, "Session", return_value=mock_session_cm),
        patch.object(scheduler, "get_engine"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler()

        mock_reset.assert_called_once_with(ANY, weekly_reset=False)
