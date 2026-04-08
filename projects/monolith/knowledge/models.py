"""SQLModel definitions for the knowledge schema."""

import json
from datetime import datetime
from typing import Any, Literal, NewType

NoteId = NewType("NoteId", str)

from pgvector.sqlalchemy import Vector
from pydantic import field_validator
from sqlalchemy import JSON, Column, String
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# Mirror of the CHECK constraint in
# chart/migrations/20260408000000_knowledge_schema.sql - keep in sync.
EdgeType = Literal[
    "refines",
    "generalizes",
    "related",
    "contradicts",
    "derives_from",
    "supersedes",
]
LinkKind = Literal["link", "edge"]

# Postgres uses native TEXT[] for tags/aliases; SQLite falls back to JSON
# so the in-memory test fixture can create the tables.
_STRING_ARRAY = PG_ARRAY(String).with_variant(JSON(), "sqlite")
# Postgres uses JSONB (matching the migration + GIN index); SQLite falls
# back to JSON.
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    __table_args__ = {"schema": "knowledge", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    note_id: NoteId = Field(
        sa_column=Column(String, nullable=False, unique=True)
    )  # stable graph identity, frontmatter `id:`
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
    __table_args__ = {"schema": "knowledge", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    note_fk: int = Field(foreign_key="knowledge.notes.id")
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
    __table_args__ = {"schema": "knowledge", "extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    src_note_fk: int = Field(foreign_key="knowledge.notes.id")
    target_id: str  # target note_id (frontmatter id) or raw wikilink target
    target_title: str | None = None
    # LinkKind / EdgeType are Literals for static-analysis + the
    # __init__ validator below. At the SQL level they're plain TEXT,
    # matching the migration's CHECK constraint.
    kind: LinkKind = Field(sa_column=Column(String, nullable=False))
    edge_type: EdgeType | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )

    def __init__(self, **data: Any) -> None:
        # SQLModel table models skip pydantic validators in __init__, so
        # enforce the discriminated-union invariant manually. This
        # catches typos with a Python stack trace pointing at the call
        # site instead of waiting for the Postgres CHECK violation.
        kind = data.get("kind")
        edge_type = data.get("edge_type")
        if kind == "link" and edge_type is not None:
            raise ValueError(
                f"NoteLink.kind='link' requires edge_type=None, "
                f"got edge_type={edge_type!r}"
            )
        if kind == "edge" and edge_type is None:
            raise ValueError("NoteLink.kind='edge' requires a non-None edge_type")
        super().__init__(**data)
