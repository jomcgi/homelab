"""Extra coverage for bot.py -- _generate_response failure paths and should_respond negative cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot, should_respond


# ---------------------------------------------------------------------------
# Helpers (shared with bot_coverage_test.py conventions)
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
    author_bot: bool = False,
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
    reference=None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = author_bot
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = reference
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals so it never touches real services."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
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


# ---------------------------------------------------------------------------
# should_respond -- reply-to-different-author negative case
# ---------------------------------------------------------------------------


class TestShouldRespondReplyToDifferentAuthor:
    def test_does_not_respond_to_reply_targeting_different_user(self):
        """should_respond returns False when a reply targets a different user, not the bot."""
        message = MagicMock()
        message.author.bot = False
        message.mentions = []
        bot_user = MagicMock()
        bot_user.id = 12345

        # Reply targets a different user (id 99999, not the bot's id 12345)
        reference = MagicMock()
        reference.resolved = MagicMock()
        reference.resolved.author.id = 99999  # different from bot_user.id
        message.reference = reference

        assert should_respond(message, bot_user) is False


# ---------------------------------------------------------------------------
# _generate_response -- embed failure propagates out of on_message
# ---------------------------------------------------------------------------


class TestGenerateResponseEmbedFailure:
    @pytest.mark.asyncio
    async def test_embed_failure_is_swallowed_by_on_message(self):
        """When embed_client.embed() raises, on_message swallows the error gracefully."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()

        bot.embed_client.embed = AsyncMock(side_effect=RuntimeError("embed service down"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise — on_message wraps _generate_response in try/except
            await bot.on_message(message)

        # reply should not have been called because _generate_response failed
        message.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_run_failure_is_swallowed_by_on_message(self):
        """When agent.run() raises, on_message swallows the error gracefully."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        mock_store = MagicMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.search_similar = MagicMock(return_value=[])

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 512)
        bot.agent.run = AsyncMock(side_effect=RuntimeError("model unavailable"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise — on_message wraps the whole respond block
            await bot.on_message(message)

        message.reply.assert_not_called()
