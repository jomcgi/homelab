"""Tests for MessageStore bulk/edge-case behaviors not covered elsewhere.

Covers gaps identified in:
- save_message() with attachments missing a description key
- save_message() with attachments where description is empty string (falsy)
- get_recent() called with the default limit (no explicit limit arg)
- get_recent() when requested limit exceeds available messages
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Attachment, Blob, Message
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


# ---------------------------------------------------------------------------
# save_message() — attachment without a description key
# ---------------------------------------------------------------------------


class TestSaveMessageAttachmentNoDescription:
    @pytest.mark.asyncio
    async def test_attachment_without_description_key_excluded_from_embed_text(
        self, store
    ):
        """save_message omits [Image: ...] from embed text when description key is absent."""
        await store.save_message(
            discord_message_id="nodesc1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Look at this!",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "photo.png",
                    # no "description" key
                }
            ],
        )
        # Without a description, embed text is exactly the content
        store.embed_client.embed.assert_called_once_with("Look at this!")

    @pytest.mark.asyncio
    async def test_attachment_without_description_key_blob_description_empty(
        self, store, session
    ):
        """save_message stores blob.description as '' when description key is absent."""
        await store.save_message(
            discord_message_id="nodesc2",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Photo",
            is_bot=False,
            attachments=[
                {
                    "data": b"\xff\xd8\xff",
                    "content_type": "image/jpeg",
                    "filename": "img.jpg",
                }
            ],
        )
        blobs = session.exec(select(Blob)).all()
        assert len(blobs) == 1
        assert blobs[0].description == ""

    @pytest.mark.asyncio
    async def test_attachment_with_empty_string_description_excluded_from_embed_text(
        self, store
    ):
        """save_message omits [Image: ...] from embed text when description is empty string."""
        await store.save_message(
            discord_message_id="emptydesc1",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Here!",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "photo.png",
                    "description": "",  # falsy empty string
                }
            ],
        )
        # Empty description is falsy → not included in embed text
        store.embed_client.embed.assert_called_once_with("Here!")

    @pytest.mark.asyncio
    async def test_attachment_with_empty_string_description_blob_description_empty(
        self, store, session
    ):
        """save_message stores blob.description as '' when description is empty string."""
        await store.save_message(
            discord_message_id="emptydesc2",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Photo",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x47\x49\x46",
                    "content_type": "image/gif",
                    "filename": "anim.gif",
                    "description": "",
                }
            ],
        )
        blobs = session.exec(select(Blob)).all()
        assert len(blobs) == 1
        assert blobs[0].description == ""

    @pytest.mark.asyncio
    async def test_mix_described_and_undescribed_attachments_only_described_in_embed(
        self, store
    ):
        """Only attachments with non-empty descriptions appear in the embed text."""
        await store.save_message(
            discord_message_id="mix1",
            channel_id="ch1",
            user_id="u1",
            username="Carol",
            content="Two pics",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "with_desc.png",
                    "description": "A sunset",
                },
                {
                    "data": b"\xff\xd8\xff",
                    "content_type": "image/jpeg",
                    "filename": "no_desc.jpg",
                    # no description key
                },
            ],
        )
        embed_text = store.embed_client.embed.call_args[0][0]
        assert "[Image: A sunset]" in embed_text
        # Second attachment has no description so should NOT appear
        assert embed_text.count("[Image:") == 1

    @pytest.mark.asyncio
    async def test_attachment_without_description_still_saves_attachment_row(
        self, store, session
    ):
        """Attachment rows are created even when the attachment has no description key."""
        msg = await store.save_message(
            discord_message_id="nodesc3",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="No desc",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "plain.png",
                }
            ],
        )
        assert msg is not None
        atts = session.exec(
            select(Attachment).where(Attachment.message_id == msg.id)
        ).all()
        assert len(atts) == 1
        assert atts[0].filename == "plain.png"


# ---------------------------------------------------------------------------
# get_recent() — default limit and limit-exceeds-count behavior
# ---------------------------------------------------------------------------


class TestGetRecentDefaultLimit:
    def test_default_limit_returns_twenty_most_recent_of_many(self, store, session):
        """get_recent() with no limit arg returns at most 20 messages (the default)."""
        for i in range(25):
            session.add(
                Message(
                    discord_message_id=str(i),
                    channel_id="ch1",
                    user_id="u1",
                    username="Alice",
                    content=f"msg {i}",
                    is_bot=False,
                    embedding=[0.0] * 1024,
                    created_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        # Call without explicit limit — default is 20
        result = store.get_recent("ch1")
        assert len(result) == 20

    def test_default_limit_returns_newest_twenty_oldest_first(self, store, session):
        """get_recent() default limit returns the 20 newest messages, ordered oldest first."""
        for i in range(25):
            session.add(
                Message(
                    discord_message_id=str(i),
                    channel_id="ch1",
                    user_id="u1",
                    username="Alice",
                    content=f"msg {i}",
                    is_bot=False,
                    embedding=[0.0] * 1024,
                    created_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        result = store.get_recent("ch1")
        # Messages 5..24 are the 20 newest; oldest-first means msg 5 comes first
        assert result[0].content == "msg 5"
        assert result[-1].content == "msg 24"

    def test_limit_exceeds_available_returns_all(self, store, session):
        """get_recent() returns all messages when limit > number of stored messages."""
        for i in range(3):
            session.add(
                Message(
                    discord_message_id=str(i),
                    channel_id="ch1",
                    user_id="u1",
                    username="Alice",
                    content=f"msg {i}",
                    is_bot=False,
                    embedding=[0.0] * 1024,
                    created_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        result = store.get_recent("ch1", limit=100)
        assert len(result) == 3

    def test_limit_one_returns_single_most_recent(self, store, session):
        """get_recent() with limit=1 returns a single-element list with the newest message."""
        for i in range(5):
            session.add(
                Message(
                    discord_message_id=str(i),
                    channel_id="ch1",
                    user_id="u1",
                    username="Alice",
                    content=f"msg {i}",
                    is_bot=False,
                    embedding=[0.0] * 1024,
                    created_at=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        session.commit()

        result = store.get_recent("ch1", limit=1)
        assert len(result) == 1
        assert result[0].content == "msg 4"
