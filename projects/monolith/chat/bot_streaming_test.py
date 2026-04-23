"""Tests for the streaming response flow in the Discord bot."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai import (
    FunctionToolCallEvent,
    PartDeltaEvent,
    TextPartDelta,
    ThinkingPartDelta,
)
from pydantic_ai.messages import ToolCallPart

from chat.bot import ChatBot, ThinkingView


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as bot_thinking_test.py)
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_bot() -> ChatBot:
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


def _make_message(content="hello", mentions=None, msg_id=1):
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = 99
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = None
    msg.attachments = []
    msg.embeds = []
    sent = MagicMock(id=100)
    sent.edit = AsyncMock()
    msg.reply = AsyncMock(return_value=sent)
    return msg


def _make_store():
    """Create a mock MessageStore with standard defaults."""
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
# Fake event constructors using real PydanticAI dataclass types
# ---------------------------------------------------------------------------


def _text_delta(content: str) -> PartDeltaEvent:
    """Create a PartDeltaEvent with a TextPartDelta."""
    return PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=content))


def _thinking_delta(content: str) -> PartDeltaEvent:
    """Create a PartDeltaEvent with a ThinkingPartDelta."""
    return PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta=content))


def _tool_call_event(tool_name: str, args: dict) -> FunctionToolCallEvent:
    """Create a FunctionToolCallEvent."""
    part = ToolCallPart(tool_name=tool_name, args=args)
    return FunctionToolCallEvent(part=part)


async def _async_iter(events):
    """Convert a list into an async iterator."""
    for e in events:
        yield e


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_text_only_response_sends_and_edits(self):
        """Text chunks arrive, initial reply is sent, final edit has full text."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_store()

        events = [
            _text_delta("Hello "),
            _text_delta("world!"),
        ]

        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Initial reply was sent with first text chunk
        message.reply.assert_called()
        first_reply_text = message.reply.call_args_list[0][0][0]
        assert "Hello " in first_reply_text

        # Final edit contains full response
        sent = message.reply.return_value
        last_edit_call = sent.edit.call_args_list[-1]
        assert last_edit_call.kwargs.get("content") == "Hello world!"


class TestToolCallIndicator:
    @pytest.mark.asyncio
    async def test_tool_call_shows_searching_indicator(self):
        """Tool call event shows 'Searching...' with bullet for the query."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_store()

        events = [
            _tool_call_event("web_search", {"query": "latest news"}),
            _text_delta("Here are the results."),
        ]

        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # The first reply should contain the searching indicator
        first_content = message.reply.call_args_list[0][0][0]
        assert "Searching" in first_content
        assert "latest news" in first_content


class TestThinkingCollected:
    @pytest.mark.asyncio
    async def test_thinking_collected_for_button(self):
        """Thinking events are collected and ThinkingView is attached on final edit."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_store()

        events = [
            _thinking_delta("Let me think"),
            _thinking_delta(" about this."),
            _text_delta("Here is my answer."),
        ]

        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Final edit should have ThinkingView
        sent = message.reply.return_value
        final_edit = sent.edit.call_args_list[-1]
        view = final_edit.kwargs.get("view")
        assert isinstance(view, ThinkingView)
        assert view.thinking_text == "Let me think about this."


class TestMultipleToolCalls:
    @pytest.mark.asyncio
    async def test_multiple_tool_calls_accumulate(self):
        """Multiple tool calls show multiple bullets."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_store()

        events = [
            _tool_call_event("web_search", {"query": "first query"}),
            _tool_call_event("search_history", {"query": "second query"}),
            _text_delta("Combined results."),
        ]

        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Check that both queries appear in edit calls
        sent = message.reply.return_value
        all_edit_contents = [
            call.kwargs.get("content", "") for call in sent.edit.call_args_list
        ]
        # At least one edit should contain both bullets
        combined = " ".join(all_edit_contents)
        assert "first query" in combined
        assert "second query" in combined


class TestNoEventsFallback:
    @pytest.mark.asyncio
    async def test_no_events_sends_fallback(self):
        """Empty event stream sends fallback message."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(content="Hi", mentions=[bot_user])
        mock_store = _make_store()

        # Empty stream
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter([]))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # Should have sent a fallback message
        reply_text = message.reply.call_args_list[0][0][0]
        assert "Sorry" in reply_text
        assert "trouble" in reply_text
