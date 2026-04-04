"""Extra coverage for app/main.py lifespan -- exception paths in background tasks and bot.close()."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no valid STATIC_DIR is set (mirrors main_coverage_test.py approach)
os.environ.pop("STATIC_DIR", None)

from app.main import app, lifespan  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: create_task capture that drains coroutines without running them
# ---------------------------------------------------------------------------


def _make_task_capturer():
    """Return a list and a side_effect function that captures created tasks."""
    tasks = []

    def capture(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()  # avoid "coroutine was never awaited" warnings
        t = MagicMock()
        tasks.append(t)
        return t

    return tasks, capture


# ---------------------------------------------------------------------------
# bot.close() raises during lifespan shutdown
# ---------------------------------------------------------------------------


class TestLifespanBotCloseException:
    @pytest.mark.asyncio
    async def test_bot_close_exception_propagates(self):
        """When bot.close() raises during shutdown the exception propagates out of lifespan."""
        tasks, capture = _make_task_capturer()

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock(side_effect=RuntimeError("Discord connection lost"))

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-abc"}),
            patch("asyncio.create_task", side_effect=capture),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            with pytest.raises(RuntimeError, match="Discord connection lost"):
                async with lifespan(app):
                    pass

    @pytest.mark.asyncio
    async def test_bot_close_exception_does_not_prevent_task_creation(self):
        """Even when bot.close() will later raise, all 3 tasks are still created at startup."""
        tasks, capture = _make_task_capturer()

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock(side_effect=RuntimeError("close error"))

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-abc"}),
            patch("asyncio.create_task", side_effect=capture),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            try:
                async with lifespan(app):
                    pass
            except RuntimeError:
                pass  # expected

        # scheduler + calendar + bot = 3 tasks must have been created
        assert len(tasks) == 3


# ---------------------------------------------------------------------------
# poll_calendar raises (background task failure)
# ---------------------------------------------------------------------------


class TestLifespanPollCalendarException:
    @pytest.mark.asyncio
    async def test_lifespan_still_starts_when_poll_calendar_raises(self):
        """Lifespan yields normally even if poll_calendar() raises on first call."""
        started = False

        async def failing_poll_calendar():
            raise RuntimeError("calendar service down")

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": ""}),
            patch(
                "schedule.service.poll_calendar",
                side_effect=failing_poll_calendar,
            ),
        ):
            async with lifespan(app):
                # Give the background task a chance to execute and fail
                await asyncio.sleep(0)
                started = True

        assert started, "lifespan should have yielded despite poll_calendar failure"

    @pytest.mark.asyncio
    async def test_lifespan_shuts_down_cleanly_after_poll_calendar_failure(self):
        """Lifespan cleans up (cancels tasks) even when poll_calendar already failed."""

        async def failing_poll_calendar():
            raise RuntimeError("calendar service down")

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": ""}),
            patch(
                "schedule.service.poll_calendar",
                side_effect=failing_poll_calendar,
            ),
        ):
            # Should not raise — background task exceptions are not re-raised
            async with lifespan(app):
                await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# run_scheduler raises (background task failure)
# ---------------------------------------------------------------------------


class TestLifespanRunSchedulerException:
    @pytest.mark.asyncio
    async def test_lifespan_still_starts_when_run_scheduler_raises(self):
        """Lifespan yields normally even if run_scheduler() raises immediately."""
        started = False

        async def failing_run_scheduler():
            raise RuntimeError("scheduler db error")

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": ""}),
            patch("app.main.run_scheduler", new=failing_run_scheduler),
            patch("schedule.service.poll_calendar", new_callable=AsyncMock),
        ):
            async with lifespan(app):
                await asyncio.sleep(0)
                started = True

        assert started, "lifespan should have yielded despite run_scheduler failure"

    @pytest.mark.asyncio
    async def test_lifespan_shuts_down_cleanly_after_run_scheduler_failure(self):
        """Lifespan completes shutdown even when run_scheduler already raised."""

        async def failing_run_scheduler():
            raise RuntimeError("scheduler db error")

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": ""}),
            patch("app.main.run_scheduler", new=failing_run_scheduler),
            patch("schedule.service.poll_calendar", new_callable=AsyncMock),
        ):
            # Should not raise — background task exceptions are not re-raised
            async with lifespan(app):
                await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# bot.start() raises (background task failure while bot token is set)
# ---------------------------------------------------------------------------


class TestLifespanBotStartException:
    @pytest.mark.asyncio
    async def test_lifespan_still_starts_when_bot_start_raises(self):
        """Lifespan yields normally even if bot.start() raises in its background task."""
        started = False
        tasks, capture = _make_task_capturer()

        mock_bot = MagicMock()
        # close() succeeds so shutdown is clean
        mock_bot.close = AsyncMock()
        # start() raises — but it runs as a background task
        mock_bot.start = AsyncMock(side_effect=RuntimeError("invalid token"))

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "bad-token"}),
            patch("asyncio.create_task", side_effect=capture),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                started = True

        assert started, "lifespan should have yielded even when bot.start raises"

    @pytest.mark.asyncio
    async def test_bot_task_cancelled_even_when_start_raised(self):
        """Bot task is cancelled on shutdown even when bot.start() was going to raise."""
        tasks, capture = _make_task_capturer()

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()
        mock_bot.start = AsyncMock(side_effect=RuntimeError("invalid token"))

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "bad-token"}),
            patch("asyncio.create_task", side_effect=capture),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        # All 3 mock tasks (scheduler, calendar, bot) should be cancelled
        for task in tasks:
            task.cancel.assert_called_once()
