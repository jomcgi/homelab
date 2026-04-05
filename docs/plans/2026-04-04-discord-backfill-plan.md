# Discord History Backfill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `POST /api/chat/backfill` endpoint that backfills all Discord channel history into PostgreSQL with embeddings and image attachments.

**Architecture:** Sequential channel iteration with batched embeddings (50 messages per API call). Fire-and-forget background task, observable via SigNoz logs. Reuses existing `download_image_attachments()` for vision and `MessageStore` for persistence.

**Tech Stack:** Python, FastAPI, discord.py, httpx, SQLModel, pgvector, llama.cpp (voyage-4-nano embeddings, Gemma 4 vision)

**Design doc:** `docs/plans/2026-04-04-discord-backfill-design.md`

---

### Task 1: Add `embed_batch()` to EmbeddingClient

**Files:**

- Modify: `projects/monolith/chat/embedding.py`
- Create: `projects/monolith/chat/embedding_batch_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write the failing test**

Create `projects/monolith/chat/embedding_batch_test.py`:

```python
"""Tests for EmbeddingClient.embed_batch()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_returns_vectors_for_multiple_texts(self, client):
        """embed_batch() returns one vector per input text."""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * 1024},
                {"index": 1, "embedding": [0.2] * 1024},
            ]
        }

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await client.embed_batch(["hello", "world"])

        assert len(result) == 2
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_sends_array_input(self, client):
        """embed_batch() sends input as an array to /v1/embeddings."""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "data": [{"index": 0, "embedding": [0.0] * 1024}]
        }

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            await client.embed_batch(["test"])

        payload = mock_client.post.call_args[1]["json"]
        assert payload["input"] == ["test"]

    @pytest.mark.asyncio
    async def test_sorts_by_index(self, client):
        """embed_batch() returns vectors in input order even if API returns out of order."""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.2] * 1024},
                {"index": 0, "embedding": [0.1] * 1024},
            ]
        }

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await client.embed_batch(["first", "second"])

        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)


class TestEmbedUsesEmbedBatch:
    @pytest.mark.asyncio
    async def test_embed_delegates_to_embed_batch(self, client):
        """embed() is a thin wrapper around embed_batch()."""
        with patch.object(client, "embed_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = [[0.5] * 1024]

            result = await client.embed("hello")

        mock_batch.assert_called_once_with(["hello"])
        assert result[0] == pytest.approx(0.5)
```

**Step 2: Verify test fails**

Push to CI. Expected: `AttributeError` — `embed_batch` doesn't exist yet.

**Step 3: Implement `embed_batch()` and refactor `embed()`**

Modify `projects/monolith/chat/embedding.py`:

```python
"""Embedding client -- calls voyage-4-nano via llama.cpp /v1/embeddings."""

import os

import httpx

EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "")


class EmbeddingClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or EMBEDDING_URL

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call, returning vectors in input order."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": texts, "model": "voyage-4-nano"},
            )
            resp.raise_for_status()
            try:
                data = resp.json()["data"]
                sorted_data = sorted(data, key=lambda d: d["index"])
                return [d["embedding"] for d in sorted_data]
            except (KeyError, IndexError) as e:
                raise ValueError(f"unexpected embedding response shape: {e}") from e

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, returning a 1024-dim vector."""
        result = await self.embed_batch([text])
        return result[0]
```

Note: timeout bumped to 60s for batches.

**Step 4: Update existing embedding tests**

In `projects/monolith/chat/embedding_test.py`, the `test_embed_sends_correct_payload` test needs updating since `input` is now an array:

Change the payload assertion from string to array input.

**Step 5: Update BUILD file**

Add `py_test` target for `chat_embedding_batch_test`:

```starlark
py_test(
    name = "chat_embedding_batch_test",
    srcs = ["chat/embedding_batch_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

**Step 6: Verify tests pass**

Push to CI. Expected: all embedding tests pass.

**Step 7: Commit**

```
feat(chat): add embed_batch() to EmbeddingClient

Batches multiple texts into a single /v1/embeddings API call.
embed() now delegates to embed_batch() for a single code path.
```

---

### Task 2: Refactor `save_message()` to use `save_messages()` on MessageStore

**Files:**

- Modify: `projects/monolith/chat/store.py`
- Create: `projects/monolith/chat/store_save_messages_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write the failing test**

Create `projects/monolith/chat/store_save_messages_test.py`:

```python
"""Tests for MessageStore.save_messages() -- batch save with embeddings."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Attachment, Blob, Message
from chat.store import MessageStore, SaveResult


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session (schema-stripped for SQLite compat)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def store(session):
    embed_client = AsyncMock()
    embed_client.embed_batch.return_value = [[0.0] * 1024]
    return MessageStore(session=session, embed_client=embed_client)


class TestSaveMessages:
    @pytest.mark.asyncio
    async def test_saves_single_message(self, store, session):
        """save_messages with one message behaves like old save_message."""
        result = await store.save_messages([
            {
                "discord_message_id": "111",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": "Hello!",
                "is_bot": False,
            }
        ])
        assert result.stored == 1
        assert result.skipped == 0
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 1
        assert msgs[0].content == "Hello!"

    @pytest.mark.asyncio
    async def test_saves_batch_of_messages(self, store, session):
        """save_messages persists multiple messages in one call."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 3
        messages = [
            {
                "discord_message_id": str(i),
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": f"msg {i}",
                "is_bot": False,
            }
            for i in range(3)
        ]
        result = await store.save_messages(messages)
        assert result.stored == 3
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_skips_duplicates(self, store, session):
        """save_messages skips messages with duplicate discord_message_id."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        await store.save_messages([
            {
                "discord_message_id": "dup1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": "First",
                "is_bot": False,
            }
        ])
        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 2
        result = await store.save_messages([
            {
                "discord_message_id": "dup1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": "First again",
                "is_bot": False,
            },
            {
                "discord_message_id": "new1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": "New",
                "is_bot": False,
            },
        ])
        assert result.stored == 1
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_calls_embed_batch(self, store):
        """save_messages calls embed_batch with all message texts."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 2
        await store.save_messages([
            {
                "discord_message_id": "a",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "A",
                "content": "Hello",
                "is_bot": False,
            },
            {
                "discord_message_id": "b",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "B",
                "content": "World",
                "is_bot": False,
            },
        ])
        store.embed_client.embed_batch.assert_called_once_with(["Hello", "World"])

    @pytest.mark.asyncio
    async def test_saves_attachments(self, store, session):
        """save_messages persists attachments alongside messages."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        result = await store.save_messages([
            {
                "discord_message_id": "att1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "Alice",
                "content": "Photo",
                "is_bot": False,
                "attachments": [
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "cat.png",
                        "description": "A cat",
                    }
                ],
            }
        ])
        assert result.stored == 1
        saved = session.exec(select(Attachment)).all()
        assert len(saved) == 1
        assert saved[0].filename == "cat.png"

    @pytest.mark.asyncio
    async def test_embed_text_includes_descriptions(self, store):
        """save_messages includes image descriptions in embed text."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        await store.save_messages([
            {
                "discord_message_id": "d1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "A",
                "content": "Check this",
                "is_bot": False,
                "attachments": [
                    {
                        "data": b"\x89PNG",
                        "content_type": "image/png",
                        "filename": "pic.png",
                        "description": "Sunset",
                    }
                ],
            }
        ])
        embed_texts = store.embed_client.embed_batch.call_args[0][0]
        assert "[Image: Sunset]" in embed_texts[0]

    @pytest.mark.asyncio
    async def test_returns_save_result(self, store):
        """save_messages returns a SaveResult dataclass."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        result = await store.save_messages([
            {
                "discord_message_id": "r1",
                "channel_id": "ch1",
                "user_id": "u1",
                "username": "A",
                "content": "hi",
                "is_bot": False,
            }
        ])
        assert isinstance(result, SaveResult)


class TestSaveMessageBackcompat:
    @pytest.mark.asyncio
    async def test_save_message_delegates_to_save_messages(self, store, session):
        """save_message() still works as a convenience wrapper."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        msg = await store.save_message(
            discord_message_id="bc1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello!",
            is_bot=False,
        )
        assert msg is not None
        assert msg.content == "Hello!"
```

**Step 2: Verify test fails**

Push to CI. Expected: `ImportError` — `SaveResult` doesn't exist, `save_messages` doesn't exist.

**Step 3: Implement `save_messages()` and `SaveResult`**

Modify `projects/monolith/chat/store.py`. Key changes:

1. Add `from dataclasses import dataclass` at top
2. Add `SaveResult` dataclass at module level
3. Add `save_messages()` method using `begin_nested()` savepoints per message
4. Refactor `save_message()` to delegate to `save_messages()`

The new `save_messages()`:

- Builds embed texts from content + image descriptions
- Calls `embed_batch()` once
- Loops through messages, using `begin_nested()` per message for savepoint isolation
- Catches `IntegrityError` per message, rolls back just that savepoint
- `commit()` at the end
- Returns `SaveResult(stored=N, skipped=M)`

The refactored `save_message()`:

- Builds a message dict, calls `save_messages([dict])`
- Returns `None` if skipped, or queries for the saved message to return it

**Step 4: Update existing store test fixtures**

All store test files need their `store` fixture updated from mocking `embed_client.embed` to mocking `embed_client.embed_batch`. This is a mechanical change across:

- `store_test.py`, `store_coverage_test.py`, `store_extra_test.py`
- `store_integrity_test.py`, `store_attachments_test.py`, `store_blob_test.py`
- `store_bulk_test.py`, `store_embed_text_test.py`, `store_upsert_test.py`

In each file:

- `embed_client.embed.return_value = [0.0] * 1024` → `embed_client.embed_batch.return_value = [[0.0] * 1024]`
- `store.embed_client.embed.assert_called_once_with("text")` → `store.embed_client.embed_batch.assert_called_once_with(["text"])`
- `embed_call = store.embed_client.embed.call_args[0][0]` → `embed_call = store.embed_client.embed_batch.call_args[0][0][0]`

**Step 5: Update BUILD file**

Add `py_test` target for `chat_store_save_messages_test`:

```starlark
py_test(
    name = "chat_store_save_messages_test",
    srcs = ["chat/store_save_messages_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 6: Verify all store tests pass**

Push to CI. Expected: all store tests pass.

**Step 7: Commit**

```
feat(chat): add save_messages() for batch persistence

Batch-embeds then saves individually with savepoints for duplicate isolation.
save_message() now delegates to save_messages() for a single code path.
```

---

### Task 3: Create backfill loop in `chat/backfill.py`

**Files:**

- Create: `projects/monolith/chat/backfill.py`
- Create: `projects/monolith/chat/backfill_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write the failing test**

Create `projects/monolith/chat/backfill_test.py`:

```python
"""Tests for Discord history backfill loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.backfill import run_backfill


def _make_discord_message(
    id, content, author_name="Alice", author_id="u1", author_bot=False, attachments=None
):
    """Helper to create a mock discord.Message."""
    msg = MagicMock()
    msg.id = id
    msg.content = content
    msg.author.display_name = author_name
    msg.author.id = author_id
    msg.author.bot = author_bot
    msg.channel.id = "ch1"
    msg.attachments = attachments or []
    return msg


class _AsyncIterator:
    """Wraps a list into an async iterator (simulates channel.history())."""

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


class TestRunBackfill:
    @pytest.mark.asyncio
    async def test_backfills_messages_from_channel(self):
        """run_backfill iterates channel history and saves messages."""
        messages = [_make_discord_message(i, f"msg {i}") for i in range(3)]

        channel = MagicMock()
        channel.name = "general"
        channel.id = "ch1"
        channel.history.return_value = _AsyncIterator(messages)

        guild = MagicMock()
        guild.text_channels = [channel]

        bot = MagicMock()
        bot.guilds = [guild]
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_store = MagicMock()
        mock_store.save_messages = AsyncMock(
            return_value=MagicMock(stored=3, skipped=0)
        )

        with (
            patch("chat.backfill.Session"),
            patch("chat.backfill.get_engine"),
            patch("chat.backfill.MessageStore", return_value=mock_store),
            patch(
                "chat.backfill.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await run_backfill(bot)

        mock_store.save_messages.assert_called_once()
        saved = mock_store.save_messages.call_args[0][0]
        assert len(saved) == 3
        assert saved[0]["content"] == "msg 0"

    @pytest.mark.asyncio
    async def test_batches_at_50_messages(self):
        """run_backfill flushes a batch every 50 messages."""
        messages = [_make_discord_message(i, f"msg {i}") for i in range(75)]

        channel = MagicMock()
        channel.name = "general"
        channel.id = "ch1"
        channel.history.return_value = _AsyncIterator(messages)

        guild = MagicMock()
        guild.text_channels = [channel]

        bot = MagicMock()
        bot.guilds = [guild]
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_store = MagicMock()
        mock_store.save_messages = AsyncMock(
            return_value=MagicMock(stored=50, skipped=0)
        )

        with (
            patch("chat.backfill.Session"),
            patch("chat.backfill.get_engine"),
            patch("chat.backfill.MessageStore", return_value=mock_store),
            patch(
                "chat.backfill.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await run_backfill(bot)

        # 50-message batch + 25-message remainder = 2 calls
        assert mock_store.save_messages.call_count == 2
        first_batch = mock_store.save_messages.call_args_list[0][0][0]
        second_batch = mock_store.save_messages.call_args_list[1][0][0]
        assert len(first_batch) == 50
        assert len(second_batch) == 25

    @pytest.mark.asyncio
    async def test_processes_image_attachments(self):
        """run_backfill downloads and describes image attachments."""
        att = MagicMock()
        att.content_type = "image/png"
        att.filename = "cat.png"
        msg = _make_discord_message(1, "Look!", attachments=[att])

        channel = MagicMock()
        channel.name = "general"
        channel.id = "ch1"
        channel.history.return_value = _AsyncIterator([msg])

        guild = MagicMock()
        guild.text_channels = [channel]

        bot = MagicMock()
        bot.guilds = [guild]
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_store = MagicMock()
        mock_store.save_messages = AsyncMock(
            return_value=MagicMock(stored=1, skipped=0)
        )

        fake_attachment = {
            "data": b"\x89PNG",
            "content_type": "image/png",
            "filename": "cat.png",
            "description": "A cat",
        }
        with (
            patch("chat.backfill.Session"),
            patch("chat.backfill.get_engine"),
            patch("chat.backfill.MessageStore", return_value=mock_store),
            patch(
                "chat.backfill.download_image_attachments",
                new_callable=AsyncMock,
                return_value=[fake_attachment],
            ),
        ):
            await run_backfill(bot)

        saved = mock_store.save_messages.call_args[0][0]
        assert saved[0]["attachments"] == [fake_attachment]

    @pytest.mark.asyncio
    async def test_skips_empty_guilds(self):
        """run_backfill handles guilds with no text channels."""
        guild = MagicMock()
        guild.text_channels = []

        bot = MagicMock()
        bot.guilds = [guild]
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        with (
            patch("chat.backfill.Session"),
            patch("chat.backfill.get_engine"),
            patch("chat.backfill.MessageStore") as mock_store_cls,
        ):
            await run_backfill(bot)

        mock_store_cls.return_value.save_messages.assert_not_called()
```

**Step 2: Verify test fails**

Push to CI. Expected: `ModuleNotFoundError` — `chat.backfill` doesn't exist.

**Step 3: Implement `chat/backfill.py`**

Create `projects/monolith/chat/backfill.py`:

```python
"""Discord history backfill -- iterates all channels and saves messages with embeddings."""

import logging

from sqlmodel import Session

from app.db import get_engine
from chat.bot import download_image_attachments
from chat.store import MessageStore

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def run_backfill(bot) -> None:
    """Backfill all text channels the bot can see."""
    channels = [c for g in bot.guilds for c in g.text_channels]
    logger.info("Starting backfill for %d text channels", len(channels))

    total_stored = 0
    total_skipped = 0

    for channel in channels:
        logger.info("Backfilling #%s (%s)", channel.name, channel.id)
        batch: list[dict] = []
        ch_stored = 0
        ch_skipped = 0

        async for message in channel.history(limit=None, oldest_first=True):
            attachments = await download_image_attachments(
                message.attachments, bot.vision_client, store=None
            )

            msg_dict = {
                "discord_message_id": str(message.id),
                "channel_id": str(channel.id),
                "user_id": str(message.author.id),
                "username": message.author.display_name,
                "content": message.content,
                "is_bot": message.author.bot,
            }
            if attachments:
                msg_dict["attachments"] = attachments

            batch.append(msg_dict)

            if len(batch) >= BATCH_SIZE:
                result = await _flush_batch(batch, bot.embed_client)
                ch_stored += result.stored
                ch_skipped += result.skipped
                batch = []

        if batch:
            result = await _flush_batch(batch, bot.embed_client)
            ch_stored += result.stored
            ch_skipped += result.skipped

        logger.info(
            "#%s done: %d stored, %d skipped", channel.name, ch_stored, ch_skipped
        )
        total_stored += ch_stored
        total_skipped += ch_skipped

    logger.info(
        "Backfill complete: %d stored, %d skipped across %d channels",
        total_stored,
        total_skipped,
        len(channels),
    )


async def _flush_batch(batch, embed_client):
    """Save a batch of messages in a fresh session."""
    with Session(get_engine()) as session:
        store = MessageStore(session=session, embed_client=embed_client)
        return await store.save_messages(batch)
```

**Step 4: Update BUILD file**

Add test target:

```starlark
py_test(
    name = "chat_backfill_test",
    srcs = ["chat/backfill_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pytest_asyncio",
        "@pip//sqlmodel",
    ],
)
```

**Step 5: Verify tests pass**

Push to CI. Expected: all backfill tests pass.

**Step 6: Commit**

```
feat(chat): add Discord history backfill loop

Sequential channel iteration with batched saves (50 messages).
Reuses download_image_attachments() for vision processing.
```

---

### Task 4: Create `chat/router.py` and wire into FastAPI

**Files:**

- Create: `projects/monolith/chat/router.py`
- Create: `projects/monolith/chat/router_test.py`
- Modify: `projects/monolith/app/main.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write the failing test**

Create `projects/monolith/chat/router_test.py`:

```python
"""Tests for chat router -- backfill endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chat.router import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.state.bot = MagicMock()
    app.state.bot.guilds = [MagicMock()]
    app.state.bot.guilds[0].text_channels = [MagicMock(), MagicMock()]
    app.state.backfill_task = None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestBackfillEndpoint:
    def test_returns_202_and_starts_backfill(self, client, app):
        """POST /api/chat/backfill returns 202 and channel count."""
        with patch("chat.router.run_backfill", new_callable=AsyncMock):
            resp = client.post("/api/chat/backfill")
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "started"
        assert body["channels"] == 2

    def test_returns_409_when_already_running(self, client, app):
        """POST /api/chat/backfill returns 409 if backfill is in progress."""
        running_task = MagicMock()
        running_task.done.return_value = False
        app.state.backfill_task = running_task

        resp = client.post("/api/chat/backfill")
        assert resp.status_code == 409

    def test_returns_503_when_no_bot(self, client, app):
        """POST /api/chat/backfill returns 503 if Discord bot is not running."""
        app.state.bot = None
        resp = client.post("/api/chat/backfill")
        assert resp.status_code == 503

    def test_allows_restart_after_previous_completes(self, client, app):
        """POST /api/chat/backfill allows restart when previous task is done."""
        done_task = MagicMock()
        done_task.done.return_value = True
        app.state.backfill_task = done_task

        with patch("chat.router.run_backfill", new_callable=AsyncMock):
            resp = client.post("/api/chat/backfill")
        assert resp.status_code == 202
```

**Step 2: Verify test fails**

Push to CI. Expected: `ModuleNotFoundError` — `chat.router` doesn't exist.

**Step 3: Implement `chat/router.py`**

Create `projects/monolith/chat/router.py`:

```python
"""Chat API routes -- backfill endpoint."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from chat.backfill import run_backfill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/backfill", status_code=202)
async def backfill(request: Request):
    """Launch a background backfill of all Discord channel history."""
    bot = request.app.state.bot
    if not bot:
        raise HTTPException(503, "Discord bot not running")

    task = getattr(request.app.state, "backfill_task", None)
    if task and not task.done():
        raise HTTPException(409, "Backfill already running")

    task = asyncio.create_task(run_backfill(bot))
    request.app.state.backfill_task = task

    channels = [c for g in bot.guilds for c in g.text_channels]
    return {"status": "started", "channels": len(channels)}
```

**Step 4: Wire into `app/main.py`**

Three changes to `projects/monolith/app/main.py`:

1. Add import after other router imports:

   ```python
   from chat.router import router as chat_router
   ```

2. In `lifespan()`, add state initialization before the `bot = None` line:

   ```python
   app.state.bot = None
   app.state.backfill_task = None
   ```

   And after `bot = create_bot()`:

   ```python
   app.state.bot = bot
   ```

3. Register the router with the other `include_router` calls:
   ```python
   app.include_router(chat_router)
   ```

**Step 5: Update BUILD file**

Add test target:

```starlark
py_test(
    name = "chat_router_test",
    srcs = ["chat/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
    ],
)
```

**Step 6: Verify all tests pass**

Push to CI. Expected: all tests pass including existing `main_test.py`.

**Step 7: Commit**

```
feat(chat): add POST /api/chat/backfill endpoint

Fire-and-forget background task with 409 guard against concurrent runs.
Wired into FastAPI via app.state.bot.
```

---

### Task 5: Update existing test mocks for embed_batch refactor

**Files:**

- Modify: `projects/monolith/chat/store_test.py`
- Modify: `projects/monolith/chat/store_coverage_test.py`
- Modify: `projects/monolith/chat/store_extra_test.py`
- Modify: `projects/monolith/chat/store_integrity_test.py`
- Modify: `projects/monolith/chat/store_attachments_test.py`
- Modify: `projects/monolith/chat/store_blob_test.py`
- Modify: `projects/monolith/chat/store_bulk_test.py`
- Modify: `projects/monolith/chat/store_embed_text_test.py`
- Modify: `projects/monolith/chat/store_upsert_test.py`
- Modify: `projects/monolith/chat/store_summary_test.py`
- Modify: `projects/monolith/chat/embedding_test.py`
- Any other test files that mock `embed_client.embed`

**Step 1: Find all test files mocking `embed_client.embed`**

Search for `embed.return_value` and `embed.assert_called` across all test files in `projects/monolith/chat/`.

**Step 2: Update each file mechanically**

For each store test fixture:

- `embed_client.embed.return_value = [0.0] * 1024` → `embed_client.embed_batch.return_value = [[0.0] * 1024]`

For assertion calls:

- `store.embed_client.embed.assert_called_once_with("text")` → `store.embed_client.embed_batch.assert_called_once_with(["text"])`
- `store.embed_client.embed.call_args[0][0]` → `store.embed_client.embed_batch.call_args[0][0][0]`

For `embedding_test.py`:

- The payload assertion needs to expect array input instead of string

For `store_integrity_test.py`:

- This uses a MagicMock session (not real SQLite). The `IntegrityError` now happens at `flush()` inside a `begin_nested()` savepoint, not at `commit()`. The mocks may need adjustment depending on how the new `save_messages()` calls the session.

**Step 3: Run `format`**

```
format
```

**Step 4: Verify full CI passes**

Push to CI. Expected: all tests green.

**Step 5: Commit**

```
fix(chat): update test mocks for embed_batch refactor

All store tests now mock embed_batch instead of embed to match
the new save_messages() code path.
```

---

### Task 6: Update ADR status and bump chart version

**Files:**

- Modify: `docs/decisions/services/001-discord-history-backfill.md`
- Modify: `projects/monolith/chart/Chart.yaml`
- Modify: `projects/monolith/deploy/application.yaml`

**Step 1: Update ADR status**

Change `**Status:** Draft` to `**Status:** Accepted`.

**Step 2: Bump chart version**

Read current `Chart.yaml` version, bump patch. Update `targetRevision` in `deploy/application.yaml` to match. Both files must stay in sync per CLAUDE.md.

**Step 3: Commit**

```
docs: accept discord backfill ADR, bump monolith chart
```

---

### Task 7: Create PR

**Step 1: Push and create PR**

```
git push -u origin feat/discord-backfill
```

Create PR with title `feat(chat): add Discord history backfill endpoint` and body summarizing the changes:

- `embed_batch()` on EmbeddingClient for batched embedding
- `save_messages()` on MessageStore with savepoint-based duplicate isolation
- Sequential backfill loop in `chat/backfill.py`
- `POST /api/chat/backfill` fire-and-forget endpoint with 409 guard

Link to design doc `docs/plans/2026-04-04-discord-backfill-design.md`.

**Step 2: Verify CI passes**

Poll `gh pr view` until CI is green.
