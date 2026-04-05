"""Tests for the None-data guard in store.save_message().

When an attachment dict has data=None (e.g. the bot could not download
the file), save_message() must skip both the Blob creation and the
Attachment row for that attachment, while still persisting the Message.
"""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Attachment, Blob, Message
from chat.store import MessageStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
# None-data guard tests
# ---------------------------------------------------------------------------


class TestSaveMessageNoneDataGuard:
    @pytest.mark.asyncio
    async def test_none_data_attachment_skips_blob_creation(self, store, session):
        """save_message() does not create a Blob when attachment data is None."""
        msg = await store.save_message(
            discord_message_id="nd-1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Here is an image",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/png",
                    "filename": "photo.png",
                    "description": "A photo",
                }
            ],
        )

        assert msg is not None
        blobs = session.exec(select(Blob)).all()
        assert len(blobs) == 0

    @pytest.mark.asyncio
    async def test_none_data_attachment_skips_attachment_row(self, store, session):
        """save_message() does not create an Attachment row when data is None."""
        msg = await store.save_message(
            discord_message_id="nd-2",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Image with missing data",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/jpeg",
                    "filename": "missing.jpg",
                    "description": "Something",
                }
            ],
        )

        assert msg is not None
        attachments = session.exec(
            select(Attachment).where(Attachment.message_id == msg.id)
        ).all()
        assert len(attachments) == 0

    @pytest.mark.asyncio
    async def test_message_is_saved_when_only_attachment_has_none_data(
        self, store, session
    ):
        """save_message() still persists the Message even if all attachments have data=None."""
        msg = await store.save_message(
            discord_message_id="nd-3",
            channel_id="ch1",
            user_id="u1",
            username="Bob",
            content="Check this out",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/png",
                    "filename": "blank.png",
                    "description": None,
                }
            ],
        )

        assert msg is not None
        saved = session.get(Message, msg.id)
        assert saved is not None
        assert saved.content == "Check this out"

    @pytest.mark.asyncio
    async def test_mixed_attachments_only_valid_data_creates_blob(self, store, session):
        """save_message() creates a Blob only for attachments that have non-None data."""
        msg = await store.save_message(
            discord_message_id="nd-4",
            channel_id="ch1",
            user_id="u1",
            username="Carol",
            content="Two attachments, one missing",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/png",
                    "filename": "missing.png",
                    "description": "Missing image",
                },
                {
                    "data": b"\x89PNG\r\n",
                    "content_type": "image/png",
                    "filename": "present.png",
                    "description": "A real image",
                },
            ],
        )

        assert msg is not None
        blobs = session.exec(select(Blob)).all()
        assert len(blobs) == 1
        assert blobs[0].description == "A real image"

    @pytest.mark.asyncio
    async def test_mixed_attachments_only_valid_data_creates_attachment_row(
        self, store, session
    ):
        """save_message() creates an Attachment row only for attachments with non-None data."""
        msg = await store.save_message(
            discord_message_id="nd-5",
            channel_id="ch1",
            user_id="u1",
            username="Dave",
            content="Mixed attachments",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/jpeg",
                    "filename": "gone.jpg",
                    "description": "Gone image",
                },
                {
                    "data": b"\xff\xd8\xff",
                    "content_type": "image/jpeg",
                    "filename": "here.jpg",
                    "description": "Present image",
                },
            ],
        )

        assert msg is not None
        attachments = session.exec(
            select(Attachment).where(Attachment.message_id == msg.id)
        ).all()
        assert len(attachments) == 1
        assert attachments[0].filename == "here.jpg"

    @pytest.mark.asyncio
    async def test_multiple_none_data_attachments_creates_no_blobs(
        self, store, session
    ):
        """save_message() with multiple None-data attachments creates zero Blobs."""
        msg = await store.save_message(
            discord_message_id="nd-6",
            channel_id="ch1",
            user_id="u1",
            username="Eve",
            content="All images missing",
            is_bot=False,
            attachments=[
                {
                    "data": None,
                    "content_type": "image/png",
                    "filename": "a.png",
                    "description": "First",
                },
                {
                    "data": None,
                    "content_type": "image/png",
                    "filename": "b.png",
                    "description": "Second",
                },
                {
                    "data": None,
                    "content_type": "image/gif",
                    "filename": "c.gif",
                    "description": "Third",
                },
            ],
        )

        assert msg is not None
        blobs = session.exec(select(Blob)).all()
        assert len(blobs) == 0
        attachments = session.exec(select(Attachment)).all()
        assert len(attachments) == 0
