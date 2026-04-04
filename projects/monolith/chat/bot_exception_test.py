"""Tests for download_image_attachments() exception swallowing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat.bot import download_image_attachments


class TestDownloadImageAttachmentsExceptions:
    @pytest.mark.asyncio
    async def test_swallows_exception_during_read(self):
        """download_image_attachments() continues when att.read() raises."""
        att = MagicMock()
        att.content_type = "image/png"
        att.filename = "broken.png"
        att.read = AsyncMock(side_effect=IOError("connection reset"))

        vision_client = AsyncMock()

        result = await download_image_attachments([att], vision_client)

        # Exception is swallowed; result is empty rather than propagating
        assert result == []
        vision_client.describe.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_exception_during_vision_describe(self):
        """download_image_attachments() continues when vision_client.describe() raises."""
        att = MagicMock()
        att.content_type = "image/jpeg"
        att.filename = "bad_vision.jpg"
        att.read = AsyncMock(return_value=b"\xff\xd8\xff")

        vision_client = AsyncMock()
        vision_client.describe.side_effect = RuntimeError("vision model crashed")

        result = await download_image_attachments([att], vision_client)

        assert result == []

    @pytest.mark.asyncio
    async def test_continues_with_remaining_attachments_after_exception(self):
        """A failing attachment does not prevent subsequent attachments from processing."""
        bad_att = MagicMock()
        bad_att.content_type = "image/png"
        bad_att.filename = "bad.png"
        bad_att.read = AsyncMock(side_effect=IOError("read failed"))

        good_att = MagicMock()
        good_att.content_type = "image/png"
        good_att.filename = "good.png"
        good_att.read = AsyncMock(return_value=b"\x89PNG")

        vision_client = AsyncMock()
        vision_client.describe.return_value = "A green meadow"

        result = await download_image_attachments([bad_att, good_att], vision_client)

        # Only the successful attachment appears in results
        assert len(result) == 1
        assert result[0]["filename"] == "good.png"
        assert result[0]["description"] == "A green meadow"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_all_attachments_fail(self):
        """download_image_attachments() returns [] when every attachment raises."""
        att1 = MagicMock()
        att1.content_type = "image/png"
        att1.filename = "fail1.png"
        att1.read = AsyncMock(side_effect=IOError("fail"))

        att2 = MagicMock()
        att2.content_type = "image/jpeg"
        att2.filename = "fail2.jpg"
        att2.read = AsyncMock(side_effect=IOError("fail"))

        vision_client = AsyncMock()

        result = await download_image_attachments([att1, att2], vision_client)

        assert result == []
