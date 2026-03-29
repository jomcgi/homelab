import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from . import scheduler

TZ = ZoneInfo("America/Los_Angeles")


@pytest.mark.asyncio
async def test_scheduler_calculates_next_midnight():
    """Verify scheduler sleeps until next midnight Pacific."""
    mock_now = datetime(2026, 3, 28, 22, 0, 0, tzinfo=TZ)
    expected_midnight = datetime.combine(
        mock_now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
    )
    expected_sleep = (expected_midnight - mock_now).total_seconds()

    with (
        patch.object(scheduler, "datetime") as mock_dt,
        patch.object(scheduler, "asyncio") as mock_asyncio,
        patch.object(scheduler, "_archive_and_reset"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        mock_asyncio.sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_scheduler()

        sleep_seconds = mock_asyncio.sleep.call_args_list[0][0][0]
        assert abs(sleep_seconds - expected_sleep) < 10  # ~7200s (2 hours)
