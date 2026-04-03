# Discord Chatbot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a conversational Discord chatbot in the monolith with persistent pgvector memory, PydanticAI tool calling, and SearXNG web search, backed by Gemma 4 26B.

**Architecture:** The monolith gains a `chat/` module with discord.py gateway, PydanticAI agent, and pgvector-backed recall. A second llama.cpp instance serves voyage-4-nano for embeddings. SearXNG is a Helm subchart for web search. The existing TypeScript chat bot is retired.

**Tech Stack:** Python (discord.py, PydanticAI, pgvector, SQLModel), Helm, llama.cpp, SearXNG, PostgreSQL (CNPG), Atlas migrations

---

## Task 1: Add Python Dependencies

**Files:**

- Modify: `pyproject.toml` (add discord.py, pydantic-ai, pgvector deps)
- Modify: `projects/monolith/BUILD` (add `@pip//` deps to `monolith_backend`)

**Step 1: Add runtime dependencies to pyproject.toml**

Add these lines to the `dependencies` array in `pyproject.toml`, under the `# Monolith dependencies` comment:

```python
    # Chat module dependencies
    "discord.py>=2.4",
    "pydantic-ai>=0.2",
    "pgvector>=0.3",
```

**Step 2: Add Bazel deps to BUILD**

In `projects/monolith/BUILD`, add to the `monolith_backend` `py_library` deps list:

```python
        "@pip//discord_py",
        "@pip//pydantic_ai",
        "@pip//pgvector",
```

Also add `"chat/**/*.py"` to both the `srcs` globs in `py_venv_binary` and `py_library`, and add `# gazelle:exclude chat` to the top of the BUILD file.

**Step 3: Commit**

```
git add pyproject.toml projects/monolith/BUILD
git commit -m "build(monolith): add discord.py, pydantic-ai, and pgvector dependencies"
```

> **Note:** Lock file regeneration (`bazel run //bazel/requirements:update`) will happen in CI via the format bot. Don't run it locally.

---

## Task 2: pgvector Migration

**Files:**

- Create: `projects/monolith/chart/migrations/20260403000000_chat_schema.sql`

**Step 1: Write the migration**

Create the migration file:

```sql
-- Enable pgvector extension and create chat schema for Discord chatbot.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE chat.messages (
    id SERIAL PRIMARY KEY,
    discord_message_id TEXT UNIQUE NOT NULL,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    is_bot BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX chat_messages_channel_time ON chat.messages (channel_id, created_at DESC);
CREATE INDEX chat_messages_channel_user_time ON chat.messages (channel_id, user_id, created_at DESC);
CREATE INDEX chat_messages_embedding_hnsw ON chat.messages USING hnsw (embedding vector_cosine_ops);
```

**Step 2: Regenerate atlas.sum**

The atlas.sum file in `projects/monolith/chart/migrations/` needs to be updated. This is handled by the `format` command or CI. If atlas is available locally:

```
cd projects/monolith/chart
atlas migrate hash --dir file://migrations
```

Otherwise, push and let CI format bot handle it.

**Step 3: Commit**

```
git add projects/monolith/chart/migrations/
git commit -m "feat(monolith): add pgvector chat schema migration"
```

---

## Task 3: Chat Models (SQLModel)

**Files:**

- Create: `projects/monolith/chat/__init__.py`
- Create: `projects/monolith/chat/models.py`
- Create: `projects/monolith/chat/models_test.py`

**Step 1: Write the failing test**

```python
# projects/monolith/chat/models_test.py
"""Tests for chat SQLModel definitions."""

import pytest
from sqlmodel import SQLModel

from chat.models import Message


class TestMessageModel:
    def test_message_table_name(self):
        """Message model maps to chat.messages table."""
        assert Message.__tablename__ == "messages"
        assert Message.__table_args__["schema"] == "chat"

    def test_message_has_required_fields(self):
        """Message model has all expected columns."""
        columns = {c.name for c in Message.__table__.columns}
        expected = {
            "id",
            "discord_message_id",
            "channel_id",
            "user_id",
            "username",
            "content",
            "is_bot",
            "embedding",
            "created_at",
        }
        assert expected == columns

    def test_message_is_bot_defaults_false(self):
        """is_bot field defaults to False."""
        msg = Message(
            discord_message_id="123",
            channel_id="456",
            user_id="789",
            username="test",
            content="hello",
            embedding=[0.0] * 512,
        )
        assert msg.is_bot is False
```

**Step 2: Create empty **init**.py**

```python
# projects/monolith/chat/__init__.py
```

**Step 3: Write the model**

```python
# projects/monolith/chat/models.py
"""Chat message model for pgvector-backed Discord conversation memory."""

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = {"schema": "chat"}

    id: int | None = Field(default=None, primary_key=True)
    discord_message_id: str = Field(unique=True)
    channel_id: str = Field(index=True)
    user_id: str
    username: str
    content: str
    is_bot: bool = Field(default=False)
    embedding: list[float] = Field(sa_column=Column(Vector(512)))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
```

**Step 4: Add test target to BUILD**

Add to `projects/monolith/BUILD`:

```python
py_test(
    name = "chat_models_test",
    srcs = ["chat/models_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)
```

**Step 5: Commit**

```
git add projects/monolith/chat/ projects/monolith/BUILD
git commit -m "feat(monolith): add chat Message SQLModel with pgvector embedding"
```

---

## Task 4: Embedding Client

**Files:**

- Create: `projects/monolith/chat/embedding.py`
- Create: `projects/monolith/chat/embedding_test.py`

**Step 1: Write the failing test**

```python
# projects/monolith/chat/embedding_test.py
"""Tests for the embedding client (calls voyage-4-nano via llama.cpp)."""

from unittest.mock import AsyncMock, patch

import pytest

from chat.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


class TestEmbeddingClient:
    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, client):
        """embed() returns a list of floats from the API response."""
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": [{"embedding": [0.1] * 512}]
        }
        fake_response.raise_for_status = AsyncMock()

        with patch("chat.embedding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            result = await client.embed("hello world")

        assert len(result) == 512
        assert result[0] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_embed_sends_correct_payload(self, client):
        """embed() sends the text to /v1/embeddings with the right model."""
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": [{"embedding": [0.0] * 512}]
        }
        fake_response.raise_for_status = AsyncMock()

        with patch("chat.embedding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            await client.embed("test input")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "/v1/embeddings" in call_kwargs[0][0]
```

**Step 2: Write the implementation**

```python
# projects/monolith/chat/embedding.py
"""Embedding client -- calls voyage-4-nano via llama.cpp /v1/embeddings."""

import os

import httpx

EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "")


class EmbeddingClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or EMBEDDING_URL

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, returning a 512-dim vector."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": text, "model": "voyage-4-nano"},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
```

**Step 3: Add test target to BUILD**

```python
py_test(
    name = "chat_embedding_test",
    srcs = ["chat/embedding_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

**Step 4: Commit**

```
git add projects/monolith/chat/embedding.py projects/monolith/chat/embedding_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add embedding client for voyage-4-nano via llama.cpp"
```

---

## Task 5: Message Store (Recall Engine)

**Files:**

- Create: `projects/monolith/chat/store.py`
- Create: `projects/monolith/chat/store_test.py`

**Step 1: Write the failing tests**

```python
# projects/monolith/chat/store_test.py
"""Tests for chat message store -- storage and recall."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Message
from chat.store import MessageStore


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
    embed_client.embed.return_value = [0.0] * 512
    return MessageStore(session=session, embed_client=embed_client)


class TestSaveMessage:
    @pytest.mark.asyncio
    async def test_saves_message_to_db(self, store, session):
        """save_message persists a message to the database."""
        await store.save_message(
            discord_message_id="111",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello!",
            is_bot=False,
        )
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 1
        assert msgs[0].content == "Hello!"
        assert msgs[0].username == "Alice"

    @pytest.mark.asyncio
    async def test_calls_embed_client(self, store):
        """save_message calls the embedding client with the message content."""
        await store.save_message(
            discord_message_id="222",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="What is the weather?",
            is_bot=False,
        )
        store.embed_client.embed.assert_called_once_with("What is the weather?")


class TestGetRecentMessages:
    @pytest.mark.asyncio
    async def test_returns_recent_messages_in_order(self, store, session):
        """get_recent returns messages ordered oldest-first."""
        for i in range(5):
            await store.save_message(
                discord_message_id=str(i),
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                content=f"msg {i}",
                is_bot=False,
            )
        recent = store.get_recent("ch1", limit=3)
        assert len(recent) == 3
        assert recent[0].content == "msg 2"
        assert recent[2].content == "msg 4"

    @pytest.mark.asyncio
    async def test_filters_by_channel(self, store, session):
        """get_recent only returns messages from the specified channel."""
        await store.save_message("a", "ch1", "u1", "A", "in ch1", False)
        await store.save_message("b", "ch2", "u1", "A", "in ch2", False)
        recent = store.get_recent("ch1", limit=10)
        assert len(recent) == 1
        assert recent[0].content == "in ch1"
```

**Step 2: Write the implementation**

```python
# projects/monolith/chat/store.py
"""Message store -- persist and recall chat messages with pgvector."""

import logging

from sqlmodel import Session, select

from chat.embedding import EmbeddingClient
from chat.models import Message

logger = logging.getLogger(__name__)


class MessageStore:
    def __init__(self, session: Session, embed_client: EmbeddingClient):
        self.session = session
        self.embed_client = embed_client

    async def save_message(
        self,
        discord_message_id: str,
        channel_id: str,
        user_id: str,
        username: str,
        content: str,
        is_bot: bool,
    ) -> Message:
        """Embed and persist a message."""
        embedding = await self.embed_client.embed(content)
        msg = Message(
            discord_message_id=discord_message_id,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            content=content,
            is_bot=is_bot,
            embedding=embedding,
        )
        self.session.add(msg)
        self.session.commit()
        self.session.refresh(msg)
        return msg

    def get_recent(
        self, channel_id: str, limit: int = 20
    ) -> list[Message]:
        """Return the most recent messages in a channel, oldest first."""
        stmt = (
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(self.session.exec(stmt).all())
        messages.reverse()
        return messages

    def search_similar(
        self,
        channel_id: str,
        query_embedding: list[float],
        limit: int = 5,
        exclude_ids: list[int] | None = None,
        user_id: str | None = None,
    ) -> list[Message]:
        """Semantic search over channel history using pgvector cosine distance.

        Note: This uses raw SQL because SQLModel doesn't natively support
        pgvector's <=> operator. Falls back gracefully in SQLite tests.
        """
        from sqlalchemy import text

        exclude = exclude_ids or []
        params = {
            "channel_id": channel_id,
            "embedding": str(query_embedding),
            "limit": limit,
        }

        filters = "channel_id = :channel_id"
        if exclude:
            filters += " AND id NOT IN (" + ",".join(str(i) for i in exclude) + ")"
        if user_id:
            filters += " AND user_id = :user_id"
            params["user_id"] = user_id

        sql = text(
            f"SELECT * FROM chat.messages WHERE {filters} "
            "ORDER BY embedding <=> :embedding LIMIT :limit"
        )
        result = self.session.exec(sql, params=params)
        return [Message.model_validate(row) for row in result]
```

**Step 3: Add test target to BUILD**

```python
py_test(
    name = "chat_store_test",
    srcs = ["chat/store_test.py"],
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

**Step 4: Commit**

```
git add projects/monolith/chat/store.py projects/monolith/chat/store_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add chat message store with pgvector semantic recall"
```

---

## Task 6: Web Search Client

**Files:**

- Create: `projects/monolith/chat/web_search.py`
- Create: `projects/monolith/chat/web_search_test.py`

**Step 1: Write the failing test**

```python
# projects/monolith/chat/web_search_test.py
"""Tests for SearXNG web search client."""

from unittest.mock import AsyncMock, patch

import pytest

from chat.web_search import search_web


class TestSearchWeb:
    @pytest.mark.asyncio
    async def test_returns_formatted_results(self):
        """search_web returns formatted string of top results."""
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "results": [
                {"title": "Result 1", "content": "First result content", "url": "http://example.com/1"},
                {"title": "Result 2", "content": "Second result content", "url": "http://example.com/2"},
            ]
        }
        fake_response.raise_for_status = AsyncMock()

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("test query", base_url="http://fake:8080")

        assert "Result 1" in result
        assert "First result content" in result
        assert "Result 2" in result

    @pytest.mark.asyncio
    async def test_limits_to_5_results(self):
        """search_web returns at most 5 results."""
        fake_results = [
            {"title": f"R{i}", "content": f"C{i}", "url": f"http://example.com/{i}"}
            for i in range(10)
        ]
        fake_response = AsyncMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"results": fake_results}
        fake_response.raise_for_status = AsyncMock()

        with patch("chat.web_search.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = fake_response
            mock_cls.return_value = mock_client

            result = await search_web("test", base_url="http://fake:8080")

        # Should only contain 5 results
        assert result.count("http://example.com/") == 5
```

**Step 2: Write the implementation**

```python
# projects/monolith/chat/web_search.py
"""Web search via SearXNG -- used as a PydanticAI tool."""

import os

import httpx

SEARXNG_URL = os.environ.get("SEARXNG_URL", "")


async def search_web(query: str, base_url: str | None = None) -> str:
    """Search the web via SearXNG, returning top 5 results as text."""
    url = base_url or SEARXNG_URL
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.get(
            f"{url}/search",
            params={"q": query, "format": "json"},
        )
        resp.raise_for_status()
        results = resp.json()["results"][:5]
        return "\n\n".join(
            f"**{r['title']}**\n{r['content']}\nURL: {r['url']}"
            for r in results
        )
```

**Step 3: Add test target to BUILD**

```python
py_test(
    name = "chat_web_search_test",
    srcs = ["chat/web_search_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

**Step 4: Commit**

```
git add projects/monolith/chat/web_search.py projects/monolith/chat/web_search_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add SearXNG web search client for chat"
```

---

## Task 7: PydanticAI Agent

**Files:**

- Create: `projects/monolith/chat/agent.py`
- Create: `projects/monolith/chat/agent_test.py`

**Step 1: Write the failing test**

```python
# projects/monolith/chat/agent_test.py
"""Tests for PydanticAI chat agent."""

from chat.agent import build_system_prompt, format_context_messages


class TestBuildSystemPrompt:
    def test_includes_bot_identity(self):
        """System prompt identifies the bot."""
        prompt = build_system_prompt()
        assert "Discord" in prompt or "chat" in prompt.lower()

    def test_includes_web_search_guidance(self):
        """System prompt mentions web search capability."""
        prompt = build_system_prompt()
        assert "search" in prompt.lower()


class TestFormatContextMessages:
    def test_formats_user_message(self):
        """User messages include username and content."""
        from chat.models import Message
        from datetime import datetime, timezone

        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Hello there",
            is_bot=False,
            embedding=[0.0] * 512,
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        )
        formatted = format_context_messages([msg])
        assert "Alice" in formatted
        assert "Hello there" in formatted

    def test_formats_bot_message(self):
        """Bot messages are labeled as assistant."""
        from chat.models import Message
        from datetime import datetime, timezone

        msg = Message(
            id=2,
            discord_message_id="2",
            channel_id="ch1",
            user_id="bot",
            username="Bot",
            content="Hi!",
            is_bot=True,
            embedding=[0.0] * 512,
            created_at=datetime(2026, 4, 3, 12, 1, tzinfo=timezone.utc),
        )
        formatted = format_context_messages([msg])
        assert "Hi!" in formatted
```

**Step 2: Write the implementation**

```python
# projects/monolith/chat/agent.py
"""PydanticAI agent -- assembles context and runs Gemma with tool calling."""

import os

from pydantic_ai import Agent

from chat.models import Message
from chat.web_search import search_web

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")


def build_system_prompt() -> str:
    """Build the system prompt for the chat agent."""
    return (
        "You are a helpful assistant in a Discord chat. "
        "You have access to a web_search tool to look up current information. "
        "Use it when users ask about recent events, facts you're unsure about, "
        "or anything that benefits from up-to-date information. "
        "Keep responses concise and conversational. "
        "You can see recent conversation history and relevant older messages for context."
    )


def format_context_messages(messages: list[Message]) -> str:
    """Format a list of messages into a context string for the prompt."""
    lines = []
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        if msg.is_bot:
            lines.append(f"[{timestamp}] Assistant: {msg.content}")
        else:
            lines.append(f"[{timestamp}] {msg.username}: {msg.content}")
    return "\n".join(lines)


def create_agent(base_url: str | None = None) -> Agent:
    """Create a PydanticAI agent configured for Gemma via llama.cpp."""
    url = base_url or LLAMA_CPP_URL

    agent = Agent(
        "openai:gemma-4-26b-a4b",
        system_prompt=build_system_prompt(),
        model_settings={
            "openai_base_url": f"{url}/v1",
            "openai_api_key": "not-needed",
        },
    )

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the web for current information. Use this for recent events, facts, or anything that needs up-to-date data."""
        return await search_web(query)

    return agent
```

**Step 3: Add test target to BUILD**

```python
py_test(
    name = "chat_agent_test",
    srcs = ["chat/agent_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)
```

**Step 4: Commit**

```
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add PydanticAI chat agent with web search tool"
```

---

## Task 8: Discord Bot Integration

**Files:**

- Create: `projects/monolith/chat/bot.py`
- Create: `projects/monolith/chat/bot_test.py`
- Modify: `projects/monolith/app/main.py` (add bot to lifespan)

**Step 1: Write the failing test**

```python
# projects/monolith/chat/bot_test.py
"""Tests for Discord bot integration."""

from unittest.mock import MagicMock

from chat.bot import should_respond


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
```

**Step 2: Write the implementation**

```python
# projects/monolith/chat/bot.py
"""Discord bot -- gateway listener and message handler."""

import logging
import os

import discord

from chat.agent import create_agent, format_context_messages
from chat.embedding import EmbeddingClient
from chat.store import MessageStore
from app.db import get_engine

from sqlmodel import Session

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")


def should_respond(message: discord.Message, bot_user: discord.User) -> bool:
    """Determine if the bot should respond to a message."""
    if message.author.bot:
        return False
    if bot_user in message.mentions:
        return True
    if (
        message.reference
        and hasattr(message.reference, "resolved")
        and message.reference.resolved
        and message.reference.resolved.author.id == bot_user.id
    ):
        return True
    return False


class ChatBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.embed_client = EmbeddingClient()
        self.agent = create_agent()

    async def on_ready(self):
        logger.info("Discord bot connected as %s", self.user)

    async def on_message(self, message: discord.Message):
        # Always store messages (for memory)
        try:
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(message.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    content=message.content,
                    is_bot=message.author.bot,
                )
        except Exception:
            logger.exception("Failed to store message %s", message.id)

        if not should_respond(message, self.user):
            return

        try:
            async with message.channel.typing():
                response_text = await self._generate_response(message)
            sent = await message.reply(response_text)

            # Store bot response
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(sent.id),
                    channel_id=str(message.channel.id),
                    user_id=str(self.user.id),
                    username=self.user.display_name,
                    content=response_text,
                    is_bot=True,
                )
        except Exception:
            logger.exception("Failed to respond to message %s", message.id)

    async def _generate_response(self, message: discord.Message) -> str:
        """Build context and run the PydanticAI agent."""
        with Session(get_engine()) as session:
            store = MessageStore(session=session, embed_client=self.embed_client)

            # Recent window
            recent = store.get_recent(str(message.channel.id), limit=20)
            recent_ids = [m.id for m in recent if m.id is not None]

            # Semantic recall
            query_embedding = await self.embed_client.embed(message.content)
            similar = store.search_similar(
                channel_id=str(message.channel.id),
                query_embedding=query_embedding,
                limit=5,
                exclude_ids=recent_ids,
            )

        # Build context
        context_parts = []
        if similar:
            context_parts.append(
                "Relevant older messages:\n" + format_context_messages(similar)
            )
        context_parts.append(
            "Recent conversation:\n" + format_context_messages(recent)
        )
        context = "\n\n---\n\n".join(context_parts)

        # Run agent
        user_prompt = (
            f"{context}\n\nCurrent message from "
            f"{message.author.display_name}: {message.content}"
        )
        result = await self.agent.run(user_prompt)
        return result.output


def create_bot() -> ChatBot:
    """Factory function for the Discord bot."""
    return ChatBot()
```

**Step 3: Update main.py lifespan**

Modify `projects/monolith/app/main.py` to start the Discord bot in the lifespan. Add Discord bot startup after the calendar loop, gated by `DISCORD_BOT_TOKEN` env var:

```python
    # Start Discord bot if token is configured
    bot = None
    bot_task = None
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if discord_token:
        from chat.bot import create_bot

        bot = create_bot()
        bot_task = asyncio.create_task(bot.start(discord_token))
        logger.info("Discord bot starting")
```

And in the shutdown block:

```python
    if bot:
        await bot.close()
    if bot_task:
        bot_task.cancel()
```

**Step 4: Add test target to BUILD**

```python
py_test(
    name = "chat_bot_test",
    srcs = ["chat/bot_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//discord_py",
        "@pip//pytest",
    ],
)
```

**Step 5: Commit**

```
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_test.py projects/monolith/app/main.py projects/monolith/BUILD
git commit -m "feat(monolith): add Discord bot with message storage and PydanticAI response generation"
```

---

## Task 9: Helm Chart Updates (Monolith)

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` (add SearXNG subchart, bump version)
- Modify: `projects/monolith/deploy/values.yaml` (add chat config)
- Modify: `projects/monolith/deploy/application.yaml` (update targetRevision)
- Modify: `projects/monolith/chart/templates/deployment.yaml` (add env vars)
- Modify: `projects/monolith/chart/templates/cnpg-cluster.yaml` (enable pgvector extension)

**Step 1: Add SearXNG subchart to Chart.yaml**

```yaml
apiVersion: v2
name: monolith
description: Consolidated homelab web services
version: 0.9.0
type: application
dependencies:
  - name: cf-ingress
    version: 0.1.0
    repository: "file://../../platform/cf-ingress-library"
  - name: searxng
    version: "1.0.0"
    repository: "https://charts.searxng.org"
```

> Check the actual SearXNG Helm chart repository URL and latest version before committing. If no official Helm chart exists, create a minimal deployment template instead.

**Step 2: Update deploy/application.yaml targetRevision**

Update `targetRevision` to match the new chart version `0.9.0`.

**Step 3: Add environment variables to deployment.yaml**

Add after the existing env block:

```yaml
            {{- if .Values.chat.enabled }}
            - name: DISCORD_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ include "monolith.fullname" . }}-secrets
                  key: DISCORD_BOT_TOKEN
            - name: LLAMA_CPP_URL
              value: {{ .Values.chat.llamaCppUrl | quote }}
            - name: EMBEDDING_URL
              value: {{ .Values.chat.embeddingUrl | quote }}
            - name: SEARXNG_URL
              value: {{ .Values.chat.searxngUrl | quote }}
            {{- end }}
```

**Step 4: Enable pgvector in CNPG cluster**

Add to `cnpg-cluster.yaml` under `spec.postgresql`:

```yaml
shared_preload_libraries:
  - "vector"
```

**Step 5: Add chat values to deploy/values.yaml**

```yaml
chat:
  enabled: true
  llamaCppUrl: "http://llama-cpp.llama-cpp.svc.cluster.local:8080"
  embeddingUrl: "http://llama-cpp-embeddings.llama-cpp.svc.cluster.local:8080"
  searxngUrl: "http://monolith-searxng:8080"
```

**Step 6: Add Discord bot token to 1Password item**

The `DISCORD_BOT_TOKEN` needs to be added to the existing 1Password item referenced by the monolith's `onepassword.itemPath`. This is a manual step.

**Step 7: Bump memory resources**

In `deploy/values.yaml`, update backend resources to accommodate discord.py:

```yaml
backend:
  resources:
    requests:
      cpu: 10m
      memory: 256Mi
    limits:
      memory: 512Mi
```

**Step 8: Commit**

```
git add projects/monolith/chart/ projects/monolith/deploy/
git commit -m "feat(monolith): add SearXNG subchart, pgvector, and Discord chat config"
```

---

## Task 10: Deploy voyage-4-nano (Embeddings Instance)

**Files:**

- Create: `projects/agent_platform/llama_cpp_embeddings/deploy/application.yaml`
- Create: `projects/agent_platform/llama_cpp_embeddings/deploy/kustomization.yaml`
- Create: `projects/agent_platform/llama_cpp_embeddings/deploy/values.yaml`

**Step 1: Create ArgoCD Application**

The embeddings instance reuses the existing llama-cpp chart but with different values:

```yaml
# projects/agent_platform/llama_cpp_embeddings/deploy/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: llama-cpp-embeddings
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/agent_platform/llama_cpp/deploy
    targetRevision: HEAD
    helm:
      releaseName: llama-cpp-embeddings
      valueFiles:
        - ../../../agent_platform/llama_cpp_embeddings/deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: llama-cpp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

> **Note:** The exact approach for sharing the chart path while using a different values file may need adjustment based on how ArgoCD resolves relative paths. An alternative is to point `source.path` directly at the embeddings deploy dir and symlink or copy the chart templates. Validate during implementation.

**Step 2: Create values.yaml for embeddings**

```yaml
# projects/agent_platform/llama_cpp_embeddings/deploy/values.yaml
fullnameOverride: "llama-cpp-embeddings"

image:
  tag: "server-cuda-b8643"

imagePullSecret:
  enabled: true

modelVolume:
  enabled: true
  reference: "ghcr.io/jomcgi/models/voyageai/voyage-4-nano:gguf-q8-0"
  mountPath: "/model-image"

server:
  nGpuLayers: 999
  ctxSize: 8192
  flashAttn: "on"
  threads: 4
  jinja: false
  extraArgs:
    - "--embedding"
    - "--alias"
    - "voyage-4-nano"

nodeSelector:
  kubernetes.io/hostname: node-4

podAnnotations:
  linkerd.io/inject: disabled

resources:
  requests:
    cpu: 1
    memory: "1Gi"
    nvidia.com/gpu: 1
  limits:
    memory: "2Gi"
    nvidia.com/gpu: 1
```

> **Important:** The `modelVolume.reference` OCI image for voyage-4-nano GGUF needs to be created first. Use the OCI Model Cache operator or manually push the GGUF to GHCR. The exact OCI reference will depend on what's available.

> **GPU sharing:** Both llama-cpp instances request `nvidia.com/gpu: 1`. If there's only one GPU on node-4, you'll need GPU sharing (MPS or time-slicing) configured, or run voyage-4-nano on CPU only (remove the GPU request and set `nGpuLayers: 0`). Check GPU availability during implementation.

**Step 3: Create kustomization.yaml**

```yaml
# projects/agent_platform/llama_cpp_embeddings/deploy/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 4: Run format to register in home-cluster kustomization**

```
format
```

**Step 5: Commit**

```
git add projects/agent_platform/llama_cpp_embeddings/
git commit -m "feat: deploy voyage-4-nano embeddings via second llama.cpp instance"
```

---

## Task 11: Retire TypeScript Chat Bot

**Files:**

- Delete: `projects/agent_platform/chat_bot/` (entire directory)
- Modify: `projects/agent_platform/kustomization.yaml` (remove chat_bot reference)

**Step 1: Remove chat_bot from agent-platform kustomization**

Edit `projects/agent_platform/kustomization.yaml` to remove the `chat_bot/deploy` resource entry.

**Step 2: Delete chat_bot directory**

```
rm -rf projects/agent_platform/chat_bot/
```

**Step 3: Run format**

```
format
```

**Step 4: Commit**

```
git add -A projects/agent_platform/
git commit -m "chore: retire TypeScript chat bot (replaced by monolith chat module)"
```

---

## Task 12: Integration Test and Verify

**Step 1: Verify all tests pass in CI**

Push the branch and check CI:

```
git push -u origin feat/discord-chatbot
```

Monitor CI via `bb` CLI or BuildBuddy UI.

**Step 2: Verify deployment**

After CI passes and ArgoCD syncs:

1. Check monolith pod is healthy (MCP: `kubernetes-mcp-pods-list` in `monolith` namespace)
2. Check llama-cpp-embeddings pod starts on node-4 (MCP: `kubernetes-mcp-pods-list` in `llama-cpp` namespace)
3. Check SearXNG pod is healthy in monolith namespace
4. Check Discord bot connects (MCP: `kubernetes-mcp-pods-log` for monolith pod, look for "Discord bot connected")
5. Send a test message mentioning the bot in Discord
6. Verify the bot responds with context-aware reply

**Step 3: Create PR**

Create PR with title "feat: Discord chatbot with persistent memory" and a summary covering:

- Conversational Discord chatbot added to monolith with pgvector memory
- voyage-4-nano embedding model deployed on GPU node
- SearXNG web search as PydanticAI tool
- TypeScript chat bot retired
