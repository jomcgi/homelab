"""Tests for auto-search on image attachments in _generate_response().

When current_attachments is non-empty, _generate_response() proactively
calls search_web() with the attachment descriptions and injects the results
into the prompt under '[Auto-search results for attached image]'.

Covers:
- Valid descriptions trigger search_web() and inject results into the prompt
- All-failed descriptions ('(image could not be processed)') skip search_web()
- search_web() exceptions are caught and processing continues (graceful degradation)
- No attachments means search_web() is never called
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "check this",
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


def _setup_bot_mocks(bot, response_text="ok"):
    """Wire up store and agent mocks, return the mock store."""
    mock_store = MagicMock()
    mock_store.get_recent = MagicMock(return_value=[])
    mock_store.get_attachments = MagicMock(return_value={})

    mock_result = MagicMock()
    mock_result.new_messages.return_value = []
    mock_result.output = response_text
    bot.agent.run = AsyncMock(return_value=mock_result)

    return mock_store


class TestAutoSearchOnImageAttachments:
    @pytest.mark.asyncio
    async def test_valid_descriptions_trigger_search_and_inject_results(self):
        """Attachments with valid descriptions call search_web() and inject '[Auto-search results for attached image]' into the prompt."""
        bot = _make_bot()
        msg = _make_message(content="What is this headline?")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "headline.png",
                "description": "Breaking news: scientists discover water on Mars",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_search.return_value = "Mars water story: NASA confirms findings"
            await bot._generate_response(msg, current_attachments=attachments)

        # search_web must have been called with the description text
        mock_search.assert_called_once()
        search_query = mock_search.call_args[0][0]
        assert "Breaking news: scientists discover water on Mars" in search_query

        # The prompt forwarded to the agent must contain the auto-search marker
        prompt_arg = bot.agent.run.call_args[0][0]
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "[Auto-search results for attached image]" in text
        assert "Mars water story: NASA confirms findings" in text

    @pytest.mark.asyncio
    async def test_all_failed_descriptions_skip_search_web(self):
        """When all descriptions are '(image could not be processed)', search_web() is not called."""
        bot = _make_bot()
        msg = _make_message(content="Look at this")
        mock_store = _setup_bot_mocks(bot)

        attachments = [
            {
                "data": None,
                "content_type": "image/png",
                "filename": "broken.png",
                "description": "(image could not be processed)",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        mock_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_web_exception_allows_graceful_degradation(self):
        """When search_web() raises an exception, _generate_response() continues and returns the agent response."""
        bot = _make_bot()
        msg = _make_message(content="Check this image")
        mock_store = _setup_bot_mocks(bot, response_text="Here is my answer.")

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "photo.png",
                "description": "A stormy sky over a city",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_search.side_effect = RuntimeError("search service unavailable")
            result = await bot._generate_response(msg, current_attachments=attachments)

        # Must complete without raising and still return the agent's output
        assert result == ("Here is my answer.", None)

        # The agent was still invoked despite the search failure
        bot.agent.run.assert_called_once()

        # Prompt must NOT contain the auto-search results block (search failed)
        prompt_arg = bot.agent.run.call_args[0][0]
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "[Auto-search results for attached image]" not in text

    @pytest.mark.asyncio
    async def test_no_attachments_does_not_call_search_web(self):
        """When current_attachments is None, search_web() is never called."""
        bot = _make_bot()
        msg = _make_message(content="Plain text message, no images")
        mock_store = _setup_bot_mocks(bot)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=None)

        mock_search.assert_not_called()
