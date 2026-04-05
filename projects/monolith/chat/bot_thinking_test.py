"""Tests for thinking mode handling in the Discord bot."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import discord
import httpx
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

from chat.bot import _extract_thinking, _summarize_thinking, ThinkingView, ChatBot


def _make_result(output: str, thinking: str | None = None):
    """Build a mock agent result with optional ThinkingPart."""
    parts = []
    if thinking is not None:
        parts.append(ThinkingPart(content=thinking))
    parts.append(TextPart(content=output))
    response = ModelResponse(parts=parts)
    result = MagicMock()
    result.output = output
    result.new_messages.return_value = [response]
    return result


class TestExtractThinking:
    def test_no_thinking(self):
        """Returns None when no ThinkingPart is present."""
        result = _make_result("Hello!")
        assert _extract_thinking(result) is None

    def test_with_thinking(self):
        """Extracts thinking content from ThinkingPart."""
        result = _make_result("Hello!", thinking="reasoning here")
        assert _extract_thinking(result) == "reasoning here"

    def test_empty_thinking(self):
        """Empty thinking content returns None."""
        result = _make_result("Hello!", thinking="")
        assert _extract_thinking(result) is None

    def test_whitespace_thinking(self):
        """Whitespace-only thinking is stripped and returns None."""
        result = _make_result("Hello!", thinking="   \n  ")
        assert _extract_thinking(result) is None

    def test_multiple_thinking_parts(self):
        """Multiple ThinkingParts are concatenated."""
        parts = [
            ThinkingPart(content="first thought"),
            TextPart(content="middle"),
            ThinkingPart(content="second thought"),
            TextPart(content="end"),
        ]
        response = ModelResponse(parts=parts)
        result = MagicMock()
        result.output = "middleend"
        result.new_messages.return_value = [response]

        assert _extract_thinking(result) == "first thought\n\nsecond thought"

    def test_skips_non_model_response(self):
        """Non-ModelResponse messages are ignored."""
        result = MagicMock()
        result.output = "Hello!"
        result.new_messages.return_value = [MagicMock(spec=[])]
        assert _extract_thinking(result) is None


class TestSummarizeThinking:
    @pytest.mark.asyncio
    async def test_short_thinking_returned_as_is(self):
        """Thinking under 2000 chars is not summarized."""
        result = await _summarize_thinking(
            "short reasoning", base_url="http://fake:8080"
        )
        assert result == "short reasoning"

    @pytest.mark.asyncio
    async def test_long_thinking_calls_llm(self):
        """Thinking over 2000 chars triggers an LLM summarization call."""
        long_text = "x" * 2001
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "summarized"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert result == "summarized"
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_llm_failure_truncates(self):
        """If summarization LLM call fails, truncate to 1990 chars."""
        long_text = "x" * 2500

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_text, base_url="http://fake:8080")

        assert len(result) <= 2000
        assert result.endswith("... (truncated)")


class TestThinkingView:
    def test_view_has_button(self):
        """ThinkingView contains a 'Show thinking' button."""
        view = ThinkingView("some thinking")
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "Show thinking"
        assert buttons[0].style == discord.ButtonStyle.secondary

    def test_view_no_timeout(self):
        """ThinkingView has no timeout."""
        view = ThinkingView("some thinking")
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_button_sends_ephemeral(self):
        """Clicking the button sends thinking as an ephemeral message."""
        view = ThinkingView("my reasoning")
        button = [c for c in view.children if isinstance(c, discord.ui.Button)][0]

        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_called_once_with(
            "my reasoning", ephemeral=True
        )


# Helpers for integration tests (same pattern as bot_coverage_test.py)


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
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


class TestThinkingIntegration:
    @pytest.mark.asyncio
    async def test_response_with_thinking_adds_view(self):
        """When model returns thinking, reply includes ThinkingView."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = _make_result("Hello!", thinking="reasoning here")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot._summarize_thinking",
                new_callable=AsyncMock,
                return_value="reasoning here",
            ),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        call_kwargs = message.reply.call_args
        assert call_kwargs[0][0] == "Hello!"
        assert isinstance(call_kwargs[1].get("view"), ThinkingView)

    @pytest.mark.asyncio
    async def test_response_without_thinking_no_view(self):
        """When model returns plain text, reply has no view."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = _make_result("Hello!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        message.reply.assert_called_once_with("Hello!")

    @pytest.mark.asyncio
    async def test_thinking_only_triggers_retry(self):
        """When model produces only thinking (empty output), bot retries with a nudge."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        thinking_only = _make_result("", thinking="just reasoning")
        proper_response = _make_result("Here's my answer!")
        bot.agent.run = AsyncMock(side_effect=[thinking_only, proper_response])

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        assert bot.agent.run.call_count == 2
        second_prompt = bot.agent.run.call_args_list[1][0][0]
        assert (
            "no visible response" in second_prompt.lower()
            or "respond to the user" in second_prompt.lower()
        )
        message.reply.assert_called_once_with("Here's my answer!")
