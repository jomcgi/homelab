"""Tests for thinking mode handling in the Discord bot."""

import pytest

from chat.bot import _parse_thinking


class TestParseThinking:
    def test_no_thinking_tags(self):
        """Plain text without <think> tags passes through unchanged."""
        response, thinking = _parse_thinking("Hello world!")
        assert response == "Hello world!"
        assert thinking is None

    def test_thinking_and_response(self):
        """Extracts thinking and returns clean response."""
        text = "<think>I should greet them.</think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "I should greet them."

    def test_thinking_with_whitespace(self):
        """Strips whitespace between thinking block and response."""
        text = "<think>reasoning</think>\n\nHello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking == "reasoning"

    def test_thinking_only_empty_response(self):
        """Returns empty response when model only produces thinking."""
        text = "<think>I'm just thinking here.</think>"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "I'm just thinking here."

    def test_thinking_only_whitespace_response(self):
        """Whitespace-only response after thinking is treated as empty."""
        text = "<think>reasoning</think>   \n  "
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "reasoning"

    def test_multiple_think_blocks(self):
        """Multiple <think> blocks are concatenated."""
        text = "<think>first</think>middle<think>second</think>end"
        response, thinking = _parse_thinking(text)
        assert response == "middleend"
        assert thinking == "first\n\nsecond"

    def test_unclosed_think_tag(self):
        """Unclosed <think> tag — treat entire remainder as thinking."""
        text = "<think>no closing tag here"
        response, thinking = _parse_thinking(text)
        assert response == ""
        assert thinking == "no closing tag here"

    def test_empty_think_block(self):
        """Empty <think></think> produces no thinking text."""
        text = "<think></think>Hello!"
        response, thinking = _parse_thinking(text)
        assert response == "Hello!"
        assert thinking is None


from unittest.mock import AsyncMock, patch, MagicMock
import discord
import httpx

from chat.bot import _summarize_thinking, ThinkingView, ChatBot


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
        """When model returns <think>...</think>, reply includes ThinkingView."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        mock_result = MagicMock()
        mock_result.output = "<think>reasoning here</think>Hello!"
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

        mock_result = MagicMock()
        mock_result.output = "Hello!"
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
        """When model produces only thinking, bot retries with a nudge."""
        bot = _make_bot()
        bot_user = bot.user

        message = _make_message(content="Hi", mentions=[bot_user])

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})

        thinking_only = MagicMock()
        thinking_only.output = "<think>just reasoning</think>"
        proper_response = MagicMock()
        proper_response.output = "Here's my answer!"
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
