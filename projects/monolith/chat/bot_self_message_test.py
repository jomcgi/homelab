"""Tests for ChatBot.on_message() -- early return when message is from the bot itself."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals so it never touches real services."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    # Set bot's own user id via internal connection mock
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


class TestOnMessageSelfMessageEarlyReturn:
    @pytest.mark.asyncio
    async def test_does_not_call_store_when_author_is_self(self):
        """on_message returns immediately without storing when message.author.id == self.user.id."""
        bot = _make_bot()
        bot_user_id = bot.user.id  # 999

        # Craft a message authored by the bot itself
        message = MagicMock()
        message.id = 1
        message.author.id = bot_user_id
        message.author.display_name = "BotUser"
        message.author.bot = True
        message.content = "I said this myself"
        message.channel.id = 42

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        mock_store.save_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_reply_when_author_is_self(self):
        """on_message does not call message.reply when message.author.id == self.user.id."""
        bot = _make_bot()
        bot_user_id = bot.user.id  # 999

        message = MagicMock()
        message.id = 2
        message.author.id = bot_user_id
        message.author.display_name = "BotUser"
        message.author.bot = True
        message.content = "My own message"
        message.channel.id = 42
        message.reply = AsyncMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore") as mock_store_cls,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value.save_message = AsyncMock()
            await bot.on_message(message)

        message.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_processes_message_from_different_user(self):
        """on_message proceeds (at minimum calls store) for messages not from self."""
        bot = _make_bot()
        bot_user_id = bot.user.id  # 999

        # Message from a different user
        message = MagicMock()
        message.id = 3
        message.author.id = bot_user_id + 1  # different user
        message.author.display_name = "HumanUser"
        message.author.bot = False
        message.content = "Hello bot!"
        message.channel.id = 42
        message.mentions = []
        message.reference = None
        message.reply = AsyncMock()

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Store should have been called for the non-self message
        mock_store.save_message.assert_called_once()
