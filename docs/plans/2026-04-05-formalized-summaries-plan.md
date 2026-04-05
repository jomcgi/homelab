# Formalized Summaries Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-inject channel and user summaries into the Discord bot's agent context so every response is informed by who it's talking to and what the channel is about.

**Architecture:** Extend the existing summary system with a new `channel_summaries` table, add channel-level summary generation to the summarizer, improve prompts with rolling-window awareness, and inject both channel + user summaries into the prompt built by `_generate_response()`. No new dependencies, tools, or agent changes.

**Tech Stack:** Python, SQLModel, PostgreSQL (pgvector), PydanticAI, Atlas migrations, Bazel (remote via `bb remote test`)

**Working directory:** `/tmp/claude-worktrees/formalized-summaries`

**Test command:** `bb remote test //projects/monolith:<target> --config=ci`

**Important patterns:**

- Tests use in-memory SQLite with schema stripping (see `session_fixture` in existing tests)
- New test files need a `py_test` target in `projects/monolith/BUILD`
- After adding new Python files, run `format` to regenerate BUILD targets (or add manually)
- Chart version bump: update BOTH `chart/Chart.yaml` version AND `deploy/application.yaml` `targetRevision`

---

### Task 1: Add `ChannelSummary` model

**Files:**

- Modify: `projects/monolith/chat/models.py:69` (append after `UserChannelSummary`)

**Step 1: Add the model**

Append to `chat/models.py` after the `UserChannelSummary` class:

```python
class ChannelSummary(SQLModel, table=True):
    __tablename__ = "channel_summaries"
    __table_args__ = {"schema": "chat"}

    id: int | None = Field(default=None, primary_key=True)
    channel_id: str = Field(unique=True)
    summary: str
    message_count: int = Field(default=0)
    last_message_id: int = Field(foreign_key="chat.messages.id")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**Step 2: Commit**

```
git add projects/monolith/chat/models.py
git commit -m "feat(chat): add ChannelSummary model"
```

---

### Task 2: Add Atlas migration for `channel_summaries`

**Files:**

- Create: `projects/monolith/chart/migrations/20260405100000_channel_summaries.sql`
- Modify: `projects/monolith/chart/migrations/atlas.sum` (will be auto-updated)

**Step 1: Write the migration**

```sql
-- Channel-level rolling summaries for ambient bot context.

CREATE TABLE chat.channel_summaries (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    message_count INT NOT NULL DEFAULT 0,
    last_message_id INT NOT NULL REFERENCES chat.messages(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Step 2: Update atlas.sum**

The atlas.sum file tracks migration checksums. Run:

```
atlas migrate hash --dir "file://projects/monolith/chart/migrations"
```

If `atlas` is not available locally, manually append the new migration to `atlas.sum`. CI will validate checksums. Check the format of the existing `atlas.sum` and match it.

**Step 3: Commit**

```
git add projects/monolith/chart/migrations/
git commit -m "feat(chat): add channel_summaries migration"
```

---

### Task 3: Add store methods for channel summaries

**Files:**

- Modify: `projects/monolith/chat/store.py:9` (add `ChannelSummary` import)
- Modify: `projects/monolith/chat/store.py:227` (append new methods)
- Create: `projects/monolith/chat/store_channel_summary_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write failing tests**

Create `projects/monolith/chat/store_channel_summary_test.py`:

```python
"""Tests for MessageStore channel summary methods."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import ChannelSummary, Message, UserChannelSummary
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


class TestGetChannelSummary:
    def test_returns_none_when_not_exists(self, store):
        """get_channel_summary returns None for unknown channel."""
        result = store.get_channel_summary("ch_unknown")
        assert result is None

    def test_returns_summary_when_exists(self, store, session):
        """get_channel_summary returns the summary for a known channel."""
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        session.add(
            ChannelSummary(
                channel_id="ch1",
                summary="This channel discusses deployments.",
                message_count=10,
                last_message_id=1,
            )
        )
        session.commit()
        result = store.get_channel_summary("ch1")
        assert result is not None
        assert "deployments" in result.summary
        assert result.message_count == 10


class TestUpsertChannelSummary:
    def test_inserts_new_summary(self, store, session):
        """upsert_channel_summary creates a new summary."""
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        store.upsert_channel_summary("ch1", "Channel about infra.", 1, 5)
        result = store.get_channel_summary("ch1")
        assert result is not None
        assert result.summary == "Channel about infra."
        assert result.message_count == 5

    def test_updates_existing_summary(self, store, session):
        """upsert_channel_summary updates an existing summary."""
        msg = Message(
            id=1,
            discord_message_id="1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="hello",
            is_bot=False,
            embedding=[0.0] * 1024,
        )
        session.add(msg)
        session.commit()
        store.upsert_channel_summary("ch1", "First.", 1, 5)
        store.upsert_channel_summary("ch1", "Updated.", 1, 10)
        result = store.get_channel_summary("ch1")
        assert result.summary == "Updated."
        assert result.message_count == 10


class TestGetUserSummariesForUsers:
    def test_returns_matching_summaries(self, store, session):
        """get_user_summaries_for_users returns summaries for given user IDs."""
        store.upsert_summary("ch1", "u1", "Alice", "Alice summary.", 10)
        store.upsert_summary("ch1", "u2", "Bob", "Bob summary.", 20)
        result = store.get_user_summaries_for_users("ch1", ["u1", "u2"])
        assert len(result) == 2
        usernames = {s.username for s in result}
        assert usernames == {"Alice", "Bob"}

    def test_ignores_missing_users(self, store, session):
        """get_user_summaries_for_users skips users without summaries."""
        store.upsert_summary("ch1", "u1", "Alice", "Alice summary.", 10)
        result = store.get_user_summaries_for_users("ch1", ["u1", "u_missing"])
        assert len(result) == 1
        assert result[0].username == "Alice"

    def test_returns_empty_for_no_matches(self, store):
        """get_user_summaries_for_users returns [] when no users match."""
        result = store.get_user_summaries_for_users("ch1", ["u_missing"])
        assert result == []

    def test_empty_user_ids_returns_empty(self, store):
        """get_user_summaries_for_users returns [] for empty user list."""
        result = store.get_user_summaries_for_users("ch1", [])
        assert result == []

    def test_scoped_to_channel(self, store, session):
        """get_user_summaries_for_users only returns summaries from the given channel."""
        store.upsert_summary("ch1", "u1", "Alice", "Alice in ch1.", 10)
        store.upsert_summary("ch2", "u1", "Alice", "Alice in ch2.", 20)
        result = store.get_user_summaries_for_users("ch1", ["u1"])
        assert len(result) == 1
        assert "ch1" in result[0].summary
```

**Step 2: Run tests to verify they fail**

```
bb remote test //projects/monolith:chat_store_channel_summary_test --config=ci
```

Expected: FAIL -- `get_channel_summary`, `upsert_channel_summary`, `get_user_summaries_for_users` don't exist yet.

**Step 3: Implement the store methods**

In `projects/monolith/chat/store.py`:

Add `ChannelSummary` to the import on line 9:

```python
from chat.models import Attachment, Blob, ChannelSummary, Message, UserChannelSummary
```

Append after `upsert_summary()` (after line 226):

```python
    def get_channel_summary(self, channel_id: str) -> ChannelSummary | None:
        """Return the rolling summary for a channel, or None."""
        stmt = select(ChannelSummary).where(ChannelSummary.channel_id == channel_id)
        return self.session.exec(stmt).first()

    def upsert_channel_summary(
        self,
        channel_id: str,
        summary_text: str,
        last_message_id: int,
        message_count: int,
    ) -> None:
        """Insert or update a rolling summary for a channel."""
        from datetime import datetime, timezone

        existing = self.session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == channel_id)
        ).first()
        if existing:
            existing.summary = summary_text
            existing.last_message_id = last_message_id
            existing.message_count = message_count
            existing.updated_at = datetime.now(timezone.utc)
            self.session.add(existing)
        else:
            self.session.add(
                ChannelSummary(
                    channel_id=channel_id,
                    summary=summary_text,
                    last_message_id=last_message_id,
                    message_count=message_count,
                )
            )
        self.session.commit()

    def get_user_summaries_for_users(
        self, channel_id: str, user_ids: list[str]
    ) -> list[UserChannelSummary]:
        """Return user summaries for a specific set of users in a channel."""
        if not user_ids:
            return []
        stmt = select(UserChannelSummary).where(
            UserChannelSummary.channel_id == channel_id,
            UserChannelSummary.user_id.in_(user_ids),
        )
        return list(self.session.exec(stmt).all())
```

**Step 4: Add BUILD target**

Add to `projects/monolith/BUILD` (near the other `store_*_test` targets):

```python
py_test(
    name = "chat_store_channel_summary_test",
    srcs = ["chat/store_channel_summary_test.py"],
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

```
bb remote test //projects/monolith:chat_store_channel_summary_test --config=ci
```

Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/chat/store.py projects/monolith/chat/store_channel_summary_test.py projects/monolith/BUILD
git commit -m "feat(chat): add store methods for channel summaries"
```

---

### Task 4: Add channel summary generation to summarizer

**Files:**

- Modify: `projects/monolith/chat/summarizer.py` (add import, new function, update prompts)
- Create: `projects/monolith/chat/summarizer_channel_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write failing tests**

Create `projects/monolith/chat/summarizer_channel_test.py`:

```python
"""Tests for channel-level summary generation."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import ChannelSummary, Message
from chat.summarizer import generate_channel_summaries


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


def _make_message(session, channel_id, user_id, username, content, msg_id, is_bot=False):
    msg = Message(
        id=msg_id,
        discord_message_id=str(msg_id),
        channel_id=channel_id,
        user_id=user_id,
        username=username,
        content=content,
        is_bot=is_bot,
        embedding=[0.0] * 1024,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


class TestGenerateChannelSummaries:
    @pytest.mark.asyncio
    async def test_creates_summary_for_new_channel(self, session):
        """First run creates a channel summary from scratch."""
        _make_message(session, "ch1", "u1", "Alice", "Deployed the app", 1)
        _make_message(session, "ch1", "u2", "Bob", "Looks good", 2)

        mock_llm = AsyncMock(return_value="Channel discusses app deployments.")

        await generate_channel_summaries(session, mock_llm)

        summary = session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == "ch1")
        ).first()
        assert summary is not None
        assert summary.summary == "Channel discusses app deployments."
        assert summary.last_message_id == 2
        assert summary.message_count == 2

    @pytest.mark.asyncio
    async def test_updates_existing_channel_summary(self, session):
        """Subsequent runs update the existing channel summary."""
        _make_message(session, "ch1", "u1", "Alice", "Old message", 1)
        session.add(
            ChannelSummary(
                channel_id="ch1",
                summary="Old channel summary.",
                message_count=1,
                last_message_id=1,
            )
        )
        session.commit()

        _make_message(session, "ch1", "u2", "Bob", "New message", 2)

        mock_llm = AsyncMock(return_value="Updated channel summary.")

        await generate_channel_summaries(session, mock_llm)

        summary = session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == "ch1")
        ).first()
        assert summary.summary == "Updated channel summary."
        assert summary.last_message_id == 2
        assert summary.message_count == 2

    @pytest.mark.asyncio
    async def test_skips_when_no_new_messages(self, session):
        """No LLM call when there are no new messages since last summary."""
        _make_message(session, "ch1", "u1", "Alice", "Old", 1)
        session.add(
            ChannelSummary(
                channel_id="ch1",
                summary="Existing.",
                message_count=1,
                last_message_id=1,
            )
        )
        session.commit()

        mock_llm = AsyncMock()

        await generate_channel_summaries(session, mock_llm)

        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_bot_messages(self, session):
        """Channel summaries include bot messages (unlike user summaries)."""
        _make_message(session, "ch1", "u1", "Alice", "Question", 1)
        _make_message(session, "ch1", "bot", "Bot", "Answer", 2, is_bot=True)

        mock_llm = AsyncMock(return_value="Channel has Q&A.")

        await generate_channel_summaries(session, mock_llm)

        summary = session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == "ch1")
        ).first()
        assert summary is not None
        assert summary.message_count == 2

    @pytest.mark.asyncio
    async def test_prompt_mentions_rolling_window(self, session):
        """The LLM prompt mentions the bot's 20-message recent window."""
        _make_message(session, "ch1", "u1", "Alice", "hello", 1)

        captured_prompt = None

        async def capture_llm(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "Summary."

        await generate_channel_summaries(session, capture_llm)

        assert captured_prompt is not None
        assert "most recent 20 messages" in captured_prompt

    @pytest.mark.asyncio
    async def test_handles_multiple_channels(self, session):
        """Generates separate summaries for each channel."""
        _make_message(session, "ch1", "u1", "Alice", "Infra talk", 1)
        _make_message(session, "ch2", "u2", "Bob", "Gaming talk", 2)

        call_count = 0

        async def counting_llm(prompt):
            nonlocal call_count
            call_count += 1
            return f"Summary {call_count}."

        await generate_channel_summaries(session, counting_llm)

        assert call_count == 2
        s1 = session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == "ch1")
        ).first()
        s2 = session.exec(
            select(ChannelSummary).where(ChannelSummary.channel_id == "ch2")
        ).first()
        assert s1 is not None
        assert s2 is not None

    @pytest.mark.asyncio
    async def test_continues_on_error(self, session):
        """A failure for one channel doesn't stop others."""
        _make_message(session, "ch1", "u1", "Alice", "hello", 1)
        _make_message(session, "ch2", "u2", "Bob", "world", 2)

        call_count = 0

        async def failing_then_ok(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM failed")
            return "OK summary."

        await generate_channel_summaries(session, failing_then_ok)

        # One channel should have a summary despite the other failing
        all_summaries = list(session.exec(select(ChannelSummary)).all())
        assert len(all_summaries) == 1
```

**Step 2: Run tests to verify they fail**

```
bb remote test //projects/monolith:chat_summarizer_channel_test --config=ci
```

Expected: FAIL -- `generate_channel_summaries` doesn't exist yet.

**Step 3: Implement `generate_channel_summaries()`**

In `projects/monolith/chat/summarizer.py`:

Update the import on line 11 to include `ChannelSummary`:

```python
from chat.models import ChannelSummary, Message, UserChannelSummary
```

Update the existing user summary prompts (lines 60-71) to include rolling-window awareness:

```python
            if existing:
                prompt = (
                    f"Current summary of {username}'s messages:\n{existing.summary}\n\n"
                    f"New messages from {username}:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on patterns, topics, and context from OLDER messages "
                    "that would help the bot understand this person better. "
                    "Keep it to 2-4 concise sentences."
                )
            else:
                prompt = (
                    f"Messages from {username}:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on patterns, topics, and context from OLDER messages "
                    "that would help the bot understand this person better. "
                    "Write a 2-4 sentence summary of this user's key topics, interests, "
                    "and communication style."
                )
```

Add `generate_channel_summaries()` after `generate_summaries()` (after line 98):

```python
async def generate_channel_summaries(
    session: Session,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Update rolling summaries for all channels with new messages."""
    channels = session.exec(
        select(Message.channel_id).group_by(Message.channel_id)
    ).all()

    for (channel_id,) in [(c,) if isinstance(c, str) else c for c in channels]:
        try:
            existing = session.exec(
                select(ChannelSummary).where(
                    ChannelSummary.channel_id == channel_id,
                )
            ).first()

            high_water = existing.last_message_id if existing else 0

            new_messages = list(
                session.exec(
                    select(Message)
                    .where(
                        Message.channel_id == channel_id,
                        Message.id > high_water,
                    )
                    .order_by(Message.created_at.asc())
                ).all()
            )

            if not new_messages:
                continue

            new_max_id = max(m.id for m in new_messages)
            total_count = (existing.message_count if existing else 0) + len(new_messages)
            messages_text = "\n".join(
                f"[{m.created_at.strftime('%Y-%m-%d %H:%M')}] {m.username}: {m.content}"
                for m in new_messages
            )

            if existing:
                prompt = (
                    f"Current channel summary:\n{existing.summary}\n\n"
                    f"New messages:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on the channel's overall topics, culture, and "
                    "recurring themes from OLDER messages. "
                    "Keep it to 2-4 concise sentences."
                )
            else:
                prompt = (
                    f"Messages from a Discord channel:\n{messages_text}\n\n"
                    "The bot already sees the most recent 20 messages as direct context. "
                    "Focus your summary on the channel's overall topics, culture, and "
                    "recurring themes from OLDER messages. "
                    "Write a 2-4 sentence summary of what this channel is about."
                )

            summary_text = await llm_call(prompt)

            if existing:
                existing.summary = summary_text
                existing.last_message_id = new_max_id
                existing.message_count = total_count
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
            else:
                session.add(
                    ChannelSummary(
                        channel_id=channel_id,
                        summary=summary_text,
                        last_message_id=new_max_id,
                        message_count=total_count,
                    )
                )
            session.commit()
        except Exception:
            logger.exception(
                "Failed to generate channel summary for %s", channel_id
            )
            continue

    logger.info("Channel summary generation complete for %d channels", len(channels))
```

**Step 4: Add BUILD target**

Add to `projects/monolith/BUILD`:

```python
py_test(
    name = "chat_summarizer_channel_test",
    srcs = ["chat/summarizer_channel_test.py"],
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

```
bb remote test //projects/monolith:chat_summarizer_channel_test --config=ci
```

Expected: PASS

**Step 6: Also verify existing summarizer tests still pass**

```
bb remote test //projects/monolith:chat_summarizer_test //projects/monolith:chat_summarizer_prompts_test //projects/monolith:chat_summarizer_coverage_test //projects/monolith:chat_summarizer_none_id_test --config=ci
```

Expected: PASS (existing tests should not break)

**Step 7: Commit**

```
git add projects/monolith/chat/summarizer.py projects/monolith/chat/summarizer_channel_test.py projects/monolith/BUILD
git commit -m "feat(chat): add channel summary generation with rolling-window prompts"
```

---

### Task 5: Inject summaries into agent context

**Files:**

- Modify: `projects/monolith/chat/bot.py:259-278` (add summary fetching + context header)
- Create: `projects/monolith/chat/bot_summary_injection_test.py`
- Modify: `projects/monolith/BUILD` (add test target)

**Step 1: Write failing tests**

Create `projects/monolith/chat/bot_summary_injection_test.py`.

This test needs to verify that `_generate_response()` prepends summary context. The existing bot tests mock `discord.Message`, the `Session`, `MessageStore`, and the agent. Follow the pattern from existing `bot_*_test.py` files.

```python
"""Tests for summary context injection in _generate_response()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.models import ChannelSummary, UserChannelSummary


def _make_mock_message(channel_id="ch1", author_name="Alice", content="hello"):
    """Create a mock discord.Message."""
    msg = MagicMock()
    msg.channel.id = channel_id
    msg.author.display_name = author_name
    msg.content = content
    msg.attachments = []
    return msg


def _make_mock_result(output="Bot response"):
    """Create a mock PydanticAI RunResult."""
    result = MagicMock()
    result.output = output
    result.all_messages.return_value = []
    return result


class TestSummaryInjection:
    @pytest.mark.asyncio
    async def test_injects_channel_summary(self):
        """Channel summary appears in the prompt sent to the agent."""
        from chat.bot import ChatBot

        bot = ChatBot.__new__(ChatBot)
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_result = _make_mock_result()
        bot.agent = MagicMock()
        bot.agent.run = AsyncMock(return_value=mock_result)

        channel_summary = ChannelSummary(
            id=1,
            channel_id="ch1",
            summary="This channel discusses Kubernetes deployments.",
            message_count=50,
            last_message_id=100,
        )

        with patch("chat.bot.Session") as mock_session_cls, \
             patch("chat.bot.get_engine"):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.get_recent.return_value = []
            mock_store.get_attachments.return_value = {}
            mock_store.get_channel_summary.return_value = channel_summary
            mock_store.get_user_summaries_for_users.return_value = []

            with patch("chat.bot.MessageStore", return_value=mock_store):
                msg = _make_mock_message()
                response, _ = await bot._generate_response(msg)

            # Verify the agent was called with a prompt containing channel summary
            call_args = bot.agent.run.call_args
            prompt = (
                call_args[0][0]
                if call_args[0]
                else call_args[1].get("user_prompt", "")
            )
            assert "Channel context:" in prompt
            assert "Kubernetes deployments" in prompt

    @pytest.mark.asyncio
    async def test_injects_user_summaries(self):
        """User summaries for people in the recent window appear in the prompt."""
        from chat.bot import ChatBot
        from chat.models import Message

        bot = ChatBot.__new__(ChatBot)
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_result = _make_mock_result()
        bot.agent = MagicMock()
        bot.agent.run = AsyncMock(return_value=mock_result)

        recent_msg = MagicMock(spec=Message)
        recent_msg.id = 1
        recent_msg.user_id = "u1"
        recent_msg.username = "Bob"
        recent_msg.is_bot = False
        recent_msg.content = "hello"
        recent_msg.created_at = MagicMock()
        recent_msg.created_at.strftime.return_value = "2026-04-05 14:30"

        user_summary = UserChannelSummary(
            id=1,
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            summary="Bob focuses on container networking.",
            last_message_id=1,
        )

        with patch("chat.bot.Session") as mock_session_cls, \
             patch("chat.bot.get_engine"):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.get_recent.return_value = [recent_msg]
            mock_store.get_attachments.return_value = {}
            mock_store.get_channel_summary.return_value = None
            mock_store.get_user_summaries_for_users.return_value = [user_summary]

            with patch("chat.bot.MessageStore", return_value=mock_store):
                msg = _make_mock_message()
                response, _ = await bot._generate_response(msg)

            call_args = bot.agent.run.call_args
            prompt = (
                call_args[0][0]
                if call_args[0]
                else call_args[1].get("user_prompt", "")
            )
            assert "People in this conversation:" in prompt
            assert "Bob" in prompt
            assert "container networking" in prompt

    @pytest.mark.asyncio
    async def test_works_without_summaries(self):
        """When no summaries exist, the prompt has no summary header."""
        from chat.bot import ChatBot

        bot = ChatBot.__new__(ChatBot)
        bot.embed_client = AsyncMock()
        bot.vision_client = AsyncMock()

        mock_result = _make_mock_result()
        bot.agent = MagicMock()
        bot.agent.run = AsyncMock(return_value=mock_result)

        with patch("chat.bot.Session") as mock_session_cls, \
             patch("chat.bot.get_engine"):
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_store = MagicMock()
            mock_store.get_recent.return_value = []
            mock_store.get_attachments.return_value = {}
            mock_store.get_channel_summary.return_value = None
            mock_store.get_user_summaries_for_users.return_value = []

            with patch("chat.bot.MessageStore", return_value=mock_store):
                msg = _make_mock_message()
                response, _ = await bot._generate_response(msg)

            call_args = bot.agent.run.call_args
            prompt = (
                call_args[0][0]
                if call_args[0]
                else call_args[1].get("user_prompt", "")
            )
            assert "Channel context:" not in prompt
            assert "People in this conversation:" not in prompt
```

**Step 2: Run tests to verify they fail**

```
bb remote test //projects/monolith:chat_bot_summary_injection_test --config=ci
```

Expected: FAIL -- `get_channel_summary` and `get_user_summaries_for_users` not called by bot yet.

**Step 3: Implement context injection**

In `projects/monolith/chat/bot.py`, modify `_generate_response()`. After line 274 (`attachments_by_msg = store.get_attachments(all_msg_ids)`), add summary fetching and context header construction:

```python
            # Fetch summaries for ambient context
            channel_summary = store.get_channel_summary(str(message.channel.id))
            recent_user_ids = list(
                {m.user_id for m in recent if not m.is_bot}
            )
            user_summaries = store.get_user_summaries_for_users(
                str(message.channel.id), recent_user_ids
            )

            # Build summary context header
            summary_header = ""
            if channel_summary:
                summary_header += (
                    f"[Channel context: {channel_summary.summary}]\n\n"
                )
            if user_summaries:
                summary_header += "[People in this conversation:\n"
                for s in user_summaries:
                    summary_header += f" - {s.username}: {s.summary}\n"
                summary_header += "]\n\n"
```

Then modify the existing context line (line 276) to prepend the header:

```python
            context = summary_header + "Recent conversation:\n" + format_context_messages(
                recent, attachments_by_msg
            )
```

**Step 4: Add BUILD target**

Add to `projects/monolith/BUILD`:

```python
py_test(
    name = "chat_bot_summary_injection_test",
    srcs = ["chat/bot_summary_injection_test.py"],
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

```
bb remote test //projects/monolith:chat_bot_summary_injection_test --config=ci
```

Expected: PASS

**Step 6: Run all bot tests to check for regressions**

```
bb remote test //projects/monolith:chat_bot_test //projects/monolith:chat_bot_coverage_test //projects/monolith:chat_bot_extra_test //projects/monolith:chat_bot_generate_response_gaps_test //projects/monolith:chat_bot_remaining_gaps_test --config=ci
```

Expected: PASS -- existing tests may need minor updates if they mock `MessageStore` and the new methods are now called. If tests fail because `get_channel_summary` or `get_user_summaries_for_users` are called but not mocked, add `mock_store.get_channel_summary.return_value = None` and `mock_store.get_user_summaries_for_users.return_value = []` to those test fixtures.

**Step 7: Commit**

```
git add projects/monolith/chat/bot.py projects/monolith/chat/bot_summary_injection_test.py projects/monolith/BUILD
git commit -m "feat(chat): inject channel and user summaries into agent context"
```

---

### Task 6: Wire channel summaries into the lifespan loop

**Files:**

- Modify: `projects/monolith/app/main.py:84-94` (add channel summary call)

**Step 1: Update the summary loop**

In `projects/monolith/app/main.py`, modify `_summary_loop()` (lines 84-94) to also call `generate_channel_summaries`:

```python
        async def _summary_loop():
            from chat.summarizer import (
                build_llm_caller,
                generate_channel_summaries,
                generate_summaries,
            )

            while True:
                await asyncio.sleep(86400)  # 24 hours
                try:
                    with Session(get_engine()) as session:
                        llm_caller = build_llm_caller()
                        await generate_summaries(session, llm_caller)
                        await generate_channel_summaries(session, llm_caller)
                except Exception:
                    logger.exception("Summary generation failed")
```

**Step 2: Commit**

```
git add projects/monolith/app/main.py
git commit -m "feat(chat): wire channel summary generation into lifespan loop"
```

---

### Task 7: Chart version bump and full test suite

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` (bump version)
- Modify: `projects/monolith/deploy/application.yaml` (bump targetRevision)

**Step 1: Bump chart version**

In `projects/monolith/chart/Chart.yaml`, bump `version` from `0.17.28` to `0.17.29`.

In `projects/monolith/deploy/application.yaml`, bump `targetRevision` from `0.17.28` to `0.17.29`.

**Step 2: Run full test suite**

```
bb remote test //projects/monolith/... --config=ci
```

Fix any regressions from existing tests that now hit the new store methods without mocking them.

**Step 3: Commit**

```
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to 0.17.29"
```

---

### Task 8: Push and create PR

**Step 1: Push**

```
git push -u origin feat/formalized-summaries
```

**Step 2: Create PR**

Use `gh pr create` with title "feat(chat): formalized summaries with auto-injection" and a body covering:

- Adds `channel_summaries` table for channel-level rolling summaries
- Extends summarizer with `generate_channel_summaries()` + rolling-window-aware prompts
- Auto-injects channel + user summaries into agent context in `_generate_response()`
- Phase 1 of ADR 002 (Discord Chat Automation)

**Step 3: Wait for CI and merge**

Enable auto-merge with `gh pr merge --auto --rebase`. Poll until merged, then verify deployment via ArgoCD MCP tools.
