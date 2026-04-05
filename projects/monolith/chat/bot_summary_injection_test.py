"""Tests for summary injection into agent context in _generate_response().

Verifies that channel and user summaries are fetched from the store and
prepended to the prompt passed to the agent.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot
from chat.models import ChannelSummary, UserChannelSummary


# ---------------------------------------------------------------------------
# Shared helpers (same patterns as bot_generate_response_gaps_test.py)
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "hello",
    channel_id: int = 99,
    msg_id: int = 1,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = []
    msg.reference = None
    msg.attachments = []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.VisionClient"),
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


def _make_agent_result(output: str) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.new_messages.return_value = []
    return result


def _setup_store_mock(
    channel_summary=None,
    user_summaries=None,
) -> MagicMock:
    """Return a store mock with configurable summary return values."""
    store = MagicMock()
    store.get_recent = MagicMock(return_value=[])
    store.get_attachments = MagicMock(return_value={})
    store.get_channel_summary = MagicMock(return_value=channel_summary)
    store.get_user_summaries_for_users = MagicMock(return_value=user_summaries or [])
    store.save_message = AsyncMock()
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChannelSummaryInjection:
    @pytest.mark.asyncio
    async def test_channel_summary_appears_in_prompt(self):
        """When a channel summary exists, its text is included in the prompt."""
        bot = _make_bot()
        msg = _make_message(content="What's up?")

        cs = ChannelSummary(
            id=1,
            channel_id="99",
            summary="This channel discusses homelab infrastructure.",
            message_count=50,
            last_message_id=100,
        )
        mock_store = _setup_store_mock(channel_summary=cs)

        mock_result = _make_agent_result("Not much!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert (
            "[Channel context: This channel discusses homelab infrastructure.]"
            in prompt_arg
        )


class TestUserSummaryInjection:
    @pytest.mark.asyncio
    async def test_user_summaries_appear_in_prompt(self):
        """When user summaries exist, they are included in the prompt."""
        bot = _make_bot()
        msg = _make_message(content="Hello")

        user_sums = [
            UserChannelSummary(
                id=1,
                channel_id="99",
                user_id="42",
                username="Alice",
                summary="Interested in Kubernetes and Go.",
            ),
            UserChannelSummary(
                id=2,
                channel_id="99",
                user_id="43",
                username="Bob",
                summary="Asks about Python packaging.",
            ),
        ]
        mock_store = _setup_store_mock(user_summaries=user_sums)

        mock_result = _make_agent_result("Hi there!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert "[People in this conversation:" in prompt_arg
        assert " - Alice: Interested in Kubernetes and Go." in prompt_arg
        assert " - Bob: Asks about Python packaging." in prompt_arg


class TestNoSummariesGracefulSkip:
    @pytest.mark.asyncio
    async def test_no_summaries_no_header(self):
        """When no summaries exist, the prompt has no summary header."""
        bot = _make_bot()
        msg = _make_message(content="Hey")

        mock_store = _setup_store_mock(channel_summary=None, user_summaries=[])

        mock_result = _make_agent_result("Hey back!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert "[Channel context:" not in prompt_arg
        assert "[People in this conversation:" not in prompt_arg
        # Should still start with the recent conversation header
        assert prompt_arg.startswith("Recent conversation:")
