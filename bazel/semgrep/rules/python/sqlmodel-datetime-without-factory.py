# Tests for sqlmodel-datetime-without-factory rule.
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


# ruleid: sqlmodel-datetime-without-factory
class BadItemBareNone(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime | None = None


# ruleid: sqlmodel-datetime-without-factory
class BadItemOptionalBareNone(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    indexed_at: Optional[datetime] = None


# ruleid: sqlmodel-datetime-without-factory
class BadItemFieldNoFactory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    updated_at: datetime | None = Field(default=None)


# ruleid: sqlmodel-datetime-without-factory
class BadItemOptionalFieldNoFactory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    updated_at: Optional[datetime] = Field(default=None)


# ok: sqlmodel-datetime-without-factory
class OkItemWithFactory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime | None = Field(default_factory=lambda: datetime.utcnow())


# ok: sqlmodel-datetime-without-factory
class OkItemOptionalWithFactory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ok: sqlmodel-datetime-without-factory
class OkItemBaseNotTable(SQLModel):
    created_at: datetime | None = None


# ok: sqlmodel-datetime-without-factory
class OkItemBaseOptionalNotTable(SQLModel):
    indexed_at: Optional[datetime] = None


# ruleid: sqlmodel-datetime-without-factory
class BadItemMultipleDatetimeFields(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime | None = None
    updated_at: Optional[datetime] = None


# ok: sqlmodel-datetime-without-factory
class OkItemNosemgrep(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime | None = None  # nosemgrep: sqlmodel-datetime-without-factory
