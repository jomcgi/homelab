import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from .scheduler import TZ


@pytest.mark.asyncio
async def test_scheduler_calculates_next_midnight():
    """Verify scheduler sleeps until next midnight Pacific."""
    from .scheduler import run_scheduler

    mock_now = datetime(2026, 3, 28, 22, 0, 0, tzinfo=TZ)

    with (
        patch("projects.nexus.backend.todo.scheduler.datetime") as mock_dt,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("projects.nexus.backend.todo.scheduler._archive_and_reset"),
    ):
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await run_scheduler()

        sleep_seconds = mock_sleep.call_args_list[0][0][0]
        assert 7100 < sleep_seconds < 7300  # ~2 hours
