# Chat History Tools + Rolling User Summaries — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give the chat agent on-demand tools to search message history and retrieve per-user rolling summaries, replacing the blind pre-fetch.

**Architecture:** Two new PydanticAI tools (`search_history`, `get_user_summary`) injected via a `ChatDeps` dependency dataclass. A background summarizer job runs daily, incrementally updating per-user-per-channel summaries via Gemma 4. New `UserChannelSummary` SQLModel + Atlas migration.

**Tech Stack:** PydanticAI (deps + tools), SQLModel, pgvector, llama.cpp (Gemma 4), FastAPI lifespan, asyncio

---

### Task 1: Add `UserChannelSummary` model

**Files:**

- Modify: `projects/monolith/chat/models.py`
- Test: `projects/monolith/chat/models_summary_test.py` (create)

**Step 1: Write the failing test**

Create `projects/monolith/chat/models_summary_test.py`:

```python
"""Tests for UserChannelSummary model."""

from datetime import datetime, timezone

from chat.models import UserChannelSummary


class TestUserChannelSummary:
    def test_creates_summary_instance(self):
        """UserChannelSummary can be instantiated with required fields."""
        summary = UserChannelSummary(
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            summary="Alice discussed deployment issues.",
            last_message_id=42,
        )
        assert summary.channel_id == "ch1"
        assert summary.username == "Alice"
        assert summary.summary == "Alice discussed deployment issues."
        assert summary.last_message_id == 42

    def test_default_updated_at_is_utc(self):
        """updated_at defaults to a UTC timestamp."""
        summary = UserChannelSummary(
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            summary="test",
            last_message_id=1,
        )
        assert summary.updated_at is not None
        assert summary.updated_at.tzinfo is not None
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_models_summary_test`
Expected: FAIL — `ImportError: cannot import name 'UserChannelSummary'`

**Step 3: Write minimal implementation**

Add to `projects/monolith/chat/models.py`:

```python
from sqlalchemy import UniqueConstraint

class UserChannelSummary(SQLModel, table=True):
    __tablename__ = "user_channel_summaries"
    __table_args__ = (
        UniqueConstraint("channel_id", "user_id"),
        {"schema": "chat"},
    )

    id: int | None = Field(default=None, primary_key=True)
    channel_id: str
    user_id: str
    username: str
    summary: str
    last_message_id: int
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**Step 4: Add BUILD target**

Add to `projects/monolith/BUILD`:

```starlark
py_test(
    name = "chat_models_summary_test",
    srcs = ["chat/models_summary_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)
```

**Step 5: Run test to verify it passes**

Run: `bazel test //projects/monolith:chat_models_summary_test`
Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/chat/models.py projects/monolith/chat/models_summary_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add UserChannelSummary model for rolling user summaries"
```

---

### Task 2: Add Atlas migration for `user_channel_summaries` table

**Files:**

- Create: `projects/monolith/chart/migrations/20260404000000_user_channel_summaries.sql`

**Step 1: Write the migration**

Create `projects/monolith/chart/migrations/20260404000000_user_channel_summaries.sql`:

```sql
-- Rolling per-user-per-channel summaries for chat agent context.

CREATE TABLE chat.user_channel_summaries (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    summary TEXT NOT NULL,
    last_message_id INT NOT NULL REFERENCES chat.messages(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, user_id)
);

CREATE INDEX chat_summaries_channel ON chat.user_channel_summaries (channel_id);
```

**Step 2: Update atlas.sum**

Run: `format` (to regenerate atlas.sum and any other formatting)

**Step 3: Commit**

```
git add projects/monolith/chart/migrations/
git commit -m "feat(monolith): add migration for user_channel_summaries table"
```

---

### Task 3: Add `ChatDeps` dataclass and refactor `create_agent` to accept deps

**Files:**

- Modify: `projects/monolith/chat/agent.py`
- Test: `projects/monolith/chat/agent_deps_test.py` (create)

**Step 1: Write the failing test**

Create `projects/monolith/chat/agent_deps_test.py`:

```python
"""Tests for ChatDeps and agent dependency injection."""

from unittest.mock import AsyncMock, MagicMock

from chat.agent import ChatDeps, create_agent


class TestChatDeps:
    def test_creates_deps_instance(self):
        """ChatDeps holds channel_id, store, and embed_client."""
        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        assert deps.channel_id == "ch1"


class TestCreateAgentWithDeps:
    def test_agent_has_search_history_tool(self):
        """create_agent registers a search_history tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = [t.name for t in agent._function_tools.values()]
        assert "search_history" in tool_names

    def test_agent_has_get_user_summary_tool(self):
        """create_agent registers a get_user_summary tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = [t.name for t in agent._function_tools.values()]
        assert "get_user_summary" in tool_names

    def test_system_prompt_references_search_history(self):
        """System prompt tells the agent about search_history."""
        from chat.agent import build_system_prompt
        prompt = build_system_prompt()
        assert "search_history" in prompt

    def test_system_prompt_references_get_user_summary(self):
        """System prompt tells the agent about get_user_summary."""
        from chat.agent import build_system_prompt
        prompt = build_system_prompt()
        assert "get_user_summary" in prompt
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_agent_deps_test`
Expected: FAIL — `ImportError: cannot import name 'ChatDeps'`

**Step 3: Write implementation**

Modify `projects/monolith/chat/agent.py`:

1. Add `ChatDeps` dataclass:

```python
from dataclasses import dataclass
from pydantic_ai import RunContext
from chat.embedding import EmbeddingClient
from chat.store import MessageStore

@dataclass
class ChatDeps:
    channel_id: str
    store: MessageStore
    embed_client: EmbeddingClient
```

2. Update `build_system_prompt()` to mention the new tools:

```python
def build_system_prompt() -> str:
    return (
        "You are a helpful assistant in a Discord chat. "
        "You have access to these tools:\n"
        "- web_search: Look up current information from the web.\n"
        "- search_history: Search older messages in this channel by topic, "
        "optionally filtered by username. Use when the recent conversation "
        "doesn't have enough context.\n"
        "- get_user_summary: Get a summary of what a specific user has been "
        "discussing in this channel. Use when asked about a user's activity.\n\n"
        "Keep responses concise and conversational. "
        "You can see recent conversation history for context. "
        "Use your tools before saying you don't have context."
    )
```

3. Change `Agent` type to `Agent[ChatDeps]` and register tools:

```python
def create_agent(base_url: str | None = None) -> Agent[ChatDeps]:
    url = base_url or LLAMA_CPP_URL
    model = OpenAIChatModel(
        "gemma-4-26b-a4b",
        provider=OpenAIProvider(base_url=f"{url}/v1", api_key="not-needed"),
    )
    agent: Agent[ChatDeps] = Agent(model, system_prompt=build_system_prompt())

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the web for current information."""
        return await search_web(query)

    @agent.tool
    async def search_history(
        ctx: RunContext[ChatDeps],
        query: str,
        username: str | None = None,
        limit: int = 5,
    ) -> str:
        """Search older messages in this channel by topic. Optionally filter by username."""
        deps = ctx.deps
        query_embedding = await deps.embed_client.embed(query)
        user_id = None
        if username:
            user_id = deps.store.find_user_id_by_username(deps.channel_id, username)
        results = deps.store.search_similar(
            channel_id=deps.channel_id,
            query_embedding=query_embedding,
            limit=limit,
            user_id=user_id,
        )
        if not results:
            return "No matching messages found."
        return format_context_messages(results)

    @agent.tool
    async def get_user_summary(
        ctx: RunContext[ChatDeps],
        username: str,
    ) -> str:
        """Get a summary of what a user has been discussing in this channel."""
        deps = ctx.deps
        summary = deps.store.get_user_summary(deps.channel_id, username)
        if not summary:
            return f"No summary available for {username}."
        return (
            f"Summary for {username} "
            f"(updated {summary.updated_at.strftime('%Y-%m-%d')}):\n"
            f"{summary.summary}"
        )

    return agent
```

**Step 4: Add BUILD target**

```starlark
py_test(
    name = "chat_agent_deps_test",
    srcs = ["chat/agent_deps_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pgvector",
        "@pip//pydantic_ai_slim",
        "@pip//pytest",
        "@pip//sqlmodel",
    ],
)
```

**Step 5: Run tests to verify they pass**

Run: `bazel test //projects/monolith:chat_agent_deps_test`
Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/chat/agent.py projects/monolith/chat/agent_deps_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add ChatDeps and register search_history/get_user_summary tools"
```

---

### Task 4: Add `find_user_id_by_username` and `get_user_summary` to `MessageStore`

**Files:**

- Modify: `projects/monolith/chat/store.py`
- Test: `projects/monolith/chat/store_summary_test.py` (create)

**Step 1: Write the failing tests**

Create `projects/monolith/chat/store_summary_test.py`:

```python
"""Tests for MessageStore summary and username lookup methods."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import Message, UserChannelSummary
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
    embed_client.embed.return_value = [0.0] * 1024
    return MessageStore(session=session, embed_client=embed_client)


class TestFindUserIdByUsername:
    @pytest.mark.asyncio
    async def test_finds_user_by_username_in_channel(self, store, session):
        """find_user_id_by_username returns the user_id for a known username."""
        await store.save_message("1", "ch1", "u42", "Alice", "hello", False)
        result = store.find_user_id_by_username("ch1", "Alice")
        assert result == "u42"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_username(self, store):
        """find_user_id_by_username returns None when username not found."""
        result = store.find_user_id_by_username("ch1", "Nobody")
        assert result is None

    @pytest.mark.asyncio
    async def test_scoped_to_channel(self, store, session):
        """find_user_id_by_username only looks in the specified channel."""
        await store.save_message("1", "ch1", "u1", "Alice", "hello", False)
        result = store.find_user_id_by_username("ch2", "Alice")
        assert result is None


class TestGetUserSummary:
    def test_returns_summary_when_exists(self, store, session):
        """get_user_summary returns the summary for a known user."""
        summary = UserChannelSummary(
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            summary="Alice talked about deployments.",
            last_message_id=1,
        )
        session.add(summary)
        session.commit()
        result = store.get_user_summary("ch1", "Alice")
        assert result is not None
        assert "deployments" in result.summary

    def test_returns_none_when_not_exists(self, store):
        """get_user_summary returns None for unknown user."""
        result = store.get_user_summary("ch1", "Nobody")
        assert result is None


class TestUpsertSummary:
    def test_inserts_new_summary(self, store, session):
        """upsert_summary creates a new summary when none exists."""
        store.upsert_summary("ch1", "u1", "Alice", "First summary.", 10)
        result = store.get_user_summary("ch1", "Alice")
        assert result is not None
        assert result.summary == "First summary."
        assert result.last_message_id == 10

    def test_updates_existing_summary(self, store, session):
        """upsert_summary updates an existing summary."""
        store.upsert_summary("ch1", "u1", "Alice", "First.", 10)
        store.upsert_summary("ch1", "u1", "Alice", "Updated.", 20)
        result = store.get_user_summary("ch1", "Alice")
        assert result.summary == "Updated."
        assert result.last_message_id == 20
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //projects/monolith:chat_store_summary_test`
Expected: FAIL — `AttributeError: 'MessageStore' object has no attribute 'find_user_id_by_username'`

**Step 3: Write implementation**

Add these methods to the `MessageStore` class in `projects/monolith/chat/store.py`:

```python
from chat.models import Message, UserChannelSummary

def find_user_id_by_username(self, channel_id: str, username: str) -> str | None:
    """Look up a user_id by username within a channel. Returns None if not found."""
    stmt = (
        select(Message.user_id)
        .where(Message.channel_id == channel_id, Message.username == username)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return self.session.exec(stmt).first()

def get_user_summary(
    self, channel_id: str, username: str
) -> UserChannelSummary | None:
    """Return the rolling summary for a user in a channel, or None."""
    stmt = select(UserChannelSummary).where(
        UserChannelSummary.channel_id == channel_id,
        UserChannelSummary.username == username,
    )
    return self.session.exec(stmt).first()

def upsert_summary(
    self,
    channel_id: str,
    user_id: str,
    username: str,
    summary_text: str,
    last_message_id: int,
) -> None:
    """Insert or update a rolling summary for a user in a channel."""
    from datetime import datetime, timezone

    existing = self.session.exec(
        select(UserChannelSummary).where(
            UserChannelSummary.channel_id == channel_id,
            UserChannelSummary.user_id == user_id,
        )
    ).first()
    if existing:
        existing.summary = summary_text
        existing.username = username
        existing.last_message_id = last_message_id
        existing.updated_at = datetime.now(timezone.utc)
        self.session.add(existing)
    else:
        self.session.add(
            UserChannelSummary(
                channel_id=channel_id,
                user_id=user_id,
                username=username,
                summary=summary_text,
                last_message_id=last_message_id,
            )
        )
    self.session.commit()
```

**Step 4: Add BUILD target**

```starlark
py_test(
    name = "chat_store_summary_test",
    srcs = ["chat/store_summary_test.py"],
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

**Step 5: Run tests to verify they pass**

Run: `bazel test //projects/monolith:chat_store_summary_test`
Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/chat/store.py projects/monolith/chat/store_summary_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add find_user_id_by_username, get_user_summary, upsert_summary to MessageStore"
```

---

### Task 5: Refactor `_generate_response` to use `ChatDeps` (remove pre-fetch)

**Files:**

- Modify: `projects/monolith/chat/bot.py`
- Modify: `projects/monolith/chat/bot_coverage_test.py`

**Step 1: Update `_generate_response`**

Replace the `_generate_response` method in `projects/monolith/chat/bot.py`:

```python
async def _generate_response(self, message: discord.Message) -> str:
    """Build context and run the PydanticAI agent."""
    from chat.agent import ChatDeps

    with Session(get_engine()) as session:
        store = MessageStore(session=session, embed_client=self.embed_client)

        # Recent window only — semantic recall is now on-demand via tools
        recent = store.get_recent(str(message.channel.id), limit=20)

        # Build context
        context = "Recent conversation:\n" + format_context_messages(recent)

        # Run agent with deps so tools can access store + embeddings
        deps = ChatDeps(
            channel_id=str(message.channel.id),
            store=store,
            embed_client=self.embed_client,
        )
        user_prompt = (
            f"{context}\n\nCurrent message from "
            f"{message.author.display_name}: {message.content}"
        )
        result = await self.agent.run(user_prompt, deps=deps)
        return result.output
```

**Step 2: Update tests**

In `projects/monolith/chat/bot_coverage_test.py`:

- `TestOnMessageGenerateReply.test_replies_when_mentioned`: Remove `mock_store.search_similar` and `bot.embed_client.embed` mocks since `_generate_response` no longer calls them directly.
- `TestOnMessageGenerateReply.test_swallows_reply_exception`: Same removals.
- `TestGenerateResponse.test_includes_recent_messages_in_prompt`: Remove `mock_store.search_similar` and `bot.embed_client.embed` mocks. Verify `agent.run` is called with `deps=` kwarg.
- `TestGenerateResponse.test_includes_similar_messages_when_present`: This test no longer applies — delete it or replace with a test verifying `deps` is passed.

**Step 3: Run all chat bot tests**

Run: `bazel test //projects/monolith:chat_bot_test //projects/monolith:chat_bot_coverage_test //projects/monolith:chat_bot_extra_test`
Expected: PASS

**Step 4: Commit**

```
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_coverage_test.py
git commit -m "refactor(monolith): replace pre-fetch with ChatDeps tool injection in _generate_response"
```

---

### Task 6: Create the rolling summarizer

**Files:**

- Create: `projects/monolith/chat/summarizer.py`
- Test: `projects/monolith/chat/summarizer_test.py` (create)

**Step 1: Write the failing tests**

Create `projects/monolith/chat/summarizer_test.py`:

```python
"""Tests for rolling summary generation."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Message, UserChannelSummary
from chat.summarizer import generate_summaries


@pytest.fixture(name="session")
def session_fixture():
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


def _make_message(session, channel_id, user_id, username, content, msg_id):
    msg = Message(
        id=msg_id,
        discord_message_id=str(msg_id),
        channel_id=channel_id,
        user_id=user_id,
        username=username,
        content=content,
        is_bot=False,
        embedding=[0.0] * 1024,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


class TestGenerateSummaries:
    @pytest.mark.asyncio
    async def test_creates_summary_for_new_user(self, session):
        """First run creates a new summary from scratch."""
        _make_message(session, "ch1", "u1", "Alice", "I deployed the app", 1)
        _make_message(session, "ch1", "u1", "Alice", "It went smoothly", 2)

        mock_llm = AsyncMock(return_value="Alice deployed the app successfully.")

        await generate_summaries(session, mock_llm)

        summary = session.exec(
            select(UserChannelSummary).where(
                UserChannelSummary.channel_id == "ch1",
                UserChannelSummary.user_id == "u1",
            )
        ).first()
        assert summary is not None
        assert summary.summary == "Alice deployed the app successfully."
        assert summary.last_message_id == 2

    @pytest.mark.asyncio
    async def test_updates_existing_summary(self, session):
        """Subsequent runs update the existing summary with new messages."""
        _make_message(session, "ch1", "u1", "Alice", "Old message", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                summary="Alice said old things.",
                last_message_id=1,
            )
        )
        session.commit()

        _make_message(session, "ch1", "u1", "Alice", "New message", 2)

        mock_llm = AsyncMock(return_value="Alice said old and new things.")

        await generate_summaries(session, mock_llm)

        summary = session.exec(
            select(UserChannelSummary).where(
                UserChannelSummary.user_id == "u1",
            )
        ).first()
        assert summary.summary == "Alice said old and new things."
        assert summary.last_message_id == 2

    @pytest.mark.asyncio
    async def test_skips_when_no_new_messages(self, session):
        """No LLM call when there are no new messages since last summary."""
        _make_message(session, "ch1", "u1", "Alice", "Old", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                summary="Existing.",
                last_message_id=1,
            )
        )
        session.commit()

        mock_llm = AsyncMock()

        await generate_summaries(session, mock_llm)

        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_bot_messages(self, session):
        """Bot messages are not included in summaries."""
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="bot",
            username="Bot",
            content="I am a bot",
            is_bot=True,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()

        mock_llm = AsyncMock()

        await generate_summaries(session, mock_llm)

        mock_llm.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `bazel test //projects/monolith:chat_summarizer_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'chat.summarizer'`

**Step 3: Write implementation**

Create `projects/monolith/chat/summarizer.py`:

```python
"""Rolling summary generator -- incrementally updates per-user-per-channel summaries."""

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from chat.models import Message, UserChannelSummary

logger = logging.getLogger(__name__)


async def generate_summaries(
    session: Session,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Update rolling summaries for all (channel, user) pairs with new messages."""
    pairs = session.exec(
        select(Message.channel_id, Message.user_id, Message.username)
        .where(Message.is_bot == False)  # noqa: E712
        .group_by(Message.channel_id, Message.user_id, Message.username)
    ).all()

    for channel_id, user_id, username in pairs:
        existing = session.exec(
            select(UserChannelSummary).where(
                UserChannelSummary.channel_id == channel_id,
                UserChannelSummary.user_id == user_id,
            )
        ).first()

        high_water = existing.last_message_id if existing else 0

        new_messages = list(
            session.exec(
                select(Message)
                .where(
                    Message.channel_id == channel_id,
                    Message.user_id == user_id,
                    Message.is_bot == False,  # noqa: E712
                    Message.id > high_water,
                )
                .order_by(Message.created_at.asc())
            ).all()
        )

        if not new_messages:
            continue

        new_max_id = max(m.id for m in new_messages)
        messages_text = "\n".join(
            f"[{m.created_at.strftime('%Y-%m-%d %H:%M')}] {m.content}"
            for m in new_messages
        )

        if existing:
            prompt = (
                f"Current summary of {username}'s messages:\n{existing.summary}\n\n"
                f"New messages from {username}:\n{messages_text}\n\n"
                "Update the summary to incorporate the new messages. "
                "Keep it to 2-4 concise sentences."
            )
        else:
            prompt = (
                f"Messages from {username}:\n{messages_text}\n\n"
                "Write a 2-4 sentence summary of what this user has been discussing."
            )

        summary_text = await llm_call(prompt)

        if existing:
            existing.summary = summary_text
            existing.username = username
            existing.last_message_id = new_max_id
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
        else:
            session.add(
                UserChannelSummary(
                    channel_id=channel_id,
                    user_id=user_id,
                    username=username,
                    summary=summary_text,
                    last_message_id=new_max_id,
                )
            )
        session.commit()

    logger.info("Summary generation complete for %d user-channel pairs", len(pairs))


def build_llm_caller(base_url: str | None = None) -> Callable[[str], Awaitable[str]]:
    """Create an async callable that sends a prompt to Gemma via llama.cpp."""
    url = base_url or os.environ.get("LLAMA_CPP_URL", "")

    async def call_llm(prompt: str) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{url}/v1/chat/completions",
                json={
                    "model": "gemma-4-26b-a4b",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    return call_llm
```

**Step 4: Add BUILD target**

```starlark
py_test(
    name = "chat_summarizer_test",
    srcs = ["chat/summarizer_test.py"],
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

**Step 5: Run tests to verify they pass**

Run: `bazel test //projects/monolith:chat_summarizer_test`
Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/chat/summarizer.py projects/monolith/chat/summarizer_test.py projects/monolith/BUILD
git commit -m "feat(monolith): add rolling summary generator for per-user-per-channel context"
```

---

### Task 7: Wire summarizer into FastAPI lifespan

**Files:**

- Modify: `projects/monolith/app/main.py`

**Step 1: Add summary loop to lifespan**

In `projects/monolith/app/main.py`, add after the bot setup block (after `logger.info("Discord bot starting")`):

```python
    # Start summary loop if chat is enabled
    summary_task = None
    if discord_token:
        from sqlmodel import Session as SqlSession

        async def _summary_loop():
            from chat.summarizer import build_llm_caller, generate_summaries

            while True:
                await asyncio.sleep(86400)  # 24 hours
                try:
                    with SqlSession(get_engine()) as session:
                        llm_caller = build_llm_caller()
                        await generate_summaries(session, llm_caller)
                except Exception:
                    logger.exception("Summary generation failed")

        summary_task = asyncio.create_task(_summary_loop())
        summary_task.add_done_callback(_log_task_exception)
        logger.info("Summary loop started (24h interval)")
```

Add to cleanup section:

```python
    if summary_task:
        summary_task.cancel()
```

**Step 2: Run existing main tests**

Run: `bazel test //projects/monolith:main_test //projects/monolith:main_coverage_test`
Expected: PASS (existing tests should still pass since summary_task only starts when DISCORD_BOT_TOKEN is set)

**Step 3: Commit**

```
git add projects/monolith/app/main.py
git commit -m "feat(monolith): wire rolling summary loop into FastAPI lifespan"
```

---

### Task 8: Run all tests, format, and bump chart version

**Step 1: Run formatter**

Run: `format`

This regenerates BUILD files (via gazelle) and formats all code.

**Step 2: Run all monolith tests**

Run: `bazel test //projects/monolith:all`
Expected: All PASS

**Step 3: Fix any failing tests**

Update test expectations as needed — particularly tests in `bot_coverage_test.py` and `agent_coverage_test.py` that reference the old pre-fetch flow or old system prompt text.

Key tests to check:

- `chat_agent_coverage_test` — `test_system_prompt_references_web_search` still passes (prompt still mentions web search)
- `chat_bot_coverage_test` — `TestGenerateResponse` tests no longer expect `search_similar` or `embed_client.embed` calls
- `chat_bot_extra_test` — may reference old `_generate_response` flow

**Step 4: Bump chart version**

Increment version in `projects/monolith/chart/Chart.yaml` and update `targetRevision` in `projects/monolith/deploy/application.yaml` to match.

**Step 5: Commit**

```
git add -A
git commit -m "chore(monolith): bump chart version and fix tests for history tools"
```

---

### Task 9: Push and create PR

**Step 1: Push branch**

```
git push -u origin feat/chat-history-tools
```

**Step 2: Create PR**

Title: `feat(monolith): add on-demand history search and rolling user summaries`

Body:

```
## Summary

- Add `search_history` agent tool for semantic search over channel messages (optionally filtered by username)
- Add `get_user_summary` agent tool to retrieve rolling per-user summaries
- Add daily background job that incrementally updates summaries via Gemma 4
- Remove blind 5-message pre-fetch from `_generate_response` — agent now pulls context on-demand
- New `chat.user_channel_summaries` table + migration

## Test plan

- [ ] Verify `UserChannelSummary` model creates/reads correctly
- [ ] Verify `search_history` tool embeds query and returns formatted results
- [ ] Verify `get_user_summary` tool returns summary or "not available"
- [ ] Verify summarizer creates new summaries and incrementally updates existing ones
- [ ] Verify summarizer skips bot messages and no-new-messages cases
- [ ] Verify `_generate_response` passes `ChatDeps` to agent
- [ ] CI passes all tests
```
