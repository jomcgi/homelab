"""Tests for calendar_poll_handler() and on_startup() in shared/service.py.

calendar_poll_handler() is a scheduler handler that delegates to
poll_calendar() and always returns None (no next_run_at override).

on_startup() wires calendar_poll_handler into the distributed scheduler with
a 15-minute interval and a 120-second TTL.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.service import calendar_poll_handler, on_startup


# ---------------------------------------------------------------------------
# calendar_poll_handler
# ---------------------------------------------------------------------------


class TestCalendarPollHandler:
    @pytest.mark.asyncio
    async def test_calls_poll_calendar(self):
        """calendar_poll_handler() must invoke poll_calendar() exactly once."""
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            await calendar_poll_handler()
        mock_poll.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_returns_none(self):
        """calendar_poll_handler() always returns None (no next_run_at override)."""
        with patch("shared.service.poll_calendar", new_callable=AsyncMock):
            result = await calendar_poll_handler()
        assert result is None

    @pytest.mark.asyncio
    async def test_poll_calendar_called_without_arguments(self):
        """poll_calendar is called with no arguments (all defaults)."""
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            await calendar_poll_handler()
        # Verify positional and keyword arguments are empty
        args, kwargs = mock_poll.call_args
        assert args == ()
        assert kwargs == {}

    @pytest.mark.asyncio
    async def test_return_value_is_always_none_regardless_of_poll_result(self):
        """Return value is None even if poll_calendar() returns a non-None value."""
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = "unexpected"
            result = await calendar_poll_handler()
        assert result is None

    @pytest.mark.asyncio
    async def test_awaits_poll_calendar(self):
        """calendar_poll_handler awaits poll_calendar (it is a coroutine)."""
        call_order = []

        async def tracked_poll():
            call_order.append("poll_calendar")

        with patch("shared.service.poll_calendar", side_effect=tracked_poll):
            await calendar_poll_handler()

        assert call_order == ["poll_calendar"]


# ---------------------------------------------------------------------------
# on_startup
# ---------------------------------------------------------------------------


class TestOnStartup:
    # on_startup() does a local import: `from shared.scheduler import register_job`
    # so register_job is looked up in shared.scheduler at call time.
    # We must patch shared.scheduler.register_job (where the name is bound),
    # not shared.service.register_job (which does not exist at module level).

    def test_calls_register_job_once(self):
        """on_startup() calls register_job() exactly once."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        mock_register.assert_called_once()

    def test_passes_session_to_register_job(self):
        """on_startup() forwards its session argument as the first positional arg."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        positional_args, _ = mock_register.call_args
        assert positional_args[0] is mock_session

    def test_job_name_is_shared_calendar_poll(self):
        """The registered job name is 'shared.calendar_poll'."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["name"] == "shared.calendar_poll"

    def test_interval_secs_is_900(self):
        """Calendar poll runs every 900 seconds (15 minutes)."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["interval_secs"] == 900

    def test_ttl_secs_is_120(self):
        """Calendar poll job TTL is 120 seconds."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["ttl_secs"] == 120

    def test_handler_is_calendar_poll_handler(self):
        """The registered handler is calendar_poll_handler."""
        mock_session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["handler"] is calendar_poll_handler
