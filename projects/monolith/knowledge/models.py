"""SQLModel definitions for the knowledge schema."""

import json
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from pydantic import field_validator
from sqlalchemy import JSON, Column, String
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# Postgres uses native TEXT[] for tags/aliases; SQLite falls back to JSON
# so the in-memory test fixture can create the tables.
_STRING_ARRAY = PG_ARRAY(String).with_variant(JSON(), "sqlite")
# Postgres uses JSONB (matching the migration + GIN index); SQLite falls
# back to JSON.
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    note_id: str = Field(unique=True)  # stable graph identity, frontmatter `id:`
    path: str = Field(unique=True)
    title: str
    content_hash: str
    type: str | None = None
    status: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(_STRING_ARRAY))
    aliases: list[str] = Field(default_factory=list, sa_column=Column(_STRING_ARRAY))
    created_at: datetime | None = None
    updated_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict, sa_column=Column(_JSONB))
    indexed_at: datetime | None = None


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    note_id: int = Field(foreign_key="knowledge.notes.id")
    chunk_index: int
    section_header: str = ""
    chunk_text: str
    embedding: list[float] = Field(sa_column=Column(Vector(1024)))

    @field_validator("embedding", mode="before")
    @classmethod
    def _parse_embedding(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v


class NoteLink(SQLModel, table=True):
    __tablename__ = "note_links"
    __table_args__ = {"schema": "knowledge"}

    id: int | None = Field(default=None, primary_key=True)
    src_note_id: int = Field(foreign_key="knowledge.notes.id")
    target_id: str  # target note_id (frontmatter id) or raw wikilink target
    target_title: str | None = None
    kind: str  # 'edge' | 'link'
    edge_type: str | None = None  # set when kind='edge', NULL when kind='link'
