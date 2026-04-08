"""Tests for calendar_poll_handler() and on_startup() in shared/service.py.

calendar_poll_handler() is a scheduler handler wrapper that delegates to
poll_calendar() and always returns None (no next_run_at override).  The
session parameter is accepted but unused because the handler is stateless.

on_startup() wires calendar_poll_handler into the distributed scheduler with
a 15-minute interval and a 120-second TTL.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from shared.service import calendar_poll_handler, on_startup


# ---------------------------------------------------------------------------
# calendar_poll_handler
# ---------------------------------------------------------------------------


class TestCalendarPollHandler:
    @pytest.mark.asyncio
    async def test_calls_poll_calendar(self):
        """calendar_poll_handler() must invoke poll_calendar() exactly once."""
        mock_session = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            await calendar_poll_handler(mock_session)
        mock_poll.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_returns_none(self):
        """calendar_poll_handler() always returns None (no next_run_at override)."""
        mock_session = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock):
            result = await calendar_poll_handler(mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_session_is_not_used(self):
        """The session parameter is accepted but never invoked — handler is stateless."""
        mock_session = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock):
            await calendar_poll_handler(mock_session)
        # No session methods should be called
        mock_session.exec.assert_not_called()
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_called()
        mock_session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_calendar_called_without_arguments(self):
        """poll_calendar is called with no arguments (all defaults)."""
        mock_session = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            await calendar_poll_handler(mock_session)
        # Verify positional and keyword arguments are empty
        args, kwargs = mock_poll.call_args
        assert args == ()
        assert kwargs == {}

    @pytest.mark.asyncio
    async def test_return_value_is_always_none_regardless_of_poll_result(self):
        """Return value is None even if poll_calendar() returns a non-None value."""
        mock_session = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = "unexpected"
            result = await calendar_poll_handler(mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_awaits_poll_calendar(self):
        """calendar_poll_handler awaits poll_calendar (it is a coroutine)."""
        mock_session = MagicMock()
        call_order = []

        async def tracked_poll():
            call_order.append("poll_calendar")

        with patch("shared.service.poll_calendar", side_effect=tracked_poll):
            await calendar_poll_handler(mock_session)

        assert call_order == ["poll_calendar"]

    @pytest.mark.asyncio
    async def test_different_session_objects_work_identically(self):
        """The handler behaves the same regardless of which session object is passed."""
        session_a = MagicMock()
        session_b = MagicMock()
        with patch("shared.service.poll_calendar", new_callable=AsyncMock) as mock_poll:
            result_a = await calendar_poll_handler(session_a)
            result_b = await calendar_poll_handler(session_b)
        assert result_a is None
        assert result_b is None
        assert mock_poll.call_count == 2


# ---------------------------------------------------------------------------
# on_startup
# ---------------------------------------------------------------------------


class TestOnStartup:
    def test_calls_register_job_once(self):
        """on_startup() calls register_job() exactly once."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        mock_register.assert_called_once()

    def test_passes_session_to_register_job(self):
        """on_startup() forwards its session argument as the first positional arg."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        positional_args, _ = mock_register.call_args
        assert positional_args[0] is mock_session

    def test_job_name_is_shared_calendar_poll(self):
        """The registered job name is 'shared.calendar_poll'."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["name"] == "shared.calendar_poll"

    def test_interval_secs_is_900(self):
        """Calendar poll runs every 900 seconds (15 minutes)."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["interval_secs"] == 900

    def test_ttl_secs_is_120(self):
        """Calendar poll job TTL is 120 seconds."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["ttl_secs"] == 120

    def test_handler_is_calendar_poll_handler(self):
        """The registered handler is calendar_poll_handler."""
        mock_session = MagicMock()
        with patch("shared.service.register_job") as mock_register:
            on_startup(mock_session)
        _, kwargs = mock_register.call_args
        assert kwargs["handler"] is calendar_poll_handler
