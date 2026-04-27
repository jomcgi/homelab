"""End-to-end integration test for the single-agent research pipeline.

Mocks **only** the LLM boundary (``run_research``); real DB state, real
vault writes via ``research_writer``, real handler logic. Each test
asserts on both the resulting DB row AND the bytes the writer emitted
to ``tmp_path``.

Per-disposition routing is exhaustively covered in
``research_handler_test.py``; this suite's value is that frontmatter and
body bytes from the actual writer line up with the handler's intent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.models import Gap
from knowledge.research_agent import (
    Claim,
    ResearchNote,
    ResearchResult,
    SourceEntry,
)
from knowledge.research_handler import research_gaps_handler


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Strip the ``knowledge`` schema for the in-memory SQLite engine
    # (SQLite has no schemas). Restored after the test so other modules
    # importing the metadata still see the production-shaped tables.
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


def _make_gap(
    session: Session,
    *,
    term: str = "Linkerd mTLS",
    note_id: str = "linkerd-mtls",
    research_attempts: int = 0,
) -> Gap:
    gap = Gap(
        term=term,
        note_id=note_id,
        gap_class="external",
        state="classified",
        research_attempts=research_attempts,
        pipeline_version="test",
    )
    session.add(gap)
    session.commit()
    session.refresh(gap)
    return gap


def _read_frontmatter(path: Path) -> dict:
    """Split the frontmatter block out of a writer-emitted markdown file."""
    text = path.read_text()
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


@pytest.mark.asyncio
async def test_e2e_research_disposition_writes_raw_and_marks_committed(
    session: Session, tmp_path: Path
) -> None:
    """research + supported claims: raw lands in _inbox/research, gap committed."""
    gap = _make_gap(session)

    note = ResearchNote(
        summary="Linkerd terminates mTLS at its sidecar proxy.",
        claims=[
            Claim(
                text="Linkerd issues short-lived mTLS certs to each proxy.",
                source_refs=("https://linkerd.io/2.13/features/mtls/",),
            ),
            Claim(
                text="Identity is bound to the workload's ServiceAccount.",
                source_refs=("https://linkerd.io/2.13/features/mtls/",),
            ),
        ],
    )
    result = ResearchResult(
        disposition="research",
        reason="publicly-researchable concept",
        note=note,
        raw_claims=tuple(note.claims),
        sources=(
            SourceEntry(tool="WebFetch", ref="https://linkerd.io/2.13/features/mtls/"),
        ),
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=result),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.state == "committed"
    assert gap.research_attempts == 0  # success burns no attempt
    assert gap.gap_class == "external"  # unchanged

    raw_path = tmp_path / "_inbox" / "research" / "linkerd-mtls.md"
    assert raw_path.is_file()
    assert not (tmp_path / "_failed_research").exists()

    fm = _read_frontmatter(raw_path)
    assert fm["type"] == "research"
    assert fm["id"] == "linkerd-mtls"
    assert fm["agent_model"] == "sonnet"
    assert fm["pipeline_version"] == "research-pipeline@v2"
    assert fm["claims_supported"] == 2
    assert fm["sources"] == [
        {"tool": "WebFetch", "ref": "https://linkerd.io/2.13/features/mtls/"}
    ]

    body = raw_path.read_text()
    assert "Linkerd terminates mTLS at its sidecar proxy." in body
    assert "_[https://linkerd.io/2.13/features/mtls/]_" in body


@pytest.mark.asyncio
async def test_e2e_research_disposition_empty_claims_quarantines_and_bumps(
    session: Session, tmp_path: Path
) -> None:
    """research + empty post-filter claims: draft quarantined, attempts bumped."""
    gap = _make_gap(session)

    pre_filter = (
        Claim(
            text="Linkerd uses some kind of cert.",
            source_refs=("https://hallucinated.example/never-fetched",),
        ),
        Claim(
            text="Another claim with refs the agent didn't actually retrieve.",
            source_refs=("https://also-fake.example",),
        ),
    )
    result = ResearchResult(
        disposition="research",
        reason="publicly-researchable concept",
        note=ResearchNote(
            summary="Linkerd is a service mesh that does mTLS.",
            claims=[],  # post-filter empty -> quarantine
        ),
        raw_claims=pre_filter,
        sources=(SourceEntry(tool="WebSearch", ref="linkerd mtls"),),
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=result),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.research_attempts == 1
    assert gap.state == "classified"  # below RESEARCH_PARK_THRESHOLD
    assert gap.gap_class == "external"

    quarantine_path = tmp_path / "_failed_research" / "linkerd-mtls-1.md"
    assert quarantine_path.is_file()
    assert not (tmp_path / "_inbox" / "research" / "linkerd-mtls.md").exists()

    fm = _read_frontmatter(quarantine_path)
    assert fm["type"] == "failed_research"
    assert fm["id"] == "linkerd-mtls-1"
    assert fm["attempt"] == 1
    assert fm["agent_model"] == "sonnet"
    assert fm["pipeline_version"] == "research-pipeline@v2"
    assert fm["claims_emitted"] == 2

    body = quarantine_path.read_text()
    assert "## Claims (pre-filter)" in body
    assert "Linkerd uses some kind of cert." in body
    assert "_[https://hallucinated.example/never-fetched]_" in body


@pytest.mark.asyncio
async def test_e2e_personal_disposition_flips_gap_class_no_vault_file(
    session: Session, tmp_path: Path
) -> None:
    """personal: gap_class -> internal, no vault files written."""
    gap = _make_gap(session, term="my-private-project", note_id="my-private-project")

    result = ResearchResult(
        disposition="personal",
        reason="term appears only in journal entries; no public referent",
        sources=(SourceEntry(tool="Glob", ref="glob:**/journal/*.md"),),
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=result),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.gap_class == "internal"
    assert gap.state == "classified"
    assert gap.research_attempts == 0  # personal does NOT burn an attempt

    assert not (tmp_path / "_inbox").exists()
    assert not (tmp_path / "_failed_research").exists()


@pytest.mark.asyncio
async def test_e2e_discard_disposition_parks_gap_no_vault_file(
    session: Session, tmp_path: Path
) -> None:
    """discard: gap parked, no vault files written."""
    gap = _make_gap(session, term="fooo", note_id="fooo")

    result = ResearchResult(
        disposition="discard",
        reason="looks like a typo of 'food'",
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=result),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.gap_class == "parked"
    assert gap.state == "parked"
    assert gap.research_attempts == 0  # discard does NOT burn an attempt

    assert not (tmp_path / "_inbox").exists()
    assert not (tmp_path / "_failed_research").exists()
