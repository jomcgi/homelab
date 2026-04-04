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

        bot.embed_client.embed = AsyncMock(
            side_effect=RuntimeError("embed service down")
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

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 1024)
        bot.agent.run = AsyncMock(side_effect=RuntimeError("model unavailable"))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise — on_message wraps the whole respond block
            await bot.on_message(message)

        message.reply.assert_not_called()


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
# on_message() -- double-failure: first save succeeds, bot-reply save fails
# ---------------------------------------------------------------------------


class TestOnMessageDoubleSave:
    @pytest.mark.asyncio
    async def test_swallows_bot_reply_storage_failure(self):
        """When reply succeeds but storing the bot response raises, on_message swallows it."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot._connection.user.display_name = "BotUser"
        bot_user = bot.user

        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reference = None
        # reply succeeds and returns a real sent-message mock
        sent_msg = MagicMock()
        sent_msg.id = 777
        message.reply = AsyncMock(return_value=sent_msg)

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 1024)
        mock_agent_result = MagicMock()
        mock_agent_result.output = "Here's my answer!"
        bot.agent.run = AsyncMock(return_value=mock_agent_result)

        call_count = 0

        async def save_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Second call = storing the bot reply → fails
                raise RuntimeError("pgvector unavailable")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.search_similar = MagicMock(return_value=[])
        mock_store.save_message = AsyncMock(side_effect=save_side_effect)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Must not propagate the storage failure
            await bot.on_message(message)

        # reply was called (generate + reply succeeded)
        message.reply.assert_called_once_with("Here's my answer!")
        # save_message called twice: once for incoming, once for bot response
        assert call_count == 2


# ---------------------------------------------------------------------------
# _generate_response() -- both get_recent() and search_similar() return []
# ---------------------------------------------------------------------------


class TestGenerateResponseEmptyContext:
    @pytest.mark.asyncio
    async def test_both_contexts_empty_still_calls_agent(self):
        """_generate_response runs the agent even when recent and similar are both empty."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message(content="Tell me something interesting")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.search_similar = MagicMock(return_value=[])

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 1024)
        mock_agent_result = MagicMock()
        mock_agent_result.output = "Not much context, but here you go!"
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

        assert result == "Not much context, but here you go!"
        bot.agent.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_both_contexts_empty_prompt_has_recent_header_but_no_similar_section(
        self,
    ):
        """Prompt has 'Recent conversation:' but NOT 'Relevant older messages:' when both empty."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message(content="Hello?")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.search_similar = MagicMock(return_value=[])

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 1024)
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
            await bot._generate_response(msg)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert "Recent conversation:" in prompt_arg
        # similar=[] → no "Relevant older messages:" section in prompt
        assert "Relevant older messages:" not in prompt_arg

    @pytest.mark.asyncio
    async def test_both_contexts_empty_prompt_contains_current_message(self):
        """Current user message is always appended even with no historical context."""
        bot = _make_bot()
        bot._connection.user.id = 999

        msg = _make_message(content="What time is it?")

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.search_similar = MagicMock(return_value=[])

        bot.embed_client.embed = AsyncMock(return_value=[0.0] * 1024)
        mock_agent_result = MagicMock()
        mock_agent_result.output = "It's time!"
        bot.agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg)

        prompt_arg = bot.agent.run.call_args[0][0]
        assert "What time is it?" in prompt_arg
        assert "TestUser" in prompt_arg
