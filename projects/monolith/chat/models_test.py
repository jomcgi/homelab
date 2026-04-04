"""Tests for chat SQLModel definitions."""

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel

from chat.models import Attachment, Blob, Message


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
            embedding=[0.0] * 1024,
        )
        assert msg.is_bot is False

    def test_embedding_validator_parses_string(self):
        """Embedding validator converts pgvector string to list."""
        msg = Message.model_validate(
            {
                "discord_message_id": "1",
                "channel_id": "c",
                "user_id": "u",
                "username": "bot",
                "content": "hi",
                "embedding": "[0.1,0.2,0.3]",
            }
        )
        assert msg.embedding == [0.1, 0.2, 0.3]

    def test_embedding_validator_passes_list_through(self):
        """Embedding validator leaves a native list unchanged."""
        vec = [0.4, 0.5, 0.6]
        msg = Message.model_validate(
            {
                "discord_message_id": "2",
                "channel_id": "c",
                "user_id": "u",
                "username": "bot",
                "content": "hi",
                "embedding": vec,
            }
        )
        assert msg.embedding == vec

    def test_embedding_validator_raises_on_invalid_json_string(self):
        """Embedding validator raises ValidationError for non-JSON strings."""
        with pytest.raises(ValidationError):
            Message.model_validate(
                {
                    "discord_message_id": "3",
                    "channel_id": "c",
                    "user_id": "u",
                    "username": "bot",
                    "content": "hi",
                    "embedding": "not-json",
                }
            )

    def test_embedding_validator_raises_on_empty_string(self):
        """Embedding validator raises ValidationError for empty string."""
        with pytest.raises(ValidationError):
            Message.model_validate(
                {
                    "discord_message_id": "4",
                    "channel_id": "c",
                    "user_id": "u",
                    "username": "bot",
                    "content": "hi",
                    "embedding": "",
                }
            )

    @pytest.mark.parametrize("bad_value", [None, 42, {"key": "value"}])
    def test_embedding_validator_does_not_intercept_non_string_types(self, bad_value):
        """Validator skips non-string inputs; Pydantic then rejects non-list[float] values."""
        with pytest.raises(ValidationError):
            Message.model_validate(
                {
                    "discord_message_id": "5",
                    "channel_id": "c",
                    "user_id": "u",
                    "username": "bot",
                    "content": "hi",
                    "embedding": bad_value,
                }
            )


class TestAttachmentModel:
    def test_attachment_table_name(self):
        """Attachment model maps to chat.attachments table."""
        assert Attachment.__tablename__ == "attachments"
        assert Attachment.__table_args__["schema"] == "chat"

    def test_attachment_has_required_fields(self):
        """Attachment model has all expected columns."""
        columns = {c.name for c in Attachment.__table__.columns}
        expected = {
            "id",
            "message_id",
            "blob_sha256",
            "filename",
        }
        assert expected == columns

    def test_attachment_construction(self):
        """Attachment can be constructed with all fields."""
        att = Attachment(
            message_id=1,
            blob_sha256="abc123",
            filename="photo.png",
        )
        assert att.blob_sha256 == "abc123"
        assert att.filename == "photo.png"


class TestBlobModel:
    def test_blob_table_name(self):
        """Blob model maps to chat.blobs table."""
        assert Blob.__tablename__ == "blobs"
        assert Blob.__table_args__["schema"] == "chat"

    def test_blob_has_required_fields(self):
        """Blob model has all expected columns."""
        columns = {c.name for c in Blob.__table__.columns}
        expected = {
            "sha256",
            "data",
            "content_type",
            "description",
        }
        assert expected == columns

    def test_blob_construction(self):
        """Blob can be constructed with all fields."""
        blob = Blob(
            sha256="deadbeef" * 8,
            data=b"\x89PNG",
            content_type="image/png",
            description="A photo of a cat",
        )
        assert blob.content_type == "image/png"
        assert blob.data == b"\x89PNG"
        assert blob.description == "A photo of a cat"

    def test_blob_description_defaults_empty(self):
        """Blob.description defaults to empty string."""
        blob = Blob(
            sha256="abcd1234" * 8,
            data=b"",
            content_type="image/gif",
        )
        assert blob.description == ""
