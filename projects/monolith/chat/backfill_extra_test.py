"""Extra coverage tests for chat.backfill — error paths, edge cases, and field values."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.backfill import run_backfill
from chat.store import SaveResult


class _AsyncIterator:
    """Simulate an async iterator for channel.history()."""

    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class _FailingAsyncIterator:
    """Async iterator that raises an exception after yielding some items."""

    def __init__(self, items, fail_after=0, exc=None):
        self._items = list(items)
        self._index = 0
        self._fail_after = fail_after
        self._exc = exc or RuntimeError("channel history error")

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= self._fail_after:
            raise self._exc
        item = self._items[self._index]
        self._index += 1
        return item


def _make_discord_message(
    id,
    content,
    author_name="Alice",
    author_id="u1",
    author_bot=False,
    attachments=None,
):
    msg = MagicMock()
    msg.id = id
    msg.content = content
    msg.author.display_name = author_name
    msg.author.id = author_id
    msg.author.bot = author_bot
    msg.channel.id = "ch1"
    msg.attachments = attachments or []
    return msg


def _make_bot(guilds):
    bot = MagicMock()
    bot.guilds = guilds
    bot.embed_client = MagicMock()
    bot.vision_client = MagicMock()
    return bot


def _make_channel(name, channel_id, messages):
    ch = MagicMock()
    ch.name = name
    ch.id = channel_id
    ch.history = MagicMock(return_value=_AsyncIterator(messages))
    return ch


def _make_guild(text_channels):
    guild = MagicMock()
    guild.text_channels = text_channels
    return guild


# ---------------------------------------------------------------------------
# Bot message inclusion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_bot_messages_are_included_in_batch(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """Bot messages (author.bot=True) are not filtered — backfill stores all messages.

    The is_bot flag is preserved in the dict forwarded to save_messages.
    """
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=1, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    bot_msg = _make_discord_message(1, "I am a bot", author_bot=True)
    channel = _make_channel("general", "ch1", [bot_msg])
    guild = _make_guild([channel])
    bot = _make_bot([guild])

    await run_backfill(bot)

    mock_store_instance.save_messages.assert_called_once()
    batch = mock_store_instance.save_messages.call_args[0][0]
    assert len(batch) == 1
    assert batch[0]["is_bot"] is True


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_human_messages_have_is_bot_false(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """Human messages have is_bot=False in the forwarded dict."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=1, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    human_msg = _make_discord_message(2, "hello there", author_bot=False)
    channel = _make_channel("general", "ch1", [human_msg])
    guild = _make_guild([channel])
    bot = _make_bot([guild])

    await run_backfill(bot)

    batch = mock_store_instance.save_messages.call_args[0][0]
    assert batch[0]["is_bot"] is False


# ---------------------------------------------------------------------------
# None-content (embed-only) messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_null_content_message_included_in_batch(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """Messages with content=None (embed-only) pass through with content as None."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=1, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    embed_msg = _make_discord_message(99, None)  # embed-only, no text content
    channel = _make_channel("updates", "ch2", [embed_msg])
    guild = _make_guild([channel])
    bot = _make_bot([guild])

    await run_backfill(bot)

    batch = mock_store_instance.save_messages.call_args[0][0]
    assert len(batch) == 1
    assert batch[0]["content"] is None


# ---------------------------------------------------------------------------
# Attachments key presence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_no_attachments_key_absent_from_dict(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """When download_image_attachments returns [], 'attachments' key is not set."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=1, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    msg = _make_discord_message(1, "hello", attachments=[])
    channel = _make_channel("general", "ch1", [msg])
    guild = _make_guild([channel])
    bot = _make_bot([guild])

    await run_backfill(bot)

    batch = mock_store_instance.save_messages.call_args[0][0]
    assert "attachments" not in batch[0]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_save_messages_failure_propagates(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """If save_messages raises, the exception propagates out of run_backfill."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        side_effect=RuntimeError("db write failure")
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_session.return_value.__exit__ = MagicMock(
        return_value=False
    )  # must not suppress exceptions

    msg = _make_discord_message(1, "hello")
    channel = _make_channel("general", "ch1", [msg])
    guild = _make_guild([channel])
    bot = _make_bot([guild])

    with pytest.raises(RuntimeError, match="db write failure"):
        await run_backfill(bot)


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_channel_history_exception_propagates(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """An exception raised mid-iteration from channel.history() propagates out."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=0, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    ch = MagicMock()
    ch.name = "general"
    ch.id = "ch1"
    ch.history = MagicMock(
        return_value=_FailingAsyncIterator(
            [], fail_after=0, exc=ConnectionError("discord disconnected")
        )
    )
    guild = _make_guild([ch])
    bot = _make_bot([guild])

    with pytest.raises(ConnectionError, match="discord disconnected"):
        await run_backfill(bot)


# ---------------------------------------------------------------------------
# Multi-guild, multi-channel processing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("chat.backfill.get_engine")
@patch("chat.backfill.Session")
@patch("chat.backfill.MessageStore")
@patch("chat.backfill.download_image_attachments", new_callable=AsyncMock)
async def test_multiple_guilds_multiple_channels(
    mock_download, mock_store_cls, mock_session, mock_engine
):
    """Messages from multiple channels across multiple guilds are all flushed."""
    mock_download.return_value = []
    mock_store_instance = MagicMock()
    mock_store_instance.save_messages = AsyncMock(
        return_value=SaveResult(stored=1, skipped=0)
    )
    mock_store_cls.return_value = mock_store_instance
    mock_session.return_value.__enter__ = MagicMock()
    mock_session.return_value.__exit__ = MagicMock()

    ch1 = _make_channel("general", "c1", [_make_discord_message(1, "hi")])
    ch2 = _make_channel("random", "c2", [_make_discord_message(2, "hey")])
    ch3 = _make_channel("news", "c3", [_make_discord_message(3, "yo")])
    guild1 = _make_guild([ch1, ch2])
    guild2 = _make_guild([ch3])
    bot = _make_bot([guild1, guild2])

    await run_backfill(bot)

    # Each channel has 1 message (< BATCH_SIZE) → 1 flush per channel = 3 total
    assert mock_store_instance.save_messages.call_count == 3
