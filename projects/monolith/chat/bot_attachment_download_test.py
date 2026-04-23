"""Tests for attachment processing in on_message.

Covers:
- download_image_attachments is called with the message's attachments
- store is passed for blob deduplication
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.bot import ChatBot


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
    msg.embeds = []
    sent = MagicMock(id=100)
    sent.edit = AsyncMock()
    msg.reply = AsyncMock(return_value=sent)
    return msg


# ---------------------------------------------------------------------------
# on_message with non-empty message.attachments
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
        mock_store.acquire_lock = MagicMock(return_value=True)
        mock_store.mark_completed = MagicMock()

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
        sentinel_store.acquire_lock = MagicMock(return_value=True)
        sentinel_store.mark_completed = MagicMock()

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
