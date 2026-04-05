"""Tests for batch save_messages and SaveResult."""

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


def _msg(discord_id: str = "111", content: str = "Hello!", **overrides) -> dict:
    """Helper to build a message dict with sensible defaults."""
    base = {
        "discord_message_id": discord_id,
        "channel_id": "ch1",
        "user_id": "u1",
        "username": "Alice",
        "content": content,
        "is_bot": False,
        "attachments": None,
    }
    base.update(overrides)
    return base


class TestSaveMessages:
    @pytest.mark.asyncio
    async def test_saves_single_message(self, store, session):
        """save_messages with one message returns stored=1 skipped=0."""
        result = await store.save_messages([_msg()])
        assert result.stored == 1
        assert result.skipped == 0
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 1
        assert msgs[0].content == "Hello!"

    @pytest.mark.asyncio
    async def test_saves_batch_of_messages(self, store, session):
        """save_messages persists all messages in a batch."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 3
        messages = [
            _msg("m1", "First"),
            _msg("m2", "Second"),
            _msg("m3", "Third"),
        ]
        result = await store.save_messages(messages)
        assert result.stored == 3
        assert result.skipped == 0
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 3

    @pytest.mark.asyncio
    async def test_skips_duplicates(self, store, session):
        """save_messages skips messages with duplicate discord_message_id."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024]
        await store.save_messages([_msg("dup1", "First")])

        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 2
        result = await store.save_messages(
            [
                _msg("dup1", "Duplicate"),
                _msg("new1", "New"),
            ]
        )
        assert result.stored == 1
        assert result.skipped == 1
        msgs = session.exec(select(Message)).all()
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_calls_embed_batch(self, store):
        """save_messages calls embed_batch with all texts."""
        store.embed_client.embed_batch.return_value = [[0.0] * 1024] * 2
        await store.save_messages(
            [
                _msg("a", "Hello world"),
                _msg("b", "Goodbye world"),
            ]
        )
        store.embed_client.embed_batch.assert_called_once_with(
            ["Hello world", "Goodbye world"]
        )

    @pytest.mark.asyncio
    async def test_saves_attachments(self, store, session):
        """save_messages creates Attachment rows for messages with attachments."""
        msg = _msg(
            "att1",
            "Look!",
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "photo.png",
                    "description": "A cat",
                }
            ],
        )
        await store.save_messages([msg])
        saved = session.exec(select(Attachment)).all()
        assert len(saved) == 1
        assert saved[0].filename == "photo.png"
        blob = session.get(Blob, saved[0].blob_sha256)
        assert blob is not None
        assert blob.description == "A cat"

    @pytest.mark.asyncio
    async def test_embed_text_includes_descriptions(self, store):
        """Embed text includes image descriptions from attachments."""
        msg = _msg(
            "desc1",
            "Beautiful day!",
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "photo.png",
                    "description": "A sunset",
                },
            ],
        )
        await store.save_messages([msg])
        call_args = store.embed_client.embed_batch.call_args[0][0]
        assert len(call_args) == 1
        assert "Beautiful day!" in call_args[0]
        assert "[Image: A sunset]" in call_args[0]

    @pytest.mark.asyncio
    async def test_returns_save_result(self, store):
        """save_messages returns a SaveResult dataclass."""
        result = await store.save_messages([_msg()])
        assert isinstance(result, SaveResult)

    @pytest.mark.asyncio
    async def test_save_message_delegates_to_save_messages(self, store, session):
        """save_message delegates to save_messages and returns the saved Message."""
        msg = await store.save_message(
            discord_message_id="del1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Delegated!",
            is_bot=False,
        )
        assert msg is not None
        assert msg.content == "Delegated!"
        # Verify embed_batch was called (not embed)
        store.embed_client.embed_batch.assert_called_once()
        store.embed_client.embed.assert_not_called()
