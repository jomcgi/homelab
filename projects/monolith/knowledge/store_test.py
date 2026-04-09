"""Tests for KnowledgeStore."""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.links import Link
from knowledge.models import Chunk, Note, NoteLink
from knowledge.store import KnowledgeStore

_PG_URL = os.environ.get("TEST_POSTGRES_URL")


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


@pytest.fixture(name="pg_session")
def pg_session_fixture():
    """Session backed by a real Postgres database with pgvector.

    Set TEST_POSTGRES_URL to a connection string like
    ``postgresql://user:pass@localhost/testdb`` to enable.
    The database must have the ``vector`` extension and ``knowledge``
    schema created.
    """
    if _PG_URL is None:
        pytest.skip("TEST_POSTGRES_URL not set — skipping Postgres tests")
    engine = create_engine(_PG_URL)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    # Clean up all rows so tests are hermetic.
    with Session(engine) as session:
        session.execute(Chunk.__table__.delete())
        session.execute(NoteLink.__table__.delete())
        session.execute(Note.__table__.delete())
        session.commit()


@pytest.fixture
def store(session):
    return KnowledgeStore(session=session)


def _meta(**kw):
    return ParsedFrontmatter(**kw)


def _chunks(n):
    return [
        {"index": i, "section_header": f"H{i}", "text": f"chunk {i}"} for i in range(n)
    ]


def _vecs(n):
    return [[float(i)] * 1024 for i in range(n)]


def _upsert(
    store,
    *,
    note_id="a-id",
    path="a.md",
    content_hash="h1",
    title="A",
    metadata=None,
    n_chunks=1,
    links=None,
):
    metadata = metadata or _meta(title=title)
    store.upsert_note(
        note_id=note_id,
        path=path,
        content_hash=content_hash,
        title=title,
        metadata=metadata,
        chunks=_chunks(n_chunks),
        vectors=_vecs(n_chunks),
        links=links or [],
    )


class TestGetIndexed:
    def test_empty(self, store):
        assert store.get_indexed() == {}

    def test_returns_path_to_hash_map(self, store):
        _upsert(store, path="a.md", content_hash="h1")
        assert store.get_indexed() == {"a.md": "h1"}


class TestUpsertNote:
    def test_inserts_note_chunks_and_links(self, store, session):
        _upsert(
            store,
            metadata=_meta(title="A", tags=["ml"]),
            n_chunks=3,
            links=[Link(target="B", display=None)],
        )
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].note_id == "a-id"
        assert notes[0].tags == ["ml"]
        chunks = list(session.scalars(select(Chunk)))
        assert len(chunks) == 3
        assert {c.chunk_index for c in chunks} == {0, 1, 2}
        links = list(session.scalars(select(NoteLink)))
        assert len(links) == 1
        assert links[0].target_id == "B"
        assert links[0].kind == "link"
        assert links[0].edge_type is None

    def test_re_upsert_replaces_chunk_count(self, store, session):
        _upsert(store, content_hash="h1", n_chunks=5)
        _upsert(store, content_hash="h2", n_chunks=2)
        chunks = list(session.scalars(select(Chunk)))
        assert len(chunks) == 2
        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].content_hash == "h2"

    def test_edges_emit_typed_link_rows(self, store, session):
        _upsert(
            store,
            metadata=_meta(
                title="A",
                edges={
                    "refines": ["parent"],
                    "related": ["sib1", "sib2"],
                },
            ),
        )
        rows = list(session.scalars(select(NoteLink).order_by(NoteLink.id)))
        kinds = {r.kind for r in rows}
        assert kinds == {"edge"}
        edge_pairs = {(r.edge_type, r.target_id) for r in rows}
        assert edge_pairs == {
            ("refines", "parent"),
            ("related", "sib1"),
            ("related", "sib2"),
        }

    def test_edges_and_body_links_coexist(self, store, session):
        _upsert(
            store,
            metadata=_meta(title="A", edges={"refines": ["p"]}),
            links=[Link(target="B", display="the b")],
        )
        rows = list(session.scalars(select(NoteLink)))
        by_kind: dict[str, list[NoteLink]] = {"edge": [], "link": []}
        for r in rows:
            by_kind[r.kind].append(r)
        assert len(by_kind["edge"]) == 1
        assert by_kind["edge"][0].edge_type == "refines"
        assert len(by_kind["link"]) == 1
        assert by_kind["link"][0].edge_type is None
        assert by_kind["link"][0].target_title == "the b"


class TestUpsertAtomicity:
    def test_upsert_replace_is_atomic_on_mid_insert_failure(self, store, session):
        _upsert(
            store,
            path="a.md",
            content_hash="h1",
            title="Original",
            metadata=_meta(title="Original"),
            n_chunks=1,
        )

        boom = {"fired": False}

        def _raise_once(_mapper, _connection, _target):
            if boom["fired"]:
                return
            boom["fired"] = True
            raise RuntimeError("simulated mid-insert failure")

        event.listen(Chunk, "after_insert", _raise_once)
        try:
            with pytest.raises(RuntimeError, match="simulated mid-insert failure"):
                _upsert(
                    store,
                    path="a.md",
                    content_hash="h2",
                    title="Replaced",
                    metadata=_meta(title="Replaced"),
                    n_chunks=2,
                )
            # Rollback any outer-transaction state left behind by the
            # failed upsert so we can query the preserved row.
            session.rollback()
        finally:
            event.remove(Chunk, "after_insert", _raise_once)

        notes = list(session.scalars(select(Note)))
        assert len(notes) == 1
        assert notes[0].title == "Original"
        assert notes[0].content_hash == "h1"


class TestNoteLinkValidation:
    def test_notelink_rejects_link_with_edge_type(self):
        with pytest.raises(ValueError, match="kind='link' requires edge_type=None"):
            NoteLink(
                src_note_fk=1,
                target_id="B",
                kind="link",
                edge_type="refines",
            )

    def test_notelink_rejects_edge_without_edge_type(self):
        with pytest.raises(ValueError, match="kind='edge' requires"):
            NoteLink(
                src_note_fk=1,
                target_id="B",
                kind="edge",
                edge_type=None,
            )


class TestDeleteNote:
    def test_cascade_removes_chunks_and_links(self, store, session):
        _upsert(
            store,
            n_chunks=2,
            links=[Link(target="B", display=None)],
        )
        store.delete_note("a.md")
        assert list(session.scalars(select(Note))) == []
        assert list(session.scalars(select(Chunk))) == []
        assert list(session.scalars(select(NoteLink))) == []


class TestSearchNotes:
    """search_notes requires pgvector cosine_distance (Postgres only)."""

    @pytest.fixture(autouse=True)
    def _setup(self, pg_session):
        self.session = pg_session
        self.store = KnowledgeStore(session=pg_session)

    def test_empty_returns_empty_list(self):
        result = self.store.search_notes(query_embedding=[0.0] * 1024)
        assert result == []

    def test_returns_matching_notes_ranked_by_score(self):
        # Insert two notes with distinct embeddings.
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=1)
        _upsert(self.store, note_id="n2", path="b.md", title="Beta", n_chunks=1)

        # Query with the same embedding as note n1's chunk (all 0.0s).
        results = self.store.search_notes(query_embedding=[0.0] * 1024)
        assert len(results) == 2
        # Both results should have the required keys.
        assert set(results[0].keys()) == {"note_id", "title", "path", "score"}
        # First result should be n1 (closer to all-zeros query).
        assert results[0]["note_id"] == "n1"

    def test_limit_restricts_result_count(self):
        for i in range(5):
            _upsert(
                self.store,
                note_id=f"n{i}",
                path=f"{i}.md",
                title=f"Note {i}",
                n_chunks=1,
            )
        results = self.store.search_notes(query_embedding=[0.0] * 1024, limit=2)
        assert len(results) == 2

    def test_exclude_ids_filters_notes(self):
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=1)
        _upsert(self.store, note_id="n2", path="b.md", title="Beta", n_chunks=1)

        results = self.store.search_notes(
            query_embedding=[0.0] * 1024, exclude_ids=["n1"]
        )
        note_ids = [r["note_id"] for r in results]
        assert "n1" not in note_ids
        assert "n2" in note_ids

    def test_score_is_between_zero_and_one(self):
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=1)
        results = self.store.search_notes(query_embedding=[1.0] * 1024)
        assert len(results) == 1
        assert 0.0 <= results[0]["score"] <= 1.0

    def test_best_chunk_score_used_for_multi_chunk_note(self):
        # A note with 2 chunks — the best chunk's score should be used.
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=2)
        results = self.store.search_notes(query_embedding=[0.0] * 1024)
        assert len(results) == 1
        # chunk_0 embedding is all 0.0s, chunk_1 is all 1.0s.
        # Query is all 0.0s, so chunk_0 is a perfect match (distance=0, score=1).
        assert results[0]["score"] == pytest.approx(1.0, abs=1e-6)
