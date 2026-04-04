"""Additional coverage for ChatBot -- on_message(), _generate_response(), on_ready()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot, create_bot, should_respond


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    msg.reply = AsyncMock(return_value=_make_sent_message())
    return msg


def _make_sent_message(msg_id: int = 100) -> MagicMock:
    sent = MagicMock()
    sent.id = msg_id
    return sent


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals so it never touches real services."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    # Patch the internal user reference
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


# ---------------------------------------------------------------------------
# should_respond edge cases (reference with no .resolved attribute)
# ---------------------------------------------------------------------------


class TestShouldRespondEdgeCases:
    def test_reference_without_resolved_attr(self):
        """Reference object without a resolved attribute is handled gracefully."""
        message = MagicMock()
        message.author.bot = False
        message.mentions = []
        bot_user = MagicMock()
        bot_user.id = 12345
        # reference present but has no 'resolved' attribute
        reference = MagicMock(spec=[])
        message.reference = reference
        assert should_respond(message, bot_user) is False

    def test_reference_resolved_is_none(self):
        """Reference with resolved=None does not trigger a response."""
        message = MagicMock()
        message.author.bot = False
        message.mentions = []
        bot_user = MagicMock()
        bot_user.id = 12345
        reference = MagicMock()
        reference.resolved = None
        message.reference = reference
        assert should_respond(message, bot_user) is False


# ---------------------------------------------------------------------------
# ChatBot.on_ready
# ---------------------------------------------------------------------------


class TestOnReady:
    @pytest.mark.asyncio
    async def test_on_ready_logs_without_error(self):
        """on_ready() completes without raising even with a mock user."""
        bot = _make_bot()
        # _make_bot() already sets bot._connection.user; user is a read-only property
        bot._connection.user.__str__ = MagicMock(return_value="BotUser#0001")
        await bot.on_ready()  # should not raise


# ---------------------------------------------------------------------------
# ChatBot.on_message -- store-always branch
# ---------------------------------------------------------------------------


class TestOnMessageStoreAlways:
    @pytest.mark.asyncio
    async def test_stores_every_message_even_when_not_responding(self):
        """on_message always calls save_message regardless of should_respond."""
        bot = _make_bot()
        # user is a read-only property; _make_bot() sets _connection.user with id=999

        message = _make_message(author_bot=False, mentions=[])
        message.reference = None

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

        mock_store.save_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_store_exception(self):
        """on_message does not propagate exceptions from the store phase."""
        bot = _make_bot()
        # user is a read-only property; _make_bot() sets _connection.user with id=999

        message = _make_message(author_bot=False, mentions=[])
        message.reference = None

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore") as mock_store_cls,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_store_cls.return_value.save_message = AsyncMock(
                side_effect=RuntimeError("db down")
            )
            # Should not raise
            await bot.on_message(message)


# ---------------------------------------------------------------------------
# ChatBot.on_message -- should_respond guard
# ---------------------------------------------------------------------------


class TestOnMessageShouldRespondGuard:
    @pytest.mark.asyncio
    async def test_does_not_reply_to_bot_messages(self):
        """on_message returns early and does not call reply for bot-authored messages."""
        bot = _make_bot()
        # user is a read-only property; _make_bot() sets _connection.user with id=999

        message = _make_message(author_bot=True)

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


# ---------------------------------------------------------------------------
# ChatBot.on_message -- generate + reply branch
# ---------------------------------------------------------------------------


class TestOnMessageGenerateReply:
    @pytest.mark.asyncio
    async def test_replies_when_mentioned(self):
        """on_message sends a reply when the bot is mentioned."""
        bot = _make_bot()
        # user is a read-only property — configure via _connection.user
        bot._connection.user.id = 999
        bot._connection.user.display_name = "BotUser"
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])

        mock_agent_result = MagicMock()
        mock_agent_result.output = "Hello human!"
        bot.agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        message.reply.assert_called_once_with("Hello human!")

    @pytest.mark.asyncio
    async def test_swallows_reply_exception(self):
        """on_message does not propagate exceptions from the reply phase."""
        bot = _make_bot()
        # user is a read-only property — configure via _connection.user
        bot._connection.user.id = 999
        bot._connection.user.display_name = "BotUser"
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None
        message.reply = AsyncMock(side_effect=RuntimeError("discord error"))

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])

        mock_agent_result = MagicMock()
        mock_agent_result.output = "Hello!"
        bot.agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise
            await bot.on_message(message)


# ---------------------------------------------------------------------------
# ChatBot._generate_response
# ---------------------------------------------------------------------------


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_includes_recent_messages_in_prompt(self):
        """_generate_response calls agent.run with recent conversation context."""
        from datetime import datetime, timezone

        from chat.models import Message

        bot = _make_bot()
        # user is a read-only property — configure via _connection.user
        bot._connection.user.id = 999

        msg = _make_message(content="What is the weather?")

        recent_msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="99",
            user_id="u1",
            username="Alice",
            content="recent message",
            is_bot=False,
            embedding=[0.0] * 1024,
            created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        )

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[recent_msg])

        mock_agent_result = MagicMock()
        mock_agent_result.output = "Sunny!"
        bot.agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = await bot._generate_response(msg)

        assert result == "Sunny!"
        prompt_arg = bot.agent.run.call_args[0][0]
        assert "recent message" in prompt_arg
        # Verify deps were passed to agent.run
        assert "deps" in bot.agent.run.call_args[1]


# ---------------------------------------------------------------------------
# create_bot
# ---------------------------------------------------------------------------


class TestCreateBot:
    def test_returns_chatbot_instance(self):
        """create_bot() returns a ChatBot."""
        with (
            patch("chat.bot.EmbeddingClient"),
            patch("chat.bot.create_agent"),
        ):
            bot = create_bot()
        assert isinstance(bot, ChatBot)
