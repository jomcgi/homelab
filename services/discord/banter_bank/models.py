from datetime import datetime
import uuid

from sqlmodel import SQLModel, Field


class Base(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class User(Base, table=True):
    id: int = Field(primary_key=True)
    modified_at: datetime = Field(default_factory=datetime.now)
    joined_at: datetime | None
    created_at: datetime | None
    bot: bool
    global_name: str
    display_name: str
    nick: str
