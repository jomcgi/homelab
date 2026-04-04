"""Tests for Discord bot integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from chat.bot import download_image_attachments, should_respond


class TestShouldRespond:
    def test_responds_to_mention(self):
        """Bot responds when mentioned."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Hello"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = [bot_user]
        assert should_respond(message, bot_user) is True

    def test_ignores_bot_messages(self):
        """Bot does not respond to other bots."""
        message = MagicMock()
        message.author.bot = True
        message.content = "Hello"
        bot_user = MagicMock()
        message.mentions = []
        assert should_respond(message, bot_user) is False

    def test_ignores_unmentioned_messages(self):
        """Bot does not respond to messages that don't mention it."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Hello everyone"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = []
        message.reference = None
        assert should_respond(message, bot_user) is False

    def test_responds_to_reply(self):
        """Bot responds when a message is a reply to a bot message."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Thanks"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = []
        message.reference = MagicMock()
        message.reference.resolved = MagicMock()
        message.reference.resolved.author.id = 12345
        assert should_respond(message, bot_user) is True


class TestDownloadImageAttachments:
    @pytest.mark.asyncio
    async def test_downloads_image_attachments(self):
        """download_image_attachments downloads images and describes them."""
        att = MagicMock()
        att.content_type = "image/png"
        att.filename = "photo.png"
        att.read = AsyncMock(return_value=b"\x89PNG")

        vision_client = AsyncMock()
        vision_client.describe.return_value = "A cat sitting on a chair"

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 1
        assert result[0]["data"] == b"\x89PNG"
        assert result[0]["content_type"] == "image/png"
        assert result[0]["filename"] == "photo.png"
        assert result[0]["description"] == "A cat sitting on a chair"

    @pytest.mark.asyncio
    async def test_skips_non_image_attachments(self):
        """download_image_attachments ignores non-image content types."""
        att = MagicMock()
        att.content_type = "application/pdf"
        att.filename = "doc.pdf"

        vision_client = AsyncMock()

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 0
        vision_client.describe.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_attachment_with_no_content_type(self):
        """download_image_attachments skips attachments without content_type."""
        att = MagicMock()
        att.content_type = None
        att.filename = "unknown"

        vision_client = AsyncMock()

        result = await download_image_attachments([att], vision_client)

        assert len(result) == 0
