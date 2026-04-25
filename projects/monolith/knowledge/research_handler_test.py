"""Tests for the knowledge.research-gaps scheduled-job handler.

All three model tiers are mocked; the contract under test is the state
machine -- which transitions happen for which validator outcomes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from knowledge.models import Gap
from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_handler import RESEARCH_BATCH_SIZE, research_gaps_handler
from knowledge.research_validator import ValidatedClaim, ValidatedResearch


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


@pytest.fixture
def seed_classified_external_gaps(session):
    def _seed(n: int) -> list[str]:
        slugs = []
        for i in range(n):
            slug = f"term-{i}"
            with session.begin_nested():
                session.add(
                    Gap(
                        term=slug,
                        note_id=slug,
                        gap_class="external",
                        state="classified",
                        pipeline_version="test",
                    )
                )
            slugs.append(slug)
        session.commit()
        return slugs

    return _seed


@pytest.mark.asyncio
async def test_handler_picks_up_to_batch_size_external_classified_gaps(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(RESEARCH_BATCH_SIZE + 2)

    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_sources = [
        SourceEntry(tool="web_fetch", url="u", content_hash="x", fetched_at="t")
    ]
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="supported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, fake_sources)),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    rows = session.execute(select(Gap)).scalars().all()
    committed = [g for g in rows if g.state == "committed"]
    classified = [g for g in rows if g.state == "classified"]
    assert len(committed) == RESEARCH_BATCH_SIZE
    assert len(classified) == 2  # the leftover that didn't get picked up


@pytest.mark.asyncio
async def test_handler_writes_inbox_research_file_on_supported_claim(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="supported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    assert (tmp_path / "_inbox" / "research" / "term-0.md").is_file()


@pytest.mark.asyncio
async def test_handler_quarantines_and_bumps_attempts_on_all_unsupported(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="unsupported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 1
    assert gap.state == "classified"  # back for retry
    assert (tmp_path / "_failed_research" / "term-0-1.md").is_file()


@pytest.mark.asyncio
async def test_handler_parks_after_three_consecutive_failures(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="unsupported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        for _ in range(3):
            await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 3
    assert gap.state == "parked"
    assert (tmp_path / "_failed_research" / "term-0-1.md").is_file()
    assert (tmp_path / "_failed_research" / "term-0-2.md").is_file()
    assert (tmp_path / "_failed_research" / "term-0-3.md").is_file()


@pytest.mark.asyncio
async def test_handler_does_not_bump_attempts_on_qwen_infra_error(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(1)

    with patch(
        "knowledge.research_handler._run_research",
        AsyncMock(side_effect=ConnectionError("llama-cpp down")),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 0
    assert gap.state == "classified"


@pytest.mark.asyncio
async def test_handler_does_not_bump_attempts_on_validator_timeout(
    session, tmp_path, seed_classified_external_gaps
):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(timed_out=True)

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 0
    assert gap.state == "classified"


@pytest.mark.asyncio
async def test_handler_skips_non_external_gaps(
    session, tmp_path, seed_classified_external_gaps
):
    """Internal/hybrid gaps are never selected, even if state='classified'."""
    with session.begin_nested():
        session.add(
            Gap(
                term="i",
                note_id="i",
                gap_class="internal",
                state="classified",
                pipeline_version="t",
            )
        )
    with session.begin_nested():
        session.add(
            Gap(
                term="h",
                note_id="h",
                gap_class="hybrid",
                state="classified",
                pipeline_version="t",
            )
        )
    session.commit()

    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="supported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    rows = session.execute(select(Gap)).scalars().all()
    for g in rows:
        assert g.state == "classified", (
            f"non-external gap {g.term} ({g.gap_class}) was wrongly picked up"
        )


@pytest.mark.asyncio
async def test_handler_recovers_stuck_researching_rows_at_tick_start(session, tmp_path):
    """A row stuck at state='researching' (prev tick crashed mid-flight) is
    swept back to 'classified' so it becomes eligible for re-pickup."""
    with session.begin_nested():
        session.add(
            Gap(
                term="stuck",
                note_id="stuck",
                gap_class="external",
                state="researching",
                pipeline_version="test",
            )
        )
    session.commit()

    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(
        claims=[ValidatedClaim(text="c", verdict="supported", reason="r")]
    )

    with (
        patch(
            "knowledge.research_handler._run_research",
            AsyncMock(return_value=(fake_note, [])),
        ),
        patch(
            "knowledge.research_handler.validate_research",
            AsyncMock(return_value=fake_validated),
        ),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    # Recovery sweep returned it to 'classified', then the same tick re-picked
    # it up and ran it through to 'committed' (supported claim).
    gap = session.execute(select(Gap).where(Gap.term == "stuck")).scalar_one()
    assert gap.state == "committed"


@pytest.mark.asyncio
async def test_handler_skips_when_lock_lost_to_concurrent_writer(
    session, tmp_path, seed_classified_external_gaps
):
    """If another writer flips state out from under the lock UPDATE
    (rowcount==0), the handler skips the gap silently without invoking
    Qwen or Sonnet."""
    seed_classified_external_gaps(1)

    # Simulate the race: between the SELECT (which sees state='classified')
    # and the lock UPDATE (WHERE id=? AND state='classified'), another
    # writer flips state to 'researching'. Patch the lock UPDATE seam by
    # wrapping session.execute -- when we see an UPDATE keyed on the row's
    # id, do the race-flip first, then let the original UPDATE run (it
    # will now see no matching rows -> rowcount==0 -> handler skips).
    real_execute = session.execute
    race_armed = {"done": False}

    def racing_execute(stmt, *args, **kwargs):
        compiled = str(stmt).upper()
        # Distinguish the per-row lock UPDATE from the recovery sweep:
        # the lock UPDATE is keyed on gaps.id and sets state='researching';
        # the recovery sweep is keyed on state='researching' and sets
        # state='classified'. The lock UPDATE binds parameters for the id.
        is_lock_update = (
            "UPDATE" in compiled and "GAPS.ID" in compiled and not race_armed["done"]
        )
        if is_lock_update:
            race_armed["done"] = True
            # Pre-flip: directly mutate the row to 'researching' so the
            # subsequent UPDATE's WHERE state='classified' matches nothing.
            real_execute(
                Gap.__table__.update()
                .where(Gap.term == "term-0")
                .values(state="researching")
            )
            session.commit()
        return real_execute(stmt, *args, **kwargs)

    qwen_mock = AsyncMock(
        return_value=(ResearchNote(summary="s", claims=[Claim(text="c")]), [])
    )
    validator_mock = AsyncMock(
        return_value=ValidatedResearch(
            claims=[ValidatedClaim(text="c", verdict="supported", reason="r")]
        )
    )

    with (
        patch.object(session, "execute", side_effect=racing_execute),
        patch("knowledge.research_handler._run_research", qwen_mock),
        patch("knowledge.research_handler.validate_research", validator_mock),
    ):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    # The lock UPDATE saw rowcount==0 and skipped -- Qwen/Sonnet never ran.
    assert qwen_mock.await_count == 0
    assert validator_mock.await_count == 0
