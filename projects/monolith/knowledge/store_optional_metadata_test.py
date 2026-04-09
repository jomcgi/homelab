"""Tests for optional metadata fields persisted by KnowledgeStore.upsert_note.

The coverage review identified that the ``type``, ``status``, ``source``, and
``aliases`` fields on ``Note`` are never asserted after an insert.  These tests
verify that values supplied via ``ParsedFrontmatter`` are stored correctly.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.models import Note
from knowledge.store import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures (mirrors store_extra_test.py)
# ---------------------------------------------------------------------------


@pytest.fixture(name="session")
def session_fixture():
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
    return KnowledgeStore(session=session)


def _upsert_with_meta(store, metadata: ParsedFrontmatter):
    store.upsert_note(
        note_id="meta-note",
        path="meta.md",
        content_hash="hm1",
        title="Meta Note",
        metadata=metadata,
        chunks=[],
        vectors=[],
        links=[],
    )


# ---------------------------------------------------------------------------
# Optional metadata field assertions
# ---------------------------------------------------------------------------


class TestOptionalMetadataFields:
    """Verify that type, status, source, and aliases from ParsedFrontmatter
    are persisted onto the Note row after upsert_note."""

    def test_type_is_persisted(self, store, session):
        """Note.type is set when metadata.type is provided."""
        meta = ParsedFrontmatter(type="concept")
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.type == "concept"

    def test_status_is_persisted(self, store, session):
        """Note.status is set when metadata.status is provided."""
        meta = ParsedFrontmatter(status="evergreen")
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.status == "evergreen"

    def test_source_is_persisted(self, store, session):
        """Note.source is set when metadata.source is provided."""
        meta = ParsedFrontmatter(source="https://example.com/article")
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.source == "https://example.com/article"

    def test_aliases_are_persisted(self, store, session):
        """Note.aliases is set when metadata.aliases is provided."""
        meta = ParsedFrontmatter(aliases=["alt-title", "second-alias"])
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.aliases == ["alt-title", "second-alias"]

    def test_all_optional_fields_together(self, store, session):
        """All four optional fields are persisted correctly when all are set."""
        meta = ParsedFrontmatter(
            type="reference",
            status="draft",
            source="https://paper.example.org",
            aliases=["ref-1", "ref-2"],
        )
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.type == "reference"
        assert note.status == "draft"
        assert note.source == "https://paper.example.org"
        assert note.aliases == ["ref-1", "ref-2"]

    def test_none_values_are_persisted_as_none(self, store, session):
        """When optional fields are omitted (None), the Note row stores None."""
        meta = ParsedFrontmatter()  # all optional fields default to None/[]
        _upsert_with_meta(store, meta)
        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.type is None
        assert note.status is None
        assert note.source is None
        assert note.aliases == []

    def test_re_upsert_updates_optional_fields(self, store, session):
        """Re-upserting a note with new optional-field values replaces the old ones."""
        meta_v1 = ParsedFrontmatter(type="fleeting", status="seed")
        _upsert_with_meta(store, meta_v1)

        # Now re-upsert with different values
        store.upsert_note(
            note_id="meta-note",
            path="meta.md",
            content_hash="hm2",
            title="Meta Note v2",
            metadata=ParsedFrontmatter(type="evergreen", status="published"),
            chunks=[],
            vectors=[],
            links=[],
        )

        note = session.exec(select(Note).where(Note.path == "meta.md")).first()
        assert note is not None
        assert note.type == "evergreen"
        assert note.status == "published"
