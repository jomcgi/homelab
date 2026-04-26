"""SQLModel definitions for the stars schema.

Single history table: each refresh writes one row capturing the run's status
+ scored payload. Reads always target the latest ``status='ok'`` row, so
failed refreshes never break the read path — the last good payload keeps
serving until the next success.
"""

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# Postgres uses JSONB; SQLite test fixture falls back to JSON.
_JSONB = JSONB().with_variant(JSON(), "sqlite")

RefreshStatus = Literal["ok", "error", "running"]


# nosemgrep: sqlmodel-datetime-without-factory (completed_at is intentionally NULL until set)
class RefreshRun(SQLModel, table=True):
    __tablename__ = "refresh_runs"
    __table_args__ = {"schema": "stars", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime
    completed_at: datetime | None = None
    status: RefreshStatus = Field(default="running")
    locations_count: int | None = None
    payload: dict[str, Any] | None = Field(default=None, sa_column=Column(_JSONB))
    error: str | None = None
