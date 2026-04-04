"""Chat models for pgvector-backed Discord conversation memory."""

import json
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from pydantic import field_validator
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
    embedding: list[float] = Field(sa_column=Column(Vector(1024)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("embedding", mode="before")
    @classmethod
    def _parse_embedding(cls, v: object) -> object:
        """Parse pgvector string representation from raw SQL results."""
        if isinstance(v, str):
            return json.loads(v)
        return v


class Attachment(SQLModel, table=True):
    __tablename__ = "attachments"
    __table_args__ = {"schema": "chat"}

    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="chat.messages.id")
    data: bytes
    content_type: str
    filename: str
    description: str
