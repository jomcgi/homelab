"""Tests for the exact prompt templates used by generate_summaries().

The summarizer has two prompt templates:
  1. First-run (no existing summary): "Messages from {username}:\n..." + "Write a 2-4 sentence summary"
  2. Update (existing summary): "Current summary of {username}'s messages:\n..." + "Update the summary"

These templates are never asserted in other test files (summarizer_test.py only
checks that summaries are created/updated, not the text of the prompt itself).
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.models import Message, UserChannelSummary
from chat.summarizer import generate_summaries


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session with schema stripped for SQLite compat."""
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


def _add_message(session, channel_id, user_id, username, content, msg_id):
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


# ---------------------------------------------------------------------------
# First-run prompt template (no existing summary)
# ---------------------------------------------------------------------------


class TestFirstRunPromptTemplate:
    @pytest.mark.asyncio
    async def test_first_run_prompt_starts_with_messages_from_username(self, session):
        """First-run prompt begins with 'Messages from {username}:'."""
        _add_message(session, "ch1", "u1", "Alice", "I deployed the app", 1)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "summary"

        await generate_summaries(session, capture_llm)

        assert len(prompts_received) == 1
        assert prompts_received[0].startswith("Messages from Alice:")

    @pytest.mark.asyncio
    async def test_first_run_prompt_contains_write_summary_instruction(self, session):
        """First-run prompt contains 'Write a 2-4 sentence summary' instruction."""
        _add_message(session, "ch1", "u1", "Alice", "Hello world", 1)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "summary"

        await generate_summaries(session, capture_llm)

        assert "Write a 2-4 sentence summary" in prompts_received[0]

    @pytest.mark.asyncio
    async def test_first_run_prompt_includes_message_content(self, session):
        """First-run prompt includes the actual message content in the text block."""
        _add_message(
            session, "ch1", "u1", "Bob", "Just deployed the new microservice", 1
        )

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "summary"

        await generate_summaries(session, capture_llm)

        assert "Just deployed the new microservice" in prompts_received[0]

    @pytest.mark.asyncio
    async def test_first_run_prompt_does_not_include_current_summary_header(
        self, session
    ):
        """First-run prompt does NOT include the 'Current summary of' header."""
        _add_message(session, "ch1", "u1", "Alice", "Some message", 1)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "summary"

        await generate_summaries(session, capture_llm)

        assert "Current summary of" not in prompts_received[0]
        assert "Update the summary" not in prompts_received[0]


# ---------------------------------------------------------------------------
# Update prompt template (existing summary present)
# ---------------------------------------------------------------------------


class TestUpdatePromptTemplate:
    @pytest.mark.asyncio
    async def test_update_prompt_starts_with_current_summary_header(self, session):
        """Update prompt begins with 'Current summary of {username}'s messages:'."""
        _add_message(session, "ch1", "u1", "Alice", "Old message", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                summary="Alice talked about old things.",
                last_message_id=1,
            )
        )
        session.commit()

        _add_message(session, "ch1", "u1", "Alice", "New message about deployment", 2)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "updated summary"

        await generate_summaries(session, capture_llm)

        assert len(prompts_received) == 1
        assert "Current summary of Alice's messages:" in prompts_received[0]

    @pytest.mark.asyncio
    async def test_update_prompt_includes_existing_summary_text(self, session):
        """Update prompt includes the existing summary text."""
        _add_message(session, "ch1", "u1", "Bob", "Old message", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Bob",
                summary="Bob has been discussing CI pipelines.",
                last_message_id=1,
            )
        )
        session.commit()

        _add_message(session, "ch1", "u1", "Bob", "New message about tests", 2)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "updated"

        await generate_summaries(session, capture_llm)

        assert "Bob has been discussing CI pipelines." in prompts_received[0]

    @pytest.mark.asyncio
    async def test_update_prompt_contains_update_instruction(self, session):
        """Update prompt contains 'Update the summary to incorporate the new messages.'"""
        _add_message(session, "ch1", "u1", "Carol", "Old message", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Carol",
                summary="Carol talked about testing.",
                last_message_id=1,
            )
        )
        session.commit()

        _add_message(session, "ch1", "u1", "Carol", "New message", 2)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "updated summary"

        await generate_summaries(session, capture_llm)

        assert "Keep it to 2-4 concise sentences" in prompts_received[0]

    @pytest.mark.asyncio
    async def test_update_prompt_includes_new_message_content(self, session):
        """Update prompt includes the new message content in the 'New messages' block."""
        _add_message(session, "ch1", "u1", "Dave", "Old stuff", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Dave",
                summary="Dave talked about old stuff.",
                last_message_id=1,
            )
        )
        session.commit()

        _add_message(session, "ch1", "u1", "Dave", "Brand new infrastructure idea", 2)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "updated"

        await generate_summaries(session, capture_llm)

        assert "Brand new infrastructure idea" in prompts_received[0]
        # The update prompt uses "New messages from {username}:"
        assert "New messages from Dave:" in prompts_received[0]

    @pytest.mark.asyncio
    async def test_update_prompt_does_not_use_write_instruction(self, session):
        """Update prompt does NOT contain 'Write a 2-4 sentence summary' (that's for first runs)."""
        _add_message(session, "ch1", "u1", "Eve", "Old message", 1)
        session.add(
            UserChannelSummary(
                channel_id="ch1",
                user_id="u1",
                username="Eve",
                summary="Eve talked about something.",
                last_message_id=1,
            )
        )
        session.commit()

        _add_message(session, "ch1", "u1", "Eve", "Newer message", 2)

        prompts_received = []

        async def capture_llm(prompt: str) -> str:
            prompts_received.append(prompt)
            return "updated"

        await generate_summaries(session, capture_llm)

        assert "Write a 2-4 sentence summary" not in prompts_received[0]
