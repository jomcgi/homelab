"""Unit tests for knowledge.gaps — discover/classify/review/answer lifecycle.

Uses the same in-memory SQLite + schema-strip fixture pattern as
``gap_model_test.py`` so table DDL works without a real Postgres.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.gaps import (
    GAPS_PIPELINE_VERSION,
    answer_gap,
    classify_gaps,
    discover_gaps,
    list_review_queue,
)
from knowledge.models import Gap, Note, NoteLink


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


# ---------------------------------------------------------------------------
# discover_gaps
# ---------------------------------------------------------------------------


def test_discover_gaps_finds_unresolved_wikilink(session):
    src = _make_note(session, "source-note", title="Source Note")
    _add_body_link(session, src_fk=src.id, target_id="missing-concept")

    created = discover_gaps(session)

    assert created == 1
    gaps = session.execute(select(Gap)).scalars().all()
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.term == "missing-concept"
    assert gap.context == "Source Note"
    assert gap.source_note_fk == src.id
    assert gap.state == "discovered"
    assert gap.gap_class is None
    assert gap.pipeline_version == GAPS_PIPELINE_VERSION


def test_discover_gaps_skips_resolved_links(session):
    src = _make_note(session, "source-note", title="Source")
    _make_note(session, "target-note", title="Target")  # link target exists
    _add_body_link(session, src_fk=src.id, target_id="target-note")

    created = discover_gaps(session)

    assert created == 0
    assert session.execute(select(Gap)).scalars().all() == []


def test_discover_gaps_is_idempotent(session):
    src = _make_note(session, "src", title="Src")
    _add_body_link(session, src_fk=src.id, target_id="missing")

    first = discover_gaps(session)
    second = discover_gaps(session)

    assert first == 1
    assert second == 0
    assert len(session.execute(select(Gap)).scalars().all()) == 1


def test_discover_gaps_ignores_frontmatter_edges(session):
    """kind='edge' rows are typed assertions, not wikilink gaps."""
    src = _make_note(session, "src", title="Src")
    session.add(
        NoteLink(
            src_note_fk=src.id,
            target_id="derived-target",
            target_title=None,
            kind="edge",
            edge_type="derives_from",
        )
    )
    session.commit()

    assert discover_gaps(session) == 0


def test_discover_gaps_captures_source_title_as_context(session):
    src = _make_note(session, "src-slug", title="Kubernetes Networking")
    _add_body_link(session, src_fk=src.id, target_id="cilium")

    discover_gaps(session)

    gap = session.execute(select(Gap).where(Gap.term == "cilium")).scalar_one()
    assert gap.context == "Kubernetes Networking"


# ---------------------------------------------------------------------------
# classify_gaps
# ---------------------------------------------------------------------------


def test_classify_gaps_default_is_internal_in_review(session):
    src = _make_note(session, "s", title="S")
    _add_body_link(session, src_fk=src.id, target_id="t1")
    _add_body_link(session, src_fk=src.id, target_id="t2")
    discover_gaps(session)

    classified = classify_gaps(session)  # classifier=None → internal

    assert classified == 2
    for gap in session.execute(select(Gap)).scalars().all():
        assert gap.gap_class == "internal"
        assert gap.state == "in_review"
        assert gap.classified_at is not None


def test_classify_gaps_routes_by_class(session):
    src = _make_note(session, "s", title="S")
    for target in ("ext", "int", "hyb", "park"):
        _add_body_link(session, src_fk=src.id, target_id=target)
    discover_gaps(session)

    mapping = {
        "ext": "external",
        "int": "internal",
        "hyb": "hybrid",
        "park": "parked",
    }

    def classifier(term: str, _context: str) -> str:
        return mapping[term]

    assert classify_gaps(session, classifier=classifier) == 4

    rows = {
        g.term: (g.gap_class, g.state)
        for g in session.execute(select(Gap)).scalars().all()
    }
    assert rows["ext"] == ("external", "classified")
    assert rows["int"] == ("internal", "in_review")
    assert rows["hyb"] == ("hybrid", "in_review")
    assert rows["park"] == ("parked", "classified")


def test_classify_gaps_skips_already_classified(session):
    src = _make_note(session, "s", title="S")
    _add_body_link(session, src_fk=src.id, target_id="x")
    discover_gaps(session)

    assert classify_gaps(session) == 1
    # Second call finds nothing in state='discovered'.
    assert classify_gaps(session) == 0


# ---------------------------------------------------------------------------
# list_review_queue
# ---------------------------------------------------------------------------


def test_list_review_queue_only_returns_internal_hybrid_in_review(session):
    src = _make_note(session, "s", title="S")
    # Manually construct gaps in varied states so we can assert filtering.
    now = datetime.now(timezone.utc)
    gaps = [
        Gap(
            term="a-internal",
            context="",
            source_note_fk=src.id,
            gap_class="internal",
            state="in_review",
            pipeline_version=GAPS_PIPELINE_VERSION,
            created_at=now - timedelta(seconds=30),
        ),
        Gap(
            term="b-hybrid",
            context="",
            source_note_fk=src.id,
            gap_class="hybrid",
            state="in_review",
            pipeline_version=GAPS_PIPELINE_VERSION,
            created_at=now - timedelta(seconds=20),
        ),
        Gap(
            term="c-external",
            context="",
            source_note_fk=src.id,
            gap_class="external",
            state="classified",
            pipeline_version=GAPS_PIPELINE_VERSION,
            created_at=now - timedelta(seconds=10),
        ),
        Gap(
            term="d-internal-discovered",
            context="",
            source_note_fk=src.id,
            gap_class="internal",
            state="discovered",
            pipeline_version=GAPS_PIPELINE_VERSION,
            created_at=now,
        ),
    ]
    session.add_all(gaps)
    session.commit()

    queue = list_review_queue(session)

    terms = [row["term"] for row in queue]
    assert terms == ["a-internal", "b-hybrid"]  # FIFO, only in_review+internal/hybrid
    assert queue[0]["gap_class"] == "internal"
    assert queue[1]["gap_class"] == "hybrid"


def test_list_review_queue_empty(session):
    assert list_review_queue(session) == []


# ---------------------------------------------------------------------------
# answer_gap
# ---------------------------------------------------------------------------


def _seed_reviewable_gap(session: Session, *, term: str = "Linkerd mTLS") -> int:
    src = _make_note(session, "src", title="Src")
    gap = Gap(
        term=term,
        context="networking note",
        source_note_fk=src.id,
        gap_class="internal",
        state="in_review",
        pipeline_version=GAPS_PIPELINE_VERSION,
    )
    session.add(gap)
    session.commit()
    session.refresh(gap)
    return gap.id


def test_answer_gap_writes_file_and_commits(session, tmp_path):
    gap_id = _seed_reviewable_gap(session, term="Linkerd mTLS")

    result = answer_gap(
        session,
        gap_id,
        "Linkerd enables mTLS via per-pod sidecar proxies on port 4143.",
        tmp_path,
    )

    assert result["gap_id"] == gap_id
    assert result["note_id"] == "linkerd-mtls"
    assert result["path"] == "_processed/linkerd-mtls.md"

    file_path = tmp_path / "_processed" / "linkerd-mtls.md"
    assert file_path.is_file()
    content = file_path.read_text()
    assert content.startswith("---\n")
    # Parse the frontmatter so we don't couple to yaml.dump's quoting style.
    _, fm_block, body = content.split("---\n", 2)
    fm = yaml.safe_load(fm_block)
    assert fm == {
        "id": "linkerd-mtls",
        "title": "Linkerd mTLS",
        "type": "atom",
        "source_tier": "personal",
    }
    assert "Linkerd enables mTLS" in body

    gap = session.get(Gap, gap_id)
    assert gap.state == "committed"
    assert gap.answer.startswith("Linkerd enables mTLS")
    assert gap.resolved_at is not None


def test_answer_gap_handles_filename_collisions(session, tmp_path):
    gap_id = _seed_reviewable_gap(session, term="Collision")

    # Pre-create the unadorned file to force a -1 suffix.
    processed = tmp_path / "_processed"
    processed.mkdir(parents=True)
    (processed / "collision.md").write_text("existing")

    result = answer_gap(session, gap_id, "the answer", tmp_path)

    assert result["note_id"] == "collision-1"
    assert result["path"] == "_processed/collision-1.md"
    assert (processed / "collision-1.md").is_file()
    # Original file is untouched.
    assert (processed / "collision.md").read_text() == "existing"


def test_answer_gap_rejects_unknown_id(session, tmp_path):
    with pytest.raises(ValueError, match="Gap not found"):
        answer_gap(session, gap_id=9999, answer="x", vault_root=tmp_path)


def test_answer_gap_rejects_wrong_state(session, tmp_path):
    src = _make_note(session, "src", title="Src")
    gap = Gap(
        term="still-discovered",
        context="",
        source_note_fk=src.id,
        state="discovered",
        pipeline_version=GAPS_PIPELINE_VERSION,
    )
    session.add(gap)
    session.commit()
    session.refresh(gap)

    with pytest.raises(ValueError, match="expected 'in_review'"):
        answer_gap(session, gap.id, "x", tmp_path)


def test_answer_gap_handles_special_chars_in_term(session, tmp_path):
    """YAML frontmatter must round-trip arbitrary terms (C1 regression)."""
    term = r'regex \d+ "quoted" stuff'
    gap_id = _seed_reviewable_gap(session, term=term)

    result = answer_gap(session, gap_id, "some answer body", tmp_path)

    file_path = tmp_path / result["path"]
    content = file_path.read_text()
    # Split on the frontmatter fences and parse with a real YAML loader —
    # this would fail against the old hand-rolled escape, which emitted
    # title: "regex \d+ ..." (invalid escape sequence in double-quoted YAML).
    _, fm_block, _ = content.split("---\n", 2)
    fm = yaml.safe_load(fm_block)
    assert fm["title"] == term


def test_classify_gaps_rejects_invalid_classifier_output(session, caplog):
    """Out-of-range classifier outputs fall back to internal (I2 regression)."""
    src = _make_note(session, "s", title="S")
    _add_body_link(session, src_fk=src.id, target_id="good")
    _add_body_link(session, src_fk=src.id, target_id="bad")
    discover_gaps(session)

    def classifier(term: str, _context: str) -> str:
        return "external" if term == "good" else "bogus"

    with caplog.at_level(logging.WARNING, logger="knowledge.gaps"):
        assert classify_gaps(session, classifier=classifier) == 2

    rows = {
        g.term: (g.gap_class, g.state)
        for g in session.execute(select(Gap)).scalars().all()
    }
    assert rows["good"] == ("external", "classified")
    assert rows["bad"] == ("internal", "in_review")
    assert any(
        "classifier returned invalid class 'bogus'" in record.getMessage()
        for record in caplog.records
    )


def test_answer_gap_rejects_frontmatter_terminator_in_answer(session, tmp_path):
    """Answers containing '---' on their own line must be rejected (M4)."""
    gap_id = _seed_reviewable_gap(session, term="some-term")

    with pytest.raises(ValueError, match="frontmatter terminator"):
        answer_gap(session, gap_id, "foo\n---\nbar", tmp_path)

    gap = session.get(Gap, gap_id)
    assert gap.state == "in_review"
    assert gap.answer is None
    assert gap.resolved_at is None
