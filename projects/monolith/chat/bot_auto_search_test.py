"""Tests for auto-search on image attachments in the streaming flow.

When current_attachments is non-empty, _stream_response proactively
calls search_web() with the attachment descriptions and injects the results
into the prompt under '[Auto-search results for attached image]'.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, TextPartDelta

from chat.bot import ChatBot


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
    content: str = "check this",
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = None
    msg.embeds = []
    sent = MagicMock(id=100)
    sent.edit = AsyncMock()
    msg.reply = AsyncMock(return_value=sent)
    return msg


def _make_bot() -> ChatBot:
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


def _make_image_attachment(
    filename="headline.png", content_type="image/png", data=b"\x89PNG"
):
    att = MagicMock()
    att.filename = filename
    att.content_type = content_type
    att.read = AsyncMock(return_value=data)
    return att


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoSearchOnImageAttachments:
    @pytest.mark.asyncio
    async def test_valid_descriptions_trigger_search_and_inject_results(self):
        """Attachments with valid descriptions call search_web() and inject results."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="What is this headline?", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("ok")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "headline.png",
                        "description": "Breaking news: scientists discover water on Mars",
                    }
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_search.return_value = "Mars water story: NASA confirms findings"
            await bot.on_message(msg)

        mock_search.assert_called_once()
        search_query = mock_search.call_args[0][0]
        assert "Breaking news: scientists discover water on Mars" in search_query

        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "[Auto-search results for attached image]" in text
        assert "Mars water story: NASA confirms findings" in text

    @pytest.mark.asyncio
    async def test_all_failed_descriptions_skip_search_web(self):
        """When all descriptions are '(image could not be processed)', search_web() is not called."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Look at this", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("ok")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": None,
                        "content_type": "image/png",
                        "filename": "broken.png",
                        "description": "(image could not be processed)",
                    }
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        mock_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_web_exception_allows_graceful_degradation(self):
        """When search_web() raises, _stream_response continues and returns."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(content="Check this image", mentions=[bot_user])
        msg.attachments = [_make_image_attachment()]
        mock_store = _make_store()

        events = [_text_delta("Here is my answer.")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "photo.png",
                        "description": "A stormy sky over a city",
                    }
                ],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_search.side_effect = RuntimeError("search service unavailable")
            await bot.on_message(msg)

        # The agent was still invoked despite the search failure
        bot.agent.run_stream_events.assert_called_once()

        # Prompt must NOT contain the auto-search results block
        prompt_arg = bot.agent.run_stream_events.call_args[0][0]
        text = prompt_arg[0] if isinstance(prompt_arg, list) else prompt_arg
        assert "[Auto-search results for attached image]" not in text

    @pytest.mark.asyncio
    async def test_no_attachments_does_not_call_search_web(self):
        """When there are no attachments, search_web() is never called."""
        bot = _make_bot()
        bot_user = bot.user
        msg = _make_message(
            content="Plain text message, no images", mentions=[bot_user]
        )
        msg.attachments = []
        mock_store = _make_store()

        events = [_text_delta("ok")]
        bot.agent.run_stream_events = MagicMock(return_value=_async_iter(events))

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(msg)

        mock_search.assert_not_called()
