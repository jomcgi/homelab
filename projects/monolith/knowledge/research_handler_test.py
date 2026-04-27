"""Tests for the research-gaps scheduled-job handler.

Mocks ``run_research`` directly (the single boundary). Exercises:
  - happy path (research disposition with surviving claims)
  - infra failure (RuntimeError from run_research)
  - personal disposition (gap_class flip, no file)
  - discard disposition (gap parked, no file)
  - all-claims-dropped quarantine (research disposition, empty post-filter claims)
  - park-at-threshold after repeated quarantines
  - race-lost (state already changed before lock)
  - stuck-row recovery sweep
  - privacy guard (non-external gap skipped after lock)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.models import Gap
from knowledge.research_agent import (
    Claim,
    ResearchNote,
    ResearchResult,
    SourceEntry,
)
from knowledge.research_handler import (
    RESEARCH_PARK_THRESHOLD,
    research_gaps_handler,
)


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
    gap_class: str | None = "external",
    state: str = "classified",
    note_id: str | None = "linkerd-mtls",
    research_attempts: int = 0,
) -> Gap:
    gap = Gap(
        term=term,
        gap_class=gap_class,
        state=state,
        note_id=note_id,
        research_attempts=research_attempts,
        pipeline_version="test",
    )
    session.add(gap)
    session.commit()
    session.refresh(gap)
    return gap


def _research_result_with_claims() -> ResearchResult:
    note = ResearchNote(
        summary="Linkerd uses mTLS for service-to-service auth.",
        claims=[
            Claim(
                text="Linkerd terminates mTLS at the proxy.",
                source_refs=("https://linkerd.io/2.13/features/mtls/",),
            )
        ],
    )
    return ResearchResult(
        disposition="research",
        reason="publicly-researchable concept",
        note=note,
        raw_claims=(note.claims[0],),
        sources=(
            SourceEntry(tool="WebFetch", ref="https://linkerd.io/2.13/features/mtls/"),
        ),
    )


def _research_result_all_dropped() -> ResearchResult:
    return ResearchResult(
        disposition="research",
        reason="publicly-researchable concept",
        note=ResearchNote(summary="x", claims=[]),
        raw_claims=(
            Claim(text="claim Sonnet emitted", source_refs=("https://hallucinated",)),
        ),
        sources=(SourceEntry(tool="WebSearch", ref="foo"),),
    )


@pytest.mark.asyncio
async def test_research_disposition_writes_raw_and_marks_committed(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session)

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=_research_result_with_claims()),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.state == "committed"
    assert gap.research_attempts == 0
    assert (tmp_path / "_inbox" / "research" / "linkerd-mtls.md").exists()
    assert not (tmp_path / "_failed_research").exists()


@pytest.mark.asyncio
async def test_personal_disposition_flips_gap_class_no_file(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session)

    personal = ResearchResult(
        disposition="personal",
        reason="term appears only in journal-style notes",
        sources=(SourceEntry(tool="Glob", ref="glob:**/*.md"),),
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=personal),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.gap_class == "internal"
    assert gap.state == "classified"
    assert gap.research_attempts == 0  # not bumped
    assert not (tmp_path / "_inbox").exists()
    assert not (tmp_path / "_failed_research").exists()


@pytest.mark.asyncio
async def test_discard_disposition_parks_gap_no_file(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session)

    discard = ResearchResult(
        disposition="discard",
        reason="looks like a typo of `food`",
    )

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=discard),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.gap_class == "parked"
    assert gap.state == "parked"
    assert gap.research_attempts == 0  # not bumped
    assert not (tmp_path / "_inbox").exists()
    assert not (tmp_path / "_failed_research").exists()


@pytest.mark.asyncio
async def test_all_claims_dropped_quarantines_and_bumps_attempts(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session)

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=_research_result_all_dropped()),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.research_attempts == 1
    assert gap.state == "classified"  # below threshold
    assert (tmp_path / "_failed_research" / "linkerd-mtls-1.md").exists()
    assert not (tmp_path / "_inbox" / "research" / "linkerd-mtls.md").exists()


@pytest.mark.asyncio
async def test_quarantine_at_threshold_parks_gap(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session, research_attempts=RESEARCH_PARK_THRESHOLD - 1)

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=_research_result_all_dropped()),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.research_attempts == RESEARCH_PARK_THRESHOLD
    assert gap.state == "parked"


@pytest.mark.asyncio
async def test_runtime_error_reverts_state_no_attempt_bump(
    session: Session, tmp_path: Path
) -> None:
    gap = _make_gap(session)

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(side_effect=RuntimeError("claude exit 1: boom")),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    assert gap.state == "classified"
    assert gap.research_attempts == 0  # infra failure does NOT burn an attempt
    assert not (tmp_path / "_inbox").exists()
    assert not (tmp_path / "_failed_research").exists()


@pytest.mark.asyncio
async def test_stuck_researching_rows_swept_to_classified(
    session: Session, tmp_path: Path
) -> None:
    """Rows left in 'researching' from a previous crashed tick get
    recovered to 'classified' before the SELECT picks candidates."""
    gap = _make_gap(session, state="researching")

    with patch(
        "knowledge.research_handler.run_research",
        AsyncMock(return_value=_research_result_with_claims()),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    session.refresh(gap)
    # Recovered to 'classified', then picked up, then committed.
    assert gap.state == "committed"


@pytest.mark.asyncio
async def test_race_lost_skips_gap(session: Session, tmp_path: Path) -> None:
    """If the SELECT returns no candidates because state was already
    moved out of 'classified' before the handler ran, run_research is
    never invoked."""
    gap = _make_gap(session)

    runner = AsyncMock(return_value=_research_result_with_claims())
    with patch("knowledge.research_handler.run_research", runner):
        # Move the gap out of 'classified' BEFORE the handler runs, so
        # the SELECT in the handler returns nothing. The recovery sweep
        # only catches 'researching'; 'in_review' is left alone.
        gap.state = "in_review"
        session.add(gap)
        session.commit()
        await research_gaps_handler(session=session, vault_root=tmp_path)

    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_external_gap_skipped_by_privacy_guard(
    session: Session, tmp_path: Path
) -> None:
    """Even if a 'classified' gap with non-external gap_class somehow
    reaches the loop (e.g. a future SELECT bug), the per-gap
    re-assertion skips it before any Sonnet call."""
    gap = _make_gap(session, gap_class="external", state="classified")

    runner = AsyncMock(return_value=_research_result_with_claims())
    with patch("knowledge.research_handler.run_research", runner):
        # Mutate gap_class out from under the SELECT, so the per-gap
        # re-assertion catches it.
        gap.gap_class = "internal"
        session.add(gap)
        session.commit()
        await research_gaps_handler(session=session, vault_root=tmp_path)

    runner.assert_not_awaited()
    session.refresh(gap)
    assert gap.gap_class == "internal"  # unchanged by handler


@pytest.mark.asyncio
async def test_no_candidates_logs_and_returns(session: Session, tmp_path: Path) -> None:
    runner = AsyncMock(return_value=_research_result_with_claims())
    with patch("knowledge.research_handler.run_research", runner):
        await research_gaps_handler(session=session, vault_root=tmp_path)
    runner.assert_not_awaited()
