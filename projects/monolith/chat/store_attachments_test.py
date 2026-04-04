"""Additional tests for get_attachments() edge cases and save_message() with attachments."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Attachment, Message
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
# TestGetAttachmentsEdgeCases
# ---------------------------------------------------------------------------


class TestGetAttachmentsEdgeCases:
    def test_empty_message_ids_returns_empty_dict(self, store):
        """get_attachments([]) returns an empty dict without querying the DB."""
        result = store.get_attachments([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_multiple_messages_each_with_own_attachments(self, store, session):
        """get_attachments returns correct lists keyed by message_id for multiple messages."""
        msg1 = await store.save_message(
            discord_message_id="m1",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Photo 1",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "a.png",
                    "description": "A cat",
                }
            ],
        )
        msg2 = await store.save_message(
            discord_message_id="m2",
            channel_id="ch1",
            user_id="u2",
            username="Bob",
            content="Photo 2",
            is_bot=False,
            attachments=[
                {
                    "data": b"\xff\xd8\xff",
                    "content_type": "image/jpeg",
                    "filename": "b.jpg",
                    "description": "A dog",
                },
                {
                    "data": b"\x47\x49\x46",
                    "content_type": "image/gif",
                    "filename": "c.gif",
                    "description": "A bird",
                },
            ],
        )

        result = store.get_attachments([msg1.id, msg2.id])

        assert msg1.id in result
        assert len(result[msg1.id]) == 1
        assert result[msg1.id][0].description == "A cat"

        assert msg2.id in result
        assert len(result[msg2.id]) == 2
        descriptions = {a.description for a in result[msg2.id]}
        assert descriptions == {"A dog", "A bird"}

    @pytest.mark.asyncio
    async def test_message_with_no_attachments_not_in_result(self, store, session):
        """get_attachments excludes message IDs that have no attachments."""
        msg_no_att = await store.save_message(
            discord_message_id="plain",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Just text",
            is_bot=False,
        )
        msg_with_att = await store.save_message(
            discord_message_id="withatt",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="With image",
            is_bot=False,
            attachments=[
                {
                    "data": b"\x89PNG",
                    "content_type": "image/png",
                    "filename": "x.png",
                    "description": "An image",
                }
            ],
        )

        result = store.get_attachments([msg_no_att.id, msg_with_att.id])

        assert msg_no_att.id not in result
        assert msg_with_att.id in result

    @pytest.mark.asyncio
    async def test_nonexistent_message_ids_return_empty(self, store):
        """get_attachments for IDs not in the DB returns an empty dict."""
        result = store.get_attachments([99999, 88888])
        assert result == {}


# ---------------------------------------------------------------------------
# TestSaveMessageWithAttachmentsAdditional
# ---------------------------------------------------------------------------


class TestSaveMessageWithAttachmentsAdditional:
    @pytest.mark.asyncio
    async def test_saves_multiple_attachments_for_single_message(self, store, session):
        """save_message() persists multiple attachments all linked to the same message."""
        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "first.png",
                "description": "First image",
            },
            {
                "data": b"\xff\xd8\xff",
                "content_type": "image/jpeg",
                "filename": "second.jpg",
                "description": "Second image",
            },
            {
                "data": b"\x47\x49\x46",
                "content_type": "image/gif",
                "filename": "third.gif",
                "description": "Third image",
            },
        ]
        msg = await store.save_message(
            discord_message_id="multi",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Three images!",
            is_bot=False,
            attachments=attachments,
        )

        assert msg is not None
        saved = session.exec(
            select(Attachment).where(Attachment.message_id == msg.id)
        ).all()
        assert len(saved) == 3
        filenames = {a.filename for a in saved}
        assert filenames == {"first.png", "second.jpg", "third.gif"}

    @pytest.mark.asyncio
    async def test_empty_attachments_list_saves_no_attachment_rows(
        self, store, session
    ):
        """save_message() with attachments=[] stores the message but no Attachment rows."""
        msg = await store.save_message(
            discord_message_id="noatt",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Text only",
            is_bot=False,
            attachments=[],
        )

        assert msg is not None
        saved = session.exec(select(Attachment)).all()
        assert len(saved) == 0

    @pytest.mark.asyncio
    async def test_attachment_data_is_preserved_exactly(self, store, session):
        """save_message() stores attachment bytes without modification."""
        raw_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        msg = await store.save_message(
            discord_message_id="bytes_check",
            channel_id="ch1",
            user_id="u1",
            username="Alice",
            content="Image",
            is_bot=False,
            attachments=[
                {
                    "data": raw_bytes,
                    "content_type": "image/png",
                    "filename": "test.png",
                    "description": "A test",
                }
            ],
        )

        saved = session.exec(
            select(Attachment).where(Attachment.message_id == msg.id)
        ).first()
        assert saved is not None
        assert saved.data == raw_bytes


# ---------------------------------------------------------------------------
# TestAttachmentModel -- basic instantiation
# ---------------------------------------------------------------------------


class TestAttachmentModelInstantiation:
    def test_attachment_instantiation_with_required_fields(self):
        """Attachment can be instantiated with all required fields set correctly."""
        att = Attachment(
            message_id=42,
            data=b"\x89PNG",
            content_type="image/png",
            filename="screenshot.png",
            description="A screenshot of the dashboard",
        )
        assert att.message_id == 42
        assert att.data == b"\x89PNG"
        assert att.content_type == "image/png"
        assert att.filename == "screenshot.png"
        assert att.description == "A screenshot of the dashboard"
        assert att.id is None  # Not persisted yet; primary key is None

    def test_attachment_id_defaults_to_none(self):
        """Attachment.id is None before DB persistence."""
        att = Attachment(
            message_id=1,
            data=b"",
            content_type="image/gif",
            filename="anim.gif",
            description="Animated",
        )
        assert att.id is None
