"""Tests for the summary-loop background task in app.main.

Covers gaps not addressed by existing main_* test files:
- summary_task.add_done_callback(_log_task_exception) is called when Discord token is set
- Both bot task and summary task register done callbacks
- "Summary loop started (24h interval)" is logged when Discord token is set
- "Summary loop started" is NOT logged without a token
- _summary_loop logs logger.exception when generate_summaries raises
- _summary_loop continues after repeated failures (resilience)
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no valid static directory before importing main
os.environ.pop("STATIC_DIR", None)

from app.main import app, lifespan, _log_task_exception  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_capturer():
    """Return (task_list, side_effect_fn) for patching asyncio.create_task."""
    tasks: list[MagicMock] = []

    def capture(coro, **kwargs):
        if hasattr(coro, "close"):
            coro.close()
        t = MagicMock()
        tasks.append(t)
        return t

    return tasks, capture


# ---------------------------------------------------------------------------
# summary_task.add_done_callback is registered
# ---------------------------------------------------------------------------


class TestSummaryTaskDoneCallback:
    @pytest.mark.asyncio
    async def test_summary_task_registers_done_callback_with_log_task_exception(self):
        """When DISCORD_BOT_TOKEN is set, summary_task.add_done_callback(_log_task_exception) is called.

        This pins the error-surfacing wiring for the summary background task.
        Task order: 1=scheduler, 2=calendar, 3=bot, 4=summary.
        """
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        summary_task_mock = MagicMock()
        task_counter = [0]

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            task_counter[0] += 1
            if task_counter[0] == 4:
                return summary_task_mock
            return MagicMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        summary_task_mock.add_done_callback.assert_called_once_with(_log_task_exception)

    @pytest.mark.asyncio
    async def test_bot_task_and_summary_task_both_get_done_callback(self):
        """Both the bot task (task 3) and summary task (task 4) register done callbacks."""
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        task_mocks: list[MagicMock] = []
        task_counter = [0]

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            task_counter[0] += 1
            t = MagicMock()
            task_mocks.append(t)
            return t

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        assert len(task_mocks) == 4
        # Tasks 3 and 4 (index 2 and 3) should have add_done_callback called
        bot_task = task_mocks[2]
        summary_task = task_mocks[3]
        bot_task.add_done_callback.assert_called_once_with(_log_task_exception)
        summary_task.add_done_callback.assert_called_once_with(_log_task_exception)


# ---------------------------------------------------------------------------
# "Summary loop started" log message
# ---------------------------------------------------------------------------


class TestSummaryLoopLogging:
    @pytest.mark.asyncio
    async def test_summary_loop_started_logged_when_token_set(self):
        """'Summary loop started (24h interval)' is logged when DISCORD_BOT_TOKEN is set."""
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        tasks, capture = _make_task_capturer()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.main.logger") as mock_logger,
        ):
            async with lifespan(app):
                pass

        messages = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Summary loop started" in m for m in messages), (
            "Expected 'Summary loop started' to be logged when DISCORD_BOT_TOKEN is set"
        )

    @pytest.mark.asyncio
    async def test_summary_loop_not_logged_when_no_token(self):
        """'Summary loop started' is NOT logged when DISCORD_BOT_TOKEN is absent."""
        tasks, capture = _make_task_capturer()

        env_without_token = {
            k: v for k, v in os.environ.items() if k != "DISCORD_BOT_TOKEN"
        }
        env_without_token["DISCORD_BOT_TOKEN"] = ""

        with (
            patch.dict(os.environ, env_without_token, clear=True),
            patch("asyncio.create_task", side_effect=capture),
            patch("app.main.logger") as mock_logger,
        ):
            async with lifespan(app):
                pass

        messages = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("Summary loop started" in m for m in messages)


# ---------------------------------------------------------------------------
# _summary_loop exception logging
# ---------------------------------------------------------------------------


class TestSummaryLoopExceptionLogging:
    @pytest.mark.asyncio
    async def test_summary_loop_logs_exception_when_generate_summaries_raises(self):
        """_summary_loop calls logger.exception('Summary generation failed') on error.

        Strategy:
        1. Capture the summary loop coroutine (task 4) without closing it.
        2. Patch app.db.get_engine and sqlmodel.Session before running lifespan so the
           closure captures mock objects (from-imports bind at execution time).
        3. Run the captured coroutine with asyncio.sleep patched:
           - First call: returns normally (advances past initial 24h sleep).
           - Second call: raises CancelledError to exit the infinite loop.
        4. Verify logger.exception was called with the expected message.
        """
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        # Capture summary coro (task 4) without closing it
        coros: list = []
        task_counter = [0]

        def capture_create_task(coro, **kwargs):
            task_counter[0] += 1
            t = MagicMock()
            if task_counter[0] == 4:
                coros.append(coro)  # preserve for later execution
            else:
                if hasattr(coro, "close"):
                    coro.close()
            return t

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=MagicMock())
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_cls = MagicMock(return_value=mock_session)
        mock_engine = MagicMock()

        # Patch Session and get_engine BEFORE lifespan runs so the closure
        # captures the mocked objects when `from ... import ...` executes inside lifespan.
        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.db.get_engine", return_value=mock_engine),
            patch("sqlmodel.Session", mock_session_cls),
        ):
            async with lifespan(app):
                pass

        assert len(coros) == 1, "Expected exactly one summary loop coroutine captured"

        # Control the infinite loop: run once then cancel
        sleep_call_count = [0]

        async def controlled_sleep(_secs):
            sleep_call_count[0] += 1
            if sleep_call_count[0] > 1:
                raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=controlled_sleep),
            patch("chat.summarizer.build_llm_caller", return_value=MagicMock()),
            patch(
                "chat.summarizer.generate_summaries",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB unavailable"),
            ),
            patch("app.main.logger") as mock_logger,
        ):
            try:
                await coros[0]
            except asyncio.CancelledError:
                pass  # expected exit from the loop

        mock_logger.exception.assert_called_once_with("Summary generation failed")

    @pytest.mark.asyncio
    async def test_summary_loop_continues_after_generate_summaries_raises(self):
        """_summary_loop does not propagate the exception — it catches and logs it, then loops."""
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        coros: list = []
        task_counter = [0]

        def capture_create_task(coro, **kwargs):
            task_counter[0] += 1
            t = MagicMock()
            if task_counter[0] == 4:
                coros.append(coro)
            else:
                if hasattr(coro, "close"):
                    coro.close()
            return t

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=MagicMock())
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.db.get_engine", return_value=MagicMock()),
            patch("sqlmodel.Session", MagicMock(return_value=mock_session)),
        ):
            async with lifespan(app):
                pass

        assert len(coros) == 1

        # Let the loop run twice (two generate_summaries failures) then cancel
        sleep_call_count = [0]

        async def controlled_sleep(_secs):
            sleep_call_count[0] += 1
            if sleep_call_count[0] > 2:
                raise asyncio.CancelledError()

        exception_count = [0]

        async def mock_generate(*_args, **_kwargs):
            exception_count[0] += 1
            raise RuntimeError("repeated failure")

        with (
            patch("asyncio.sleep", side_effect=controlled_sleep),
            patch("chat.summarizer.build_llm_caller", return_value=MagicMock()),
            patch("chat.summarizer.generate_summaries", side_effect=mock_generate),
            patch("app.main.logger"),
        ):
            try:
                await coros[0]
            except asyncio.CancelledError:
                pass

        # Exception was raised (and caught internally) on both iterations
        assert exception_count[0] == 2
