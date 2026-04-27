"""Integration tests for Phase A of the discardable-stub rewrite.

When a stub at ``_researching/<slug>.md`` carries ``triaged: discardable``,
``discover_gaps`` should rewrite ``[[X]]`` -> bare text in every source note
that references the slug, and skip the ``write_stub`` refresh for that slug.

The rewrite is gated on ``KNOWLEDGE_GAPS_REWRITE_DISCARDABLE``: with the
flag off (default) we log dry-run counts; with the flag on we mutate disk.

Fixture style mirrors ``gap_lifecycle_test.py`` — duplicated locally because
no shared conftest covers this concern.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.gaps import discover_gaps
from knowledge.models import Note, NoteLink


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


def _make_note(
    session: Session,
    note_id: str,
    *,
    title: str | None = None,
) -> Note:
    note = Note(
        note_id=note_id,
        path=f"_processed/{note_id}.md",
        title=title or note_id,
        content_hash=f"hash-{note_id}",
        type="atom",
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _add_body_link(session: Session, *, src_fk: int, target_id: str) -> None:
    session.add(
        NoteLink(
            src_note_fk=src_fk,
            target_id=target_id,
            target_title=target_id,
            kind="link",
            edge_type=None,
        )
    )
    session.commit()


def _write_source(tmp_path: Path, note_id: str, body: str) -> Path:
    path = tmp_path / "_processed" / f"{note_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _write_stub(tmp_path: Path, slug: str, *, triaged: str | None = None) -> Path:
    path = tmp_path / "_researching" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = [f"id: {slug}", "type: gap", "status: discovered"]
    if triaged:
        fm_lines.append(f"triaged: {triaged}")
    fm = "\n".join(fm_lines)
    path.write_text(f"---\n{fm}\n---\n\n")
    return path


def test_discardable_stub_rewrites_source_when_flag_on(monkeypatch, session, tmp_path):
    """Phase A: KNOWLEDGE_GAPS_REWRITE_DISCARDABLE=1 + triaged: discardable stub
    => source notes are rewritten and write_stub is skipped."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    src_path = _write_source(
        tmp_path,
        "source-atom",
        (
            "---\nid: source-atom\ntitle: Source Atom\ntype: atom\n---\n\n"
            "We use [[Discardable Concept]] often.\n"
        ),
    )
    stub_path = _write_stub(tmp_path, "discardable-concept", triaged="discardable")
    src = _make_note(session, "source-atom", title="Source Atom")
    _add_body_link(session, src_fk=src.id, target_id="discardable-concept")

    discover_gaps(session, tmp_path)

    rewritten = src_path.read_text()
    assert "[[Discardable Concept]]" not in rewritten
    assert "We use Discardable Concept often." in rewritten
    # write_stub was skipped — so referenced_by was NEVER added by this run.
    fm = yaml.safe_load(stub_path.read_text().split("---\n", 2)[1])
    assert "referenced_by" not in fm


def test_discardable_stub_dry_run_when_flag_off(monkeypatch, session, tmp_path):
    """Without the flag, discover_gaps logs but does not mutate source notes."""
    monkeypatch.delenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", raising=False)
    body = (
        "---\nid: src\ntitle: Src\ntype: atom\n---\n\n"
        "We use [[Discardable Concept]] often.\n"
    )
    src_path = _write_source(tmp_path, "src", body)
    _write_stub(tmp_path, "discardable-concept", triaged="discardable")
    src = _make_note(session, "src", title="Src")
    _add_body_link(session, src_fk=src.id, target_id="discardable-concept")

    discover_gaps(session, tmp_path)

    # File untouched.
    assert src_path.read_text() == body


def test_non_discardable_stub_unaffected(monkeypatch, session, tmp_path):
    """Stubs without the discardable marker behave exactly as today."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    body = (
        "---\nid: src\ntitle: Src\ntype: atom\n---\n\n"
        "[[Real Concept]] is interesting.\n"
    )
    src_path = _write_source(tmp_path, "src", body)
    src = _make_note(session, "src", title="Src")
    _add_body_link(session, src_fk=src.id, target_id="real-concept")

    discover_gaps(session, tmp_path)

    # Source untouched (no discardable marker on a stub for this slug).
    assert src_path.read_text() == body
    # Stub is created normally with referenced_by populated.
    new_stub = tmp_path / "_researching" / "real-concept.md"
    assert new_stub.exists()
    fm = yaml.safe_load(new_stub.read_text().split("---\n", 2)[1])
    assert fm.get("referenced_by") == ["src"]


def test_discardable_no_refs_no_rewrite(monkeypatch, session, tmp_path):
    """Discardable stub with NO source references — Phase A is a no-op
    for this slug (Phase B / Task 4 will tombstone it; we don't yet)."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    stub_path = _write_stub(tmp_path, "orphan", triaged="discardable")
    # No source notes link to "orphan", so slug_refs is empty for it.
    discover_gaps(session, tmp_path)
    # Stub is preserved (Task 4 deletes it; here we only verify Phase A doesn't blow up).
    assert stub_path.exists()
