"""Additional coverage for app.main -- lifespan with Discord bot token set."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no valid STATIC_DIR is set (matches main_test.py approach)
os.environ.pop("STATIC_DIR", None)

from app.main import app, lifespan  # noqa: E402


class TestLifespanWithDiscordToken:
    @pytest.mark.asyncio
    async def test_lifespan_starts_bot_when_token_set(self):
        """When DISCORD_BOT_TOKEN is set lifespan creates a third task for the bot."""
        created_tasks = []

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            mock_task = MagicMock()
            created_tasks.append(mock_task)
            return mock_task

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()
        mock_bot.start = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-xyz"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        # scheduler + calendar + bot = 3 tasks
        assert len(created_tasks) == 3

    @pytest.mark.asyncio
    async def test_lifespan_closes_bot_on_shutdown(self):
        """When Discord bot is started lifespan calls bot.close() on shutdown."""
        created_tasks = []

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            mock_task = MagicMock()
            created_tasks.append(mock_task)
            return mock_task

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-xyz"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        mock_bot.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_cancels_bot_task_on_shutdown(self):
        """Bot task is cancelled when the lifespan context exits."""
        created_tasks = []

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            mock_task = MagicMock()
            created_tasks.append(mock_task)
            return mock_task

        mock_bot = MagicMock()
        mock_bot.close = AsyncMock()

        with (
            patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "fake-token-xyz"}),
            patch("asyncio.create_task", side_effect=capture_create_task),
            patch("chat.bot.create_bot", return_value=mock_bot),
        ):
            async with lifespan(app):
                pass

        # All three tasks (scheduler, calendar, bot) should be cancelled
        for task in created_tasks:
            task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_no_bot_task_when_token_empty(self):
        """When DISCORD_BOT_TOKEN is absent lifespan creates exactly 2 tasks."""
        created_tasks = []

        def capture_create_task(coro, **kwargs):
            if hasattr(coro, "close"):
                coro.close()
            mock_task = MagicMock()
            created_tasks.append(mock_task)
            return mock_task

        env_without_token = {k: v for k, v in os.environ.items() if k != "DISCORD_BOT_TOKEN"}
        env_without_token["DISCORD_BOT_TOKEN"] = ""

        with (
            patch.dict(os.environ, env_without_token, clear=True),
            patch("asyncio.create_task", side_effect=capture_create_task),
        ):
            async with lifespan(app):
                pass

        assert len(created_tasks) == 2
