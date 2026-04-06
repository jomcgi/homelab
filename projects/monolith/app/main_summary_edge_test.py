"""Edge-case tests for the summary loop and lifespan shutdown in app.main.

Covers gaps not addressed by main_summary_test.py:
- _summary_loop exception handling: verify logger.exception is called and the loop
  continues (resilience through repeated failures in a single test).
- _summary_loop when only latest_user is None (needs_run must be True).
- _summary_loop when only latest_channel is None (needs_run must be True).
- Lifespan shutdown: when backfill_task.done() returns True, cancel is skipped.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no valid static directory before importing main
os.environ.pop("STATIC_DIR", None)

from app.main import app, lifespan  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_summary_coro():
    """Return (coros, capture_fn, mock_bot) for capturing the summary loop coroutine.

    The summary loop is the 4th asyncio.create_task call in lifespan when
    DISCORD_BOT_TOKEN is set:
      1 = scheduler, 2 = calendar, 3 = bot, 4 = summary, 5 = sweep.
    """
    mock_bot = MagicMock()
    mock_bot.close = AsyncMock()

    coros: list = []
    task_counter = [0]

    def capture_create_task(coro, **kwargs):
        task_counter[0] += 1
        t = MagicMock()
        if task_counter[0] == 4:
            coros.append(coro)  # preserve — do NOT close
        else:
            if hasattr(coro, "close"):
                coro.close()
        return t

    return coros, capture_create_task, mock_bot


def _session_mock(first_side_effect):
    """Return a Session context-manager mock whose exec().first() uses side_effect."""
    inner = MagicMock()
    inner.exec.return_value.first.side_effect = first_side_effect
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=inner)
    session.__exit__ = MagicMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# _summary_loop exception handling
# ---------------------------------------------------------------------------


class TestSummaryLoopExceptionEdgeCases:
    @pytest.mark.asyncio
    async def test_exception_is_logged_and_loop_continues(self):
        """logger.exception is called when generate_summaries raises AND the loop
        keeps running (exception does not propagate out of the loop body)."""
        coros, capture_fn, mock_bot = _capture_summary_coro()

        # Both queries return None so needs_run is always True
        inner = MagicMock()
        inner.exec.return_value.first.return_value = None
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=inner)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_cls = MagicMock(return_value=mock_session)
        mock_engine = MagicMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_fn),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.db.get_engine", return_value=mock_engine),
            patch("sqlmodel.Session", mock_session_cls),
        ):
            async with lifespan(app):
                pass

        assert len(coros) == 1

        # Run two full iterations, then cancel on the third sleep.
        sleep_count = [0]

        async def controlled_sleep(_):
            sleep_count[0] += 1
            if sleep_count[0] >= 2:
                raise asyncio.CancelledError()

        mock_generate = AsyncMock(side_effect=RuntimeError("transient error"))

        with (
            patch("asyncio.sleep", side_effect=controlled_sleep),
            patch("chat.summarizer.build_llm_caller", return_value=MagicMock()),
            patch(
                "chat.summarizer.generate_summaries",
                mock_generate,
            ),
            patch("app.main.logger") as mock_logger,
        ):
            try:
                await coros[0]
            except asyncio.CancelledError:
                pass

        # logger.exception was called at least once
        mock_logger.exception.assert_called_with("Summary generation failed")
        # The loop ran both iterations (exceptions were caught, not propagated)
        assert mock_generate.call_count == 2


# ---------------------------------------------------------------------------
# _summary_loop needs_run when only one of the timestamps is missing
# ---------------------------------------------------------------------------


class TestSummaryLoopNeedsRunEdgeCases:
    @pytest.mark.asyncio
    async def test_needs_run_true_when_only_latest_user_is_none(self):
        """When latest_user is None but latest_channel has a value, needs_run must be True
        because the staleness check only fires when BOTH timestamps are present."""
        coros, capture_fn, mock_bot = _capture_summary_coro()

        # First .first() call → latest_user = None
        # Second .first() call → latest_channel = a recent datetime (fresh)
        recent_dt = datetime.now(timezone.utc)
        session = _session_mock(first_side_effect=[None, recent_dt])
        mock_session_cls = MagicMock(return_value=session)
        mock_engine = MagicMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_fn),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.db.get_engine", return_value=mock_engine),
            patch("sqlmodel.Session", mock_session_cls),
        ):
            async with lifespan(app):
                pass

        assert len(coros) == 1

        mock_generate = AsyncMock()

        async def cancel_on_first_sleep(_):
            raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=cancel_on_first_sleep),
            patch("chat.summarizer.build_llm_caller", return_value=MagicMock()),
            patch("chat.summarizer.generate_summaries", mock_generate),
            patch(
                "chat.summarizer.generate_channel_summaries",
                new_callable=AsyncMock,
            ),
            patch("app.main.logger"),
        ):
            try:
                await coros[0]
            except asyncio.CancelledError:
                pass

        # generate_summaries must have been called — needs_run was True
        assert mock_generate.call_count == 1, (
            "generate_summaries should be called when latest_user is None"
        )

    @pytest.mark.asyncio
    async def test_needs_run_true_when_only_latest_channel_is_none(self):
        """When latest_channel is None but latest_user has a value, needs_run must be True."""
        coros, capture_fn, mock_bot = _capture_summary_coro()

        # First .first() call → latest_user = a recent datetime (fresh)
        # Second .first() call → latest_channel = None
        recent_dt = datetime.now(timezone.utc)
        session = _session_mock(first_side_effect=[recent_dt, None])
        mock_session_cls = MagicMock(return_value=session)
        mock_engine = MagicMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token"}),
            patch("asyncio.create_task", side_effect=capture_fn),
            patch("chat.bot.create_bot", return_value=mock_bot),
            patch("app.db.get_engine", return_value=mock_engine),
            patch("sqlmodel.Session", mock_session_cls),
        ):
            async with lifespan(app):
                pass

        assert len(coros) == 1

        mock_generate = AsyncMock()

        async def cancel_on_first_sleep(_):
            raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=cancel_on_first_sleep),
            patch("chat.summarizer.build_llm_caller", return_value=MagicMock()),
            patch("chat.summarizer.generate_summaries", mock_generate),
            patch(
                "chat.summarizer.generate_channel_summaries",
                new_callable=AsyncMock,
            ),
            patch("app.main.logger"),
        ):
            try:
                await coros[0]
            except asyncio.CancelledError:
                pass

        # generate_summaries must have been called — needs_run was True
        assert mock_generate.call_count == 1, (
            "generate_summaries should be called when latest_channel is None"
        )


# ---------------------------------------------------------------------------
# Lifespan shutdown: backfill_task.done() returns True → cancel skipped
# ---------------------------------------------------------------------------


class TestLifespanShutdownBackfillDone:
    @pytest.mark.asyncio
    async def test_backfill_task_not_cancelled_when_done(self):
        """If backfill_task.done() returns True, lifespan must NOT call cancel() on it.

        The code path under test (in app/main.py):
            backfill_task = getattr(app.state, 'backfill_task', None)
            if backfill_task and not backfill_task.done():
                backfill_task.cancel()
        """
        backfill_mock = MagicMock()
        backfill_mock.done.return_value = True  # task already finished

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            return MagicMock()

        env_without_token = {
            k: v for k, v in os.environ.items() if k != "DISCORD_BOT_TOKEN"
        }
        env_without_token["DISCORD_BOT_TOKEN"] = ""

        with (
            patch.dict(os.environ, env_without_token, clear=True),
            patch("asyncio.create_task", side_effect=capture_create_task),
        ):
            async with lifespan(app):
                # Inject the already-done backfill task during the lifespan body
                app.state.backfill_task = backfill_mock

        # cancel() must NOT have been called because done() returned True
        backfill_mock.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_task_cancelled_when_not_done(self):
        """If backfill_task.done() returns False, lifespan MUST call cancel()."""
        backfill_mock = MagicMock()
        backfill_mock.done.return_value = False  # task still running

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            return MagicMock()

        env_without_token = {
            k: v for k, v in os.environ.items() if k != "DISCORD_BOT_TOKEN"
        }
        env_without_token["DISCORD_BOT_TOKEN"] = ""

        with (
            patch.dict(os.environ, env_without_token, clear=True),
            patch("asyncio.create_task", side_effect=capture_create_task),
        ):
            async with lifespan(app):
                app.state.backfill_task = backfill_mock

        backfill_mock.cancel.assert_called_once()
