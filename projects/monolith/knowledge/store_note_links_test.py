"""Tests for KnowledgeStore.get_note_links() and edges in search_notes_with_context()."""

from __future__ import annotations

import os

import pytest
from sqlmodel import Session, SQLModel, create_engine

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.links import Link
from knowledge.models import Chunk, Note, NoteLink
from knowledge.store import KnowledgeStore

_PG_URL = os.environ.get("TEST_POSTGRES_URL")


@pytest.fixture(name="session")
def session_fixture():
    from sqlmodel.pool import StaticPool

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
    """Real Postgres session with pgvector for search tests.

    Set TEST_POSTGRES_URL to enable (e.g. ``postgresql://user:pass@host/db``).
    """
    if _PG_URL is None:
        pytest.skip("TEST_POSTGRES_URL not set — skipping Postgres tests")
    engine = create_engine(_PG_URL)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
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


# ---------------------------------------------------------------------------
# get_note_links — unit tests (SQLite)
# ---------------------------------------------------------------------------


class TestGetNoteLinks:
    def test_note_with_links_returns_correct_dicts(self, store):
        """A note with wikilinks returns the expected list of link dicts."""
        _upsert(
            store,
            note_id="a-id",
            path="a.md",
            links=[
                Link(target="B", display="the B"),
                Link(target="C", display=None),
            ],
        )
        links = store.get_note_links("a-id")
        assert len(links) == 2
        targets = {lnk["target_id"] for lnk in links}
        assert targets == {"B", "C"}
        b_link = next(lnk for lnk in links if lnk["target_id"] == "B")
        assert b_link["target_title"] == "the B"
        assert b_link["kind"] == "link"
        assert b_link["edge_type"] is None

    def test_note_with_edges_returns_correct_dicts(self, store):
        """Typed frontmatter edges are returned with kind='edge' and edge_type set."""
        _upsert(
            store,
            note_id="a-id",
            path="a.md",
            metadata=_meta(title="A", edges={"refines": ["parent-id"]}),
        )
        links = store.get_note_links("a-id")
        assert len(links) == 1
        assert links[0]["target_id"] == "parent-id"
        assert links[0]["kind"] == "edge"
        assert links[0]["edge_type"] == "refines"
        assert links[0]["target_title"] is None

    def test_note_with_no_links_returns_empty_list(self, store):
        """A note with no links or edges returns []."""
        _upsert(store, note_id="a-id", path="a.md", links=[])
        links = store.get_note_links("a-id")
        assert links == []

    def test_nonexistent_note_id_returns_empty_list(self, store):
        """get_note_links for an unknown note_id returns [] without error."""
        links = store.get_note_links("does-not-exist")
        assert links == []

    def test_nonexistent_note_id_on_empty_db_returns_empty_list(self, store):
        """get_note_links on an empty database returns []."""
        links = store.get_note_links("ghost")
        assert links == []

    def test_returns_only_links_for_specified_note(self, store):
        """Links from other notes are not included in the result."""
        _upsert(
            store,
            note_id="a-id",
            path="a.md",
            links=[Link(target="X", display=None)],
        )
        _upsert(
            store,
            note_id="b-id",
            path="b.md",
            links=[Link(target="Y", display=None)],
        )
        links_a = store.get_note_links("a-id")
        assert len(links_a) == 1
        assert links_a[0]["target_id"] == "X"

    def test_result_dict_has_required_keys(self, store):
        """Every returned dict contains target_id, target_title, kind, edge_type."""
        _upsert(
            store,
            note_id="a-id",
            path="a.md",
            links=[Link(target="Z", display="Zee")],
        )
        links = store.get_note_links("a-id")
        assert len(links) == 1
        assert set(links[0].keys()) == {
            "target_id",
            "target_title",
            "kind",
            "edge_type",
        }

    def test_mixed_links_and_edges(self, store):
        """A note with both wikilinks and frontmatter edges returns all of them."""
        _upsert(
            store,
            note_id="a-id",
            path="a.md",
            metadata=_meta(title="A", edges={"related": ["rel-1"]}),
            links=[Link(target="wiki-1", display=None)],
        )
        links = store.get_note_links("a-id")
        assert len(links) == 2
        kinds = {lnk["kind"] for lnk in links}
        assert kinds == {"link", "edge"}


# ---------------------------------------------------------------------------
# search_notes_with_context — edges (Postgres only)
# ---------------------------------------------------------------------------


class TestSearchNotesWithContextEdges:
    """Verify the ``edges`` key in search_notes_with_context results.

    Requires pgvector (Postgres). Tests are skipped when TEST_POSTGRES_URL
    is unset, matching the pattern used by TestSearchNotesWithContext in
    store_test.py.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, pg_session):
        self.session = pg_session
        self.store = KnowledgeStore(session=pg_session)

    def test_search_result_includes_edges_key(self):
        """Every search result must have an 'edges' key."""
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=1)
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        assert len(results) == 1
        assert "edges" in results[0]

    def test_edges_is_list(self):
        """The 'edges' value is always a list (not None, not dict)."""
        _upsert(self.store, note_id="n1", path="a.md", title="Alpha", n_chunks=1)
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        assert isinstance(results[0]["edges"], list)

    def test_empty_edges_when_note_has_no_links(self):
        """A note with no links or edges produces edges=[]."""
        _upsert(
            self.store,
            note_id="n1",
            path="a.md",
            title="Alpha",
            n_chunks=1,
            links=[],
        )
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        assert results[0]["edges"] == []

    def test_edges_contain_wikilink_data(self):
        """Wikilinks appear in edges with kind='link' and edge_type=None."""
        _upsert(
            self.store,
            note_id="n1",
            path="a.md",
            title="Alpha",
            n_chunks=1,
            links=[Link(target="n2", display="Beta")],
        )
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        assert len(results) == 1
        edges = results[0]["edges"]
        assert len(edges) == 1
        assert edges[0]["target_id"] == "n2"
        assert edges[0]["target_title"] == "Beta"
        assert edges[0]["kind"] == "link"
        assert edges[0]["edge_type"] is None

    def test_edges_contain_frontmatter_edge_data(self):
        """Typed frontmatter edges appear in edges with kind='edge' and edge_type set."""
        _upsert(
            self.store,
            note_id="n1",
            path="a.md",
            title="Alpha",
            n_chunks=1,
            metadata=_meta(title="Alpha", edges={"refines": ["parent-id"]}),
        )
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        assert len(results) == 1
        edges = results[0]["edges"]
        assert len(edges) == 1
        assert edges[0]["target_id"] == "parent-id"
        assert edges[0]["kind"] == "edge"
        assert edges[0]["edge_type"] == "refines"

    def test_edges_dict_keys(self):
        """Each edge dict has the four required keys."""
        _upsert(
            self.store,
            note_id="n1",
            path="a.md",
            title="Alpha",
            n_chunks=1,
            links=[Link(target="x", display="X")],
        )
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        edge = results[0]["edges"][0]
        assert set(edge.keys()) == {"target_id", "target_title", "kind", "edge_type"}

    def test_edges_independent_per_note(self):
        """Each result only includes edges belonging to that note."""
        _upsert(
            self.store,
            note_id="n1",
            path="a.md",
            title="Alpha",
            n_chunks=1,
            links=[Link(target="link-a", display=None)],
        )
        _upsert(
            self.store,
            note_id="n2",
            path="b.md",
            title="Beta",
            n_chunks=1,
            links=[Link(target="link-b", display=None)],
        )
        results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
        by_id = {r["note_id"]: r for r in results}
        assert by_id["n1"]["edges"][0]["target_id"] == "link-a"
        assert by_id["n2"]["edges"][0]["target_id"] == "link-b"
