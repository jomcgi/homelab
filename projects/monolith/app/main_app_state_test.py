"""Tests for app.main lifespan app.state assignments and _wait_for_sidecar timeout kwarg.

Covers gaps not addressed by existing main_* test files:

1. app.state.bot is set to the created bot instance when DISCORD_BOT_TOKEN is set.
2. app.state.bot remains None when DISCORD_BOT_TOKEN is absent.
3. _wait_for_sidecar passes timeout=2 as a keyword argument to client.get().

These complement the existing tests in main_sidecar_test.py and main_coverage_test.py
which verify task counts, callbacks, and URL forwarding but not the specific state
assignments or the timeout kwarg.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no valid static directory is set before importing main
os.environ.pop("STATIC_DIR", None)

from app.main import app, lifespan, _wait_for_sidecar  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirrors main_sidecar_test.py helper style)
# ---------------------------------------------------------------------------


def _make_mock_async_client(responses):
    """Return a mock httpx.AsyncClient context-manager and the client mock.

    ``responses`` is a list of mock response objects with a ``status_code``
    attribute or exception instances to raise from ``client.get()``.
    """
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=responses)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_client


def _resp(status_code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    return r


# ---------------------------------------------------------------------------
# _wait_for_sidecar() — timeout kwarg forwarded to client.get()
# ---------------------------------------------------------------------------


class TestWaitForSidecarTimeoutKwarg:
    @pytest.mark.asyncio
    async def test_wait_for_sidecar_passes_timeout_2_to_client_get(self):
        """client.get() is called with keyword argument timeout=2.

        The implementation calls ``await client.get(url, timeout=2)``.
        Existing tests verify the URL positional arg; this test pins the
        timeout keyword arg so accidental removal is caught.
        """
        mock_cm, mock_client = _make_mock_async_client([_resp(200)])

        with patch.dict(os.environ, {"FRONTEND_HEALTH_URL": "http://sidecar/healthz"}):
            with patch("httpx.AsyncClient", return_value=mock_cm):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await _wait_for_sidecar()

        # Verify keyword argument
        kwargs = mock_client.get.call_args[1]
        assert "timeout" in kwargs, (
            "client.get() was not called with a 'timeout' keyword argument"
        )
        assert kwargs["timeout"] == 2, (
            f"Expected timeout=2 but got timeout={kwargs['timeout']!r}"
        )

    @pytest.mark.asyncio
    async def test_wait_for_sidecar_timeout_kwarg_present_on_retry(self):
        """timeout=2 kwarg is present on every retry attempt, not just the first call."""
        mock_cm, mock_client = _make_mock_async_client([_resp(500), _resp(200)])

        with patch.dict(os.environ, {"FRONTEND_HEALTH_URL": "http://sidecar/healthz"}):
            with patch("httpx.AsyncClient", return_value=mock_cm):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await _wait_for_sidecar()

        assert mock_client.get.call_count == 2
        for call in mock_client.get.call_args_list:
            assert call[1].get("timeout") == 2, (
                f"Expected timeout=2 on every call but got: {call[1]}"
            )


# ---------------------------------------------------------------------------
# lifespan() — app.state.bot assignment
# ---------------------------------------------------------------------------


class TestLifespanAppStateBotAssignment:
    @pytest.mark.asyncio
    async def test_app_state_bot_is_set_to_bot_when_token_present(self):
        """app.state.bot is set to the create_bot() return value during lifespan.

        The lifespan code is:
            bot = create_bot()
            app.state.bot = bot

        This test verifies that the bot stored in app.state.bot is exactly the
        mock returned by create_bot() — i.e., the assignment happened correctly.
        """
        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            return MagicMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-xyz"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                # During the lifespan body, app.state.bot must be the created bot
                assert app.state.bot is mock_bot, (
                    "app.state.bot was not set to the bot created by create_bot()"
                )

    @pytest.mark.asyncio
    async def test_app_state_bot_is_none_when_no_token(self):
        """app.state.bot is None during lifespan when DISCORD_BOT_TOKEN is absent.

        With no token the Discord bot branch is skipped entirely, so the initial
        ``app.state.bot = None`` assignment from lifespan should be visible.
        """
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
                assert app.state.bot is None, (
                    "app.state.bot should be None when no DISCORD_BOT_TOKEN is set"
                )

    @pytest.mark.asyncio
    async def test_app_state_backfill_task_initialised_to_none_on_startup(self):
        """lifespan initialises app.state.backfill_task to None at startup.

        The lifespan code sets:
            app.state.backfill_task = None

        before yielding. This ensures the shutdown path's
        ``getattr(app.state, 'backfill_task', None)`` cannot encounter an
        uninitialised attribute on first run.
        """
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
                assert hasattr(app.state, "backfill_task"), (
                    "app.state.backfill_task was not set during lifespan startup"
                )
                assert app.state.backfill_task is None, (
                    "app.state.backfill_task should be None at startup"
                )
