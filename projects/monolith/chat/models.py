"""Chat message model for pgvector-backed Discord conversation memory."""

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
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
    embedding: list[float] = Field(sa_column=Column(Vector(512)))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
