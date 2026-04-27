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
from unittest.mock import AsyncMock

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.gaps import GAPS_PIPELINE_VERSION, discover_gaps
from knowledge.models import Gap, Note, NoteLink
from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore


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


def test_tombstone_removes_gap_when_refs_gone(monkeypatch, session, tmp_path):
    """Phase B: a discardable Gap row whose source links are gone is deleted,
    and its stub file is unlinked, in the same discover_gaps call."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    # Pre-existing Gap row + discardable stub, but NO source notes
    # reference it (simulating "post-rewrite" steady state).
    session.add(
        Gap(
            term="discardable-concept",
            note_id="discardable-concept",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()
    stub_path = _write_stub(tmp_path, "discardable-concept", triaged="discardable")

    discover_gaps(session, tmp_path)

    rows = (
        session.execute(select(Gap).where(Gap.note_id == "discardable-concept"))
        .scalars()
        .all()
    )
    assert rows == []
    assert not stub_path.exists()


def test_tombstone_preserves_keep_marked_stubs_with_no_refs(
    monkeypatch, session, tmp_path
):
    """A 'keep' stub with no refs is NOT tombstoned — only discardable is."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    session.add(
        Gap(
            term="kept-concept",
            note_id="kept-concept",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()
    stub_path = _write_stub(tmp_path, "kept-concept", triaged="keep")

    discover_gaps(session, tmp_path)

    rows = (
        session.execute(select(Gap).where(Gap.note_id == "kept-concept"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert stub_path.exists()


def test_tombstone_preserves_unmarked_stubs_with_no_refs(
    monkeypatch, session, tmp_path
):
    """A stub without any triage marker is NOT tombstoned."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    session.add(
        Gap(
            term="orphan-concept",
            note_id="orphan-concept",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()
    stub_path = _write_stub(tmp_path, "orphan-concept", triaged=None)

    discover_gaps(session, tmp_path)

    rows = (
        session.execute(select(Gap).where(Gap.note_id == "orphan-concept"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert stub_path.exists()


def test_tombstone_preserves_gap_when_refs_still_present(
    monkeypatch, session, tmp_path
):
    """Even with triaged: discardable, a gap with active source links is
    NOT tombstoned in the same cycle — Phase A rewrites first, Phase B
    only fires once references have been cleared (next cycle)."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    session.add(
        Gap(
            term="active-discardable",
            note_id="active-discardable",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()
    stub_path = _write_stub(tmp_path, "active-discardable", triaged="discardable")
    # Live source link.
    src_body = (
        "---\nid: src\ntitle: Src\ntype: atom\n---\n\n"
        "We use [[Active Discardable]] often.\n"
    )
    _write_source(tmp_path, "src", src_body)
    src = _make_note(session, "src", title="Src")
    _add_body_link(session, src_fk=src.id, target_id="active-discardable")

    discover_gaps(session, tmp_path)

    # Source got rewritten (Phase A) but Gap row + stub still exist
    # because the slug was in slug_refs this cycle.
    rows = (
        session.execute(select(Gap).where(Gap.note_id == "active-discardable"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert stub_path.exists()


def test_tombstone_handles_missing_stub_file(monkeypatch, session, tmp_path):
    """If the stub file is already gone but the Gap row remains (data drift),
    is_discardable returns False so we leave the orphan row alone."""
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")
    session.add(
        Gap(
            term="ghost",
            note_id="ghost",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()
    # No stub written — simulates a stale Gap row whose stub was manually deleted.

    discover_gaps(session, tmp_path)

    # Without a discardable stub, we don't dare tombstone — leave it.
    rows = session.execute(select(Gap).where(Gap.note_id == "ghost")).scalars().all()
    assert len(rows) == 1


def _embed_client() -> AsyncMock:
    client = AsyncMock()
    # Reconciler calls embed_batch on each cycle; return correctly-shaped fake vectors.
    client.embed_batch.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    return client


async def _run_reconciler(session: Session, vault_root: Path) -> None:
    rec = Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=_embed_client(),
        vault_root=vault_root,
    )
    await rec.run()


@pytest.mark.asyncio
async def test_two_cycle_convergence(monkeypatch, session, tmp_path):
    """End-to-end proof that the design's two-cycle convergence terminates.

    Cycle 1: Reconciler ingests the source note + the discardable stub,
    populating Note/NoteLink rows. discover_gaps then rewrites the source
    body via Phase A; the stub still exists this cycle.

    Cycle 2: Reconciler re-ingests the rewritten source (hash changed), so
    links.extract finds no [[Throwaway]] and the NoteLink row is deleted.
    discover_gaps then sees no slug refs and tombstones the Gap row + stub
    via Phase B.
    """
    monkeypatch.setenv("KNOWLEDGE_GAPS_REWRITE_DISCARDABLE", "1")

    # Vault: one source note with a wikilink to a discardable stub.
    src_path = _write_source(
        tmp_path,
        "src",
        (
            "---\nid: src\ntitle: Src\ntype: atom\n---\n\n"
            "We use [[Throwaway]] sometimes.\n"
        ),
    )
    stub_path = _write_stub(tmp_path, "throwaway", triaged="discardable")

    # Pre-existing Gap row, modelling reality: discover_gaps would have
    # inserted this on an earlier cycle (before the user marked the stub
    # discardable). Phase A short-circuits Gap insertion when the stub is
    # already discardable, so without this seed Phase B has nothing to
    # iterate over and the stub never gets unlinked.
    session.add(
        Gap(
            term="throwaway",
            note_id="throwaway",
            pipeline_version=GAPS_PIPELINE_VERSION,
            state="discovered",
        )
    )
    session.commit()

    # Reconciler #1: ingest source, populate Note + NoteLink (and the
    # discardable stub itself as a type:gap Note row).
    await _run_reconciler(session, tmp_path)

    # discover_gaps #1: Phase A rewrites the source body in-place. The
    # stub still exists (write_stub was skipped for this slug).
    discover_gaps(session, tmp_path)
    rewritten = src_path.read_text()
    assert "[[Throwaway]]" not in rewritten
    assert "We use Throwaway sometimes." in rewritten
    assert stub_path.exists()

    # Reconciler #2: source hash changed → re-ingest → links.extract
    # returns no Throwaway → NoteLink row for that target is deleted.
    await _run_reconciler(session, tmp_path)

    # discover_gaps #2: slug_refs no longer contains 'throwaway' → Phase B
    # tombstones the Gap row + stub.
    discover_gaps(session, tmp_path)

    rows = (
        session.execute(select(Gap).where(Gap.note_id == "throwaway")).scalars().all()
    )
    assert rows == []
    assert not stub_path.exists()
