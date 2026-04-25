"""Scheduled-job handler for knowledge.research-gaps.

Every tick: pulls up to RESEARCH_BATCH_SIZE external+classified gaps,
runs Qwen+Sonnet, transitions state per design's state machine.
Infra failures (llama-cpp down, Sonnet timeout) revert state without
burning attempts. Validator rejection (all-unsupported) bumps attempts;
>=3 attempts -> parked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from knowledge.models import Gap
from knowledge.research_agent import (
    QWEN_MODEL_ID,
    ResearchDeps,
    ResearchNote,
    SourceEntry,
    create_research_agent,
    derive_sources_bundle,
)
from knowledge.research_validator import (
    validate_research,
)
from knowledge.research_writer import quarantine, write_research_raw

logger = logging.getLogger(__name__)

RESEARCH_BATCH_SIZE = 3
RESEARCH_PARK_THRESHOLD = 3
SONNET_MODEL_ID = "sonnet-4-6"


async def research_gaps_handler(
    *,
    session: Session,
    vault_root: Path,
) -> None:
    """Run one tick of the external research pipeline."""
    # Recovery sweep: if the previous tick crashed mid-flight (between the
    # 'researching' lock and any terminal state assignment), the row would
    # be stuck forever -- the SELECT below filters state='classified', so
    # nothing would ever pick it back up. Sweep stuck rows back to
    # 'classified' before each tick. Safe under the single-worker scheduler
    # model (knowledge.research-gaps is the only writer of these states).
    stuck = session.execute(
        Gap.__table__.update()
        .where(Gap.state == "researching")
        .values(state="classified")
    )
    if stuck.rowcount:
        logger.warning(
            "knowledge.research-gaps: recovered %d stuck 'researching' rows to "
            "'classified'",
            stuck.rowcount,
        )
    session.commit()

    candidates = (
        session.execute(
            select(Gap)
            .where(Gap.gap_class == "external", Gap.state == "classified")
            .order_by(Gap.id)
            .limit(RESEARCH_BATCH_SIZE)
        )
        .scalars()
        .all()
    )

    if not candidates:
        logger.info("knowledge.research-gaps: no candidates")
        return

    for gap in candidates:
        # Defense-in-depth privacy guard: even though the SELECT filtered,
        # re-assert before each Qwen call. Cheap, prevents future misroutes.
        if gap.gap_class != "external":
            logger.warning(
                "knowledge.research-gaps: skipping non-external gap %s", gap.term
            )
            continue

        # Race-safe lock: only proceed if state still 'classified'.
        result = session.execute(
            Gap.__table__.update()
            .where(Gap.id == gap.id, Gap.state == "classified")
            .values(state="researching")
        )
        session.commit()
        # NB: gap.state in-memory is now stale (still 'classified'). The Core
        # UPDATE bypassed the ORM identity map. Don't read gap.state below
        # this point -- always assign explicitly.
        if result.rowcount == 0:
            logger.info("knowledge.research-gaps: race lost for %s", gap.term)
            continue

        await _process_one(session=session, gap=gap, vault_root=vault_root)


async def _process_one(*, session: Session, gap: Gap, vault_root: Path) -> None:
    # gap.note_id is the slug used for both _inbox/research/<slug>.md and
    # _failed_research/<slug>-<N>.md. Schema permits NULL, but a classified
    # external gap reaching this point must have one (the reconciler
    # always links a stub note before classification). Assert to fail
    # loudly rather than write files literally named 'None.md'.
    assert gap.note_id is not None, f"gap {gap.id} ({gap.term}) has no note_id"

    researched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Run Qwen.
    try:
        note, sources = await _run_research(
            session=session, gap=gap, vault_root=vault_root
        )
    except Exception:
        logger.exception(
            "knowledge.research-gaps: Qwen failure on %s; reverting state", gap.term
        )
        gap.state = "classified"
        session.commit()
        return

    # 2. Run Sonnet.
    try:
        validated = await validate_research(note=note, sources=sources)
    except Exception:
        logger.exception(
            "knowledge.research-gaps: validator failure on %s; reverting state",
            gap.term,
        )
        gap.state = "classified"
        session.commit()
        return

    if validated.timed_out or validated.parse_error:
        logger.warning(
            "knowledge.research-gaps: validator infra issue on %s "
            "(timed_out=%s parse_error=%s); reverting state",
            gap.term,
            validated.timed_out,
            validated.parse_error,
        )
        gap.state = "classified"
        session.commit()
        return

    # 3. Branch on verdicts.
    if validated.all_unsupported:
        attempt = gap.research_attempts + 1
        try:
            quarantine(
                vault_root=vault_root,
                slug=gap.note_id,
                attempt=attempt,
                draft_note=note,
                validated=validated,
                sources=sources,
                qwen_model=QWEN_MODEL_ID,
                sonnet_model=SONNET_MODEL_ID,
                researched_at=researched_at,
            )
        except Exception:
            logger.exception(
                "knowledge.research-gaps: quarantine write failed for %s", gap.term
            )
            gap.state = "classified"
            session.commit()
            return

        gap.research_attempts = attempt
        gap.state = "parked" if attempt >= RESEARCH_PARK_THRESHOLD else "classified"
        session.commit()
        logger.info(
            "knowledge.research-gaps: rejected %s (attempt=%d, state=%s)",
            gap.term,
            attempt,
            gap.state,
        )
        return

    # 4. Supported claims path.
    supported = [c for c in validated.claims if c.verdict == "supported"]
    dropped = len(validated.claims) - len(supported)

    try:
        write_research_raw(
            vault_root=vault_root,
            slug=gap.note_id,
            title=gap.term,
            summary=note.summary,
            supported_claims=supported,
            sources=sources,
            claims_dropped=dropped,
            qwen_model=QWEN_MODEL_ID,
            sonnet_model=SONNET_MODEL_ID,
            researched_at=researched_at,
        )
    except Exception:
        logger.exception(
            "knowledge.research-gaps: raw write failed for %s; reverting state",
            gap.term,
        )
        gap.state = "classified"
        session.commit()
        return

    gap.state = "committed"
    session.commit()
    logger.info(
        "knowledge.research-gaps: committed %s (supported=%d, dropped=%d)",
        gap.term,
        len(supported),
        dropped,
    )


async def _run_research(
    *,
    session: Session,
    gap: Gap,
    vault_root: Path,
) -> tuple[ResearchNote, list[SourceEntry]]:
    """Run the Pydantic AI agent; return (note, sources_bundle).

    Pulled out as a separate function so research_handler_test.py can mock
    it without standing up a real Pydantic AI loop.
    """
    agent = create_research_agent()
    deps = ResearchDeps(session=session, vault_root=vault_root)
    user_prompt = (
        f"Research the term: {gap.term!r}.\n"
        f"Context: this term appears as an unresolved [[wikilink]] in the user's "
        f"vault. Use search_knowledge first, then web_search + web_fetch as needed."
    )
    result = await agent.run(user_prompt, deps=deps)
    sources = derive_sources_bundle(result.all_messages())
    return result.output, sources
