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


def _make_message(
    session, channel_id, user_id, username, content, msg_id, is_bot=False
):
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
        all_summaries = list(session.exec(select(ChannelSummary)).all())
        assert len(all_summaries) == 1
