"""Tests for four remaining bot.py coverage gaps.

Covers:
1. _summarize_thinking: uses LLAMA_CPP_URL env-var when base_url=None
2. on_message: integration path with non-empty message.attachments
   (download_image_attachments is called with the message's attachments)
3. _generate_response: m.id is None guard in all_msg_ids list comprehension
   (messages with id=None are excluded from the attachment lookup)
4. _generate_response: data=None attachments with a valid (non-sentinel) description
   still trigger auto-search (but produce no BinaryContent)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent

from chat.bot import ChatBot, _summarize_thinking
from chat.models import Message


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


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


def _make_message(
    content: str = "hello",
    mentions=None,
    msg_id: int = 1,
    attachments=None,
) -> MagicMock:
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
    msg.attachments = attachments if attachments is not None else []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_model_message(id_val=1) -> Message:
    """Build a real Message model object for use in store.get_recent()."""
    return Message(
        id=id_val,
        discord_message_id=str(id_val),
        channel_id="99",
        user_id="u1",
        username="Alice",
        content="hello",
        is_bot=False,
        embedding=[0.0] * 1024,
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Gap 1: _summarize_thinking uses LLAMA_CPP_URL when base_url is None
# ---------------------------------------------------------------------------


class TestSummarizeThinkingEnvFallback:
    @pytest.mark.asyncio
    async def test_uses_llama_cpp_url_when_base_url_is_none(self):
        """_summarize_thinking uses LLAMA_CPP_URL module constant when base_url is not given."""
        long_text = "x" * 2001

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "concise summary"}}]
        }

        with (
            patch("chat.bot.LLAMA_CPP_URL", "http://env-llama:8080"),
            patch("chat.bot.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(long_text)  # no base_url

        assert result == "concise summary"
        call_url = mock_client.post.call_args[0][0]
        assert "http://env-llama:8080" in call_url

    @pytest.mark.asyncio
    async def test_explicit_base_url_overrides_env_var(self):
        """_summarize_thinking uses the explicit base_url, not LLAMA_CPP_URL, when given."""
        long_text = "x" * 2001

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "explicit url result"}}]
        }

        with (
            patch("chat.bot.LLAMA_CPP_URL", "http://env-llama:8080"),
            patch("chat.bot.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _summarize_thinking(
                long_text, base_url="http://explicit:9090"
            )

        assert result == "explicit url result"
        call_url = mock_client.post.call_args[0][0]
        assert "http://explicit:9090" in call_url
        assert "http://env-llama:8080" not in call_url


# ---------------------------------------------------------------------------
# Gap 2: on_message with non-empty message.attachments
# ---------------------------------------------------------------------------


class TestOnMessageWithAttachments:
    @pytest.mark.asyncio
    async def test_download_image_attachments_called_with_message_attachments(self):
        """on_message calls download_image_attachments with the message's attachments."""
        bot = _make_bot()

        fake_attachment = MagicMock()
        fake_attachment.content_type = "image/png"
        fake_attachment.filename = "photo.png"

        message = _make_message(attachments=[fake_attachment])
        # Message is NOT mentioned — just testing the attachment processing path
        message.mentions = []
        message.reference = None

        mock_store = AsyncMock()
        mock_store.save_message = AsyncMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.download_image_attachments", new_callable=AsyncMock
            ) as mock_dl,
        ):
            mock_dl.return_value = []
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            await bot.on_message(message)

        mock_dl.assert_called_once()
        call_args = mock_dl.call_args
        passed_attachments = call_args[0][0]
        assert passed_attachments == [fake_attachment]

    @pytest.mark.asyncio
    async def test_on_message_passes_store_to_download_for_blob_dedup(self):
        """on_message passes the store to download_image_attachments for blob deduplication."""
        bot = _make_bot()

        fake_attachment = MagicMock()
        fake_attachment.content_type = "image/jpeg"
        fake_attachment.filename = "snap.jpg"

        message = _make_message(attachments=[fake_attachment])
        message.mentions = []
        message.reference = None

        sentinel_store = MagicMock()
        sentinel_store.save_message = AsyncMock()

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=sentinel_store),
            patch(
                "chat.bot.download_image_attachments", new_callable=AsyncMock
            ) as mock_dl,
        ):
            mock_dl.return_value = []
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            await bot.on_message(message)

        # store kwarg should have been passed (not None)
        call_kwargs = mock_dl.call_args.kwargs
        passed_store = call_kwargs.get("store")
        assert passed_store is sentinel_store


# ---------------------------------------------------------------------------
# Gap 3: _generate_response filters messages with id=None
# ---------------------------------------------------------------------------


class TestGenerateResponseNoneIdFilter:
    @pytest.mark.asyncio
    async def test_none_id_messages_excluded_from_attachment_lookup(self):
        """Messages with id=None are excluded when building the attachment lookup key list."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(mentions=[bot_user])

        msg_with_id = _make_model_message(id_val=42)
        msg_none_id = _make_model_message(id_val=None)  # type: ignore[arg-type]
        msg_none_id.id = None  # override to force None

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[msg_with_id, msg_none_id])
        mock_store.get_attachments = MagicMock(return_value={})
        mock_store.get_channel_summary = MagicMock(return_value=None)
        mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "response"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(message)

        # get_attachments should have been called; None must not be in the id list
        mock_store.get_attachments.assert_called_once()
        id_list = mock_store.get_attachments.call_args[0][0]
        assert None not in id_list
        assert 42 in id_list

    @pytest.mark.asyncio
    async def test_all_none_ids_produces_empty_attachment_lookup(self):
        """When all recent messages have id=None, get_attachments receives an empty list."""
        bot = _make_bot()
        bot_user = bot.user
        message = _make_message(mentions=[bot_user])

        msg_none = _make_model_message(id_val=1)
        msg_none.id = None

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[msg_none])
        mock_store.get_attachments = MagicMock(return_value={})
        mock_store.get_channel_summary = MagicMock(return_value=None)
        mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "response"
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(message)

        id_list = mock_store.get_attachments.call_args[0][0]
        assert id_list == []


# ---------------------------------------------------------------------------
# Gap 4: data=None attachments with valid (non-sentinel) description
# ---------------------------------------------------------------------------


class TestDataNoneWithValidDescription:
    @pytest.mark.asyncio
    async def test_data_none_valid_description_triggers_auto_search(self):
        """Attachment with data=None but a valid description still triggers auto-search."""
        bot = _make_bot()
        message = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})
        mock_store.get_channel_summary = MagicMock(return_value=None)
        mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "Here is the answer"
        bot.agent.run = AsyncMock(return_value=mock_result)

        # data=None (download failed) but description is NOT the sentinel value
        attachments = [
            {
                "data": None,
                "content_type": "image/png",
                "filename": "broken.png",
                "description": "A political cartoon about AI regulation",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_search.return_value = "search results"
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(message, current_attachments=attachments)

        # Auto-search IS triggered because the description is valid (not the sentinel)
        mock_search.assert_called_once()
        search_query = mock_search.call_args[0][0]
        assert "A political cartoon about AI regulation" in search_query

    @pytest.mark.asyncio
    async def test_data_none_valid_description_produces_no_binary_content(self):
        """Attachment with data=None produces no BinaryContent even with a valid description."""
        bot = _make_bot()
        message = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})
        mock_store.get_channel_summary = MagicMock(return_value=None)
        mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "response"
        bot.agent.run = AsyncMock(return_value=mock_result)

        attachments = [
            {
                "data": None,
                "content_type": "image/jpeg",
                "filename": "broken.jpg",
                "description": "A sunset over the ocean",  # valid, not sentinel
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(message, current_attachments=attachments)

        # Since data=None → no BinaryContent → agent_prompt is a plain string
        prompt_arg = bot.agent.run.call_args[0][0]
        assert isinstance(prompt_arg, str), (
            "When all attachment data is None, agent_prompt should be a plain string "
            f"(no image_parts), got {type(prompt_arg).__name__}"
        )
        # Binary content should not be present
        if isinstance(prompt_arg, list):
            binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
            assert len(binary_parts) == 0

    @pytest.mark.asyncio
    async def test_data_none_valid_description_still_includes_text_context(self):
        """Attachment with data=None but valid description still adds text context to prompt."""
        bot = _make_bot()
        message = _make_message()

        mock_store = MagicMock()
        mock_store.get_recent = MagicMock(return_value=[])
        mock_store.get_attachments = MagicMock(return_value={})
        mock_store.get_channel_summary = MagicMock(return_value=None)
        mock_store.get_user_summaries_for_users = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.new_messages.return_value = []
        mock_result.output = "response"
        bot.agent.run = AsyncMock(return_value=mock_result)

        attachments = [
            {
                "data": None,
                "content_type": "image/png",
                "filename": "meme.png",
                "description": "A funny meme about Python",
            }
        ]

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock),
        ):
            ctx = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(message, current_attachments=attachments)

        # The text description should still appear in the prompt
        prompt_arg = bot.agent.run.call_args[0][0]
        text = prompt_arg if isinstance(prompt_arg, str) else prompt_arg[0]
        assert "A funny meme about Python" in text
        assert "meme.png" in text
