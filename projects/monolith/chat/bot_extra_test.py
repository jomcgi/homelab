"""Extra coverage for bot.py -- error paths via streaming and should_respond negative cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, TextPartDelta

from chat.bot import ChatBot, should_respond


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _text_delta(content: str) -> PartDeltaEvent:
    return PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=content))


async def _async_iter(events):
    for e in events:
        yield e


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
    msg.attachments = []
    msg.embeds = []
    sent = MagicMock(id=100)
    sent.edit = AsyncMock()
    msg.reply = AsyncMock(return_value=sent)
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


def _make_store():
    mock_store = AsyncMock()
    mock_store.save_message = AsyncMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})
    mock_store.get_channel_summary = MagicMock(return_value=None)
    mock_store.get_user_summaries_for_users = MagicMock(return_value=[])
    mock_store.acquire_lock = MagicMock(return_value=True)
    mock_store.mark_completed = MagicMock()
    return mock_store


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
# _stream_response -- store failure propagates as error reply
# ---------------------------------------------------------------------------


class TestStreamResponseStoreFailure:
    @pytest.mark.asyncio
    async def test_get_recent_failure_sends_error_reply(self):
        """When store.get_recent() raises inside _stream_response, on_message sends an error reply."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])

        mock_store = _make_store()
        mock_store.get_recent = MagicMock(
            side_effect=RuntimeError("db connection lost")
        )

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

        # Error reply should have been sent
        reply_calls = message.reply.call_args_list
        sorry_calls = [c for c in reply_calls if "trouble" in str(c)]
        assert len(sorry_calls) >= 1

    @pytest.mark.asyncio
    async def test_agent_failure_sends_error_reply(self):
        """When run_stream_events raises, on_message sends error reply."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        mock_store = _make_store()

        async def _failing_stream(*args, **kwargs):
            raise RuntimeError("model unavailable")

        bot.agent.run_stream_events = MagicMock(side_effect=_failing_stream)

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

        reply_calls = message.reply.call_args_list
        sorry_calls = [c for c in reply_calls if "trouble" in str(c)]
        assert len(sorry_calls) >= 1


# ---------------------------------------------------------------------------
# should_respond -- resolved=False (falsy bool, not None, not absent attr)
# ---------------------------------------------------------------------------


class TestShouldRespondResolvedFalse:
    def test_reference_resolved_is_false(self):
        """resolved=False (falsy bool) does NOT trigger a response."""
        message = MagicMock()
        message.author.bot = False
        message.mentions = []
        bot_user = MagicMock()
        bot_user.id = 12345

        reference = MagicMock()
        reference.resolved = False  # explicitly boolean False, not None
        message.reference = reference

        assert should_respond(message, bot_user) is False

    def test_reference_resolved_is_zero(self):
        """resolved=0 (falsy int) also does NOT trigger a response."""
        message = MagicMock()
        message.author.bot = False
        message.mentions = []
        bot_user = MagicMock()
        bot_user.id = 12345

        reference = MagicMock()
        reference.resolved = 0
        message.reference = reference

        assert should_respond(message, bot_user) is False


# ---------------------------------------------------------------------------
# _stream_response -- get_recent() returns [] (empty context)
# ---------------------------------------------------------------------------


class TestStreamResponseEmptyContext:
    @pytest.mark.asyncio
    async def test_empty_context_still_calls_agent(self):
        """_stream_response runs the agent even when recent is empty."""
        bot = _make_bot()
        bot_user = bot.user

        msg = _make_message(
            content="Tell me something interesting", mentions=[bot_user]
        )
        mock_store = _make_store()

        events = [_text_delta("Not much context, but here you go!")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        bot.agent.run_stream_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_context_prompt_has_recent_header(self):
        """Prompt has 'Recent conversation:' even when recent is empty."""
        bot = _make_bot()
        bot_user = bot.user

        msg = _make_message(content="Hello?", mentions=[bot_user])
        mock_store = _make_store()

        events = [_text_delta("Hello!")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        assert "Recent conversation:" in prompt_arg

    @pytest.mark.asyncio
    async def test_empty_context_prompt_contains_current_message(self):
        """Current user message is always appended even with no historical context."""
        bot = _make_bot()
        bot_user = bot.user

        msg = _make_message(content="What time is it?", mentions=[bot_user])
        mock_store = _make_store()

        events = [_text_delta("It's time!")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        assert "What time is it?" in prompt_arg
        assert "TestUser" in prompt_arg
