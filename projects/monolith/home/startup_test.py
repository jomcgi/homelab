from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from home import service

TZ = ZoneInfo("America/Vancouver")


@pytest.mark.asyncio
async def test_daily_reset_handler_calls_archive_and_reset():
    """On a Tuesday, archive_and_reset is called with weekly_reset=False and next midnight is returned."""
    # 2026-03-31 is a Tuesday (weekday 1)
    mock_now = datetime(2026, 3, 31, 0, 5, 0, tzinfo=TZ)
    expected_midnight = datetime.combine(
        mock_now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
    )

    session = MagicMock()

    with patch.object(service, "datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        with patch.object(service, "archive_and_reset") as mock_reset:
            result = await service.daily_reset_handler(session)

    mock_reset.assert_called_once_with(session, weekly_reset=False)
    assert result == expected_midnight


@pytest.mark.asyncio
async def test_daily_reset_handler_weekly_on_monday():
    """On Monday, archive_and_reset is called with weekly_reset=True."""
    # 2026-03-30 is a Monday (weekday 0)
    mock_now = datetime(2026, 3, 30, 0, 5, 0, tzinfo=TZ)

    session = MagicMock()

    with patch.object(service, "datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.combine = datetime.combine

        with patch.object(service, "archive_and_reset") as mock_reset:
            result = await service.daily_reset_handler(session)

    mock_reset.assert_called_once_with(session, weekly_reset=True)
    expected_midnight = datetime.combine(
        mock_now.date() + timedelta(days=1), time(0, 0), tzinfo=TZ
    )
    assert result == expected_midnight


def test_on_startup_registers_job():
    """on_startup calls register_job with the correct arguments."""
    session = MagicMock()

    with patch("shared.scheduler.register_job") as mock_register:
        service.on_startup(session)

    mock_register.assert_called_once_with(
        session,
        name="home.daily_reset",
        interval_secs=86400,
        handler=service.daily_reset_handler,
        ttl_secs=600,
    )
