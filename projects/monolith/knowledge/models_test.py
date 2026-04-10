"""Unit tests for knowledge.models — NoteLink validation and Chunk._parse_embedding."""

import json

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.models import Chunk, NoteLink


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
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


class TestNoteLinkDiscriminatedUnion:
    """NoteLink enforces a discriminated-union invariant in __init__.

    kind='link' must have edge_type=None.
    kind='edge' must have a non-None edge_type.
    These are enforced manually because SQLModel table models skip pydantic
    validators in __init__ (see comment in models.py).
    """

    def test_link_with_edge_type_raises(self):
        """kind='link' with edge_type set must raise ValueError."""
        with pytest.raises(ValueError, match="kind='link' requires edge_type=None"):
            NoteLink(
                src_note_fk=1,
                target_id="B",
                kind="link",
                edge_type="refines",
            )

    def test_edge_without_edge_type_raises(self):
        """kind='edge' with edge_type=None must raise ValueError."""
        with pytest.raises(ValueError, match="kind='edge' requires"):
            NoteLink(
                src_note_fk=1,
                target_id="B",
                kind="edge",
                edge_type=None,
            )

    def test_valid_link_succeeds(self):
        """kind='link' with edge_type=None is accepted."""
        note_link = NoteLink(
            src_note_fk=1,
            target_id="B",
            kind="link",
            edge_type=None,
        )
        assert note_link.kind == "link"
        assert note_link.edge_type is None
        assert note_link.target_id == "B"

    def test_valid_edge_succeeds(self):
        """kind='edge' with a valid edge_type is accepted."""
        note_link = NoteLink(
            src_note_fk=1,
            target_id="parent",
            kind="edge",
            edge_type="refines",
        )
        assert note_link.kind == "edge"
        assert note_link.edge_type == "refines"
        assert note_link.target_id == "parent"

    def test_link_with_all_valid_edge_types_raises(self):
        """Every known edge_type triggers ValueError when kind='link'."""
        edge_types = [
            "refines",
            "generalizes",
            "related",
            "contradicts",
            "derives_from",
            "supersedes",
        ]
        for et in edge_types:
            with pytest.raises(ValueError, match="kind='link' requires edge_type=None"):
                NoteLink(
                    src_note_fk=1,
                    target_id="x",
                    kind="link",
                    edge_type=et,
                )

    def test_all_valid_edge_types_accepted_with_edge_kind(self):
        """Every known edge_type is accepted when kind='edge'."""
        edge_types = [
            "refines",
            "generalizes",
            "related",
            "contradicts",
            "derives_from",
            "supersedes",
        ]
        for et in edge_types:
            link = NoteLink(
                src_note_fk=1,
                target_id="x",
                kind="edge",
                edge_type=et,
            )
            assert link.edge_type == et


class TestChunkParseEmbedding:
    """Chunk._parse_embedding parses JSON strings and passes lists through unchanged."""

    def test_json_string_is_parsed_to_list(self):
        """A JSON-encoded string is deserialised to a Python list."""
        raw = json.dumps([0.1, 0.2, 0.3])
        result = Chunk._parse_embedding(raw)
        assert result == [0.1, 0.2, 0.3]

    def test_list_input_passes_through_unchanged(self):
        """A list value is returned as-is without modification."""
        data = [0.5] * 8
        result = Chunk._parse_embedding(data)
        assert result is data

    def test_json_string_with_full_dimension_vector(self):
        """A 1024-element JSON embedding string is parsed correctly."""
        vec = [float(i) / 1024 for i in range(1024)]
        raw = json.dumps(vec)
        result = Chunk._parse_embedding(raw)
        assert result == vec
        assert len(result) == 1024

    def test_non_string_non_list_passes_through(self):
        """Non-string, non-list values (e.g. None) pass through for pydantic to handle."""
        result = Chunk._parse_embedding(None)
        assert result is None


def test_raw_input_roundtrip(session):
    from knowledge.models import RawInput

    ri = RawInput(
        raw_id="abc123",
        path="_raw/2026/04/09/abc1-my-note.md",
        source="vault-drop",
        original_path="inbox/my-note.md",
        content="# Hello\n\nBody.",
        content_hash="abc123",
    )
    session.add(ri)
    session.commit()

    loaded = session.get(RawInput, ri.id)
    assert loaded is not None
    assert loaded.raw_id == "abc123"
    assert loaded.source == "vault-drop"
    assert loaded.extra == {}


def test_atom_raw_provenance_roundtrip(session):
    from knowledge.models import AtomRawProvenance, Note, RawInput

    note = Note(
        note_id="hello-world",
        path="_processed/atoms/hello-world.md",
        title="Hello World",
        content_hash="def456",
        type="atom",
    )
    raw = RawInput(
        raw_id="abc123",
        path="_raw/2026/04/09/abc1-my-note.md",
        source="vault-drop",
        content="Body.",
        content_hash="abc123",
    )
    session.add_all([note, raw])
    session.commit()

    prov = AtomRawProvenance(
        atom_fk=note.id,
        raw_fk=raw.id,
        gardener_version="claude-sonnet-4-6@v1",
    )
    session.add(prov)
    session.commit()

    loaded = session.get(AtomRawProvenance, prov.id)
    assert loaded is not None
    assert loaded.atom_fk == note.id
    assert loaded.raw_fk == raw.id


def test_atom_raw_provenance_rejects_both_null():
    from knowledge.models import AtomRawProvenance

    with pytest.raises(ValueError, match="at least one of atom_fk or raw_fk"):
        AtomRawProvenance(
            atom_fk=None,
            raw_fk=None,
            gardener_version="claude-sonnet-4-6@v1",
        )
