"""Scheduled-job handler for knowledge.research-gaps.

Every tick: pulls up to RESEARCH_BATCH_SIZE external+classified gaps,
runs the Sonnet research agent (single subprocess that triages and
optionally researches), routes per disposition.

  - ``research`` + non-empty post-filter claims: write the research raw,
    state -> "committed".
  - ``research`` + empty post-filter claims (everything failed citation
    check): quarantine the draft, bump ``research_attempts``. Below
    threshold the stub is left in place so the next tick retries; at
    threshold the gap is parked and the stub is deleted.
  - ``personal``: gap_class flips to ``internal``, state stays
    ``classified``. Sonnet caught a mis-classification. The stub is
    deleted -- if the term reappears in another note, the gardener
    will queue a fresh stub for re-classification.
  - ``discard``: gap_class flips to ``parked``, state -> ``parked``.
    Sonnet decided this isn't worth researching at all. Stub deleted.
  - Infra failures (claude subprocess timeout / non-zero exit / parse
    error) revert state without burning a research attempt.

Stubs MUST be deleted on every terminal disposition: the reconciler
projects ``_researching/<slug>.md`` frontmatter into the Gap row on
every cycle, so a stub left at ``status: classified`` reverts the DB
back to ``classified`` and the gap is re-picked indefinitely.

Triage is a refinement of the upstream ``gap_classifier``, not a
replacement -- the classifier's "external" candidates flow into here,
and Sonnet may downgrade them based on full vault context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from knowledge.gap_stubs import RESEARCHING_DIR
from knowledge.models import Gap
from knowledge.research_agent import AGENT_MODEL, ResearchResult, run_research
from knowledge.research_writer import quarantine, write_research_raw

logger = logging.getLogger(__name__)

RESEARCH_BATCH_SIZE = 3
RESEARCH_PARK_THRESHOLD = 3


def _delete_stub(vault_root: Path, slug: str) -> None:
    # The reconciler projects _researching/<slug>.md frontmatter into the
    # Gap row on every cycle. If we leave the stub at status=classified
    # after the handler flipped the DB row to a terminal state, the next
    # reconciler tick reverts state -> classified and the gap gets
    # re-picked next research tick. This caused the same five gaps to be
    # re-researched ~every 5 minutes for days. Removing the stub stops
    # the projection; the orphan Gap row is harmless (the SELECT filters
    # state='classified', which the row no longer is).
    stub = vault_root / RESEARCHING_DIR / f"{slug}.md"
    try:
        stub.unlink()
    except FileNotFoundError:
        pass


async def research_gaps_handler(*, session: Session, vault_root: Path) -> None:
    """Run one tick of the external research pipeline."""
    # Recovery sweep: if the previous tick crashed mid-flight (between
    # the 'researching' lock and any terminal state assignment), the
    # row would be stuck forever -- the SELECT below filters
    # state='classified', so nothing would ever pick it back up. Sweep
    # stuck rows back to 'classified' before each tick. Safe under the
    # single-worker scheduler model.
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
        # Defense-in-depth privacy guard: even though the SELECT
        # filtered, re-assert before each Sonnet call. Cheap, prevents
        # future misroutes.
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
        # NB: gap.state in-memory is now stale (still 'classified').
        # The Core UPDATE bypassed the ORM identity map. Don't read
        # gap.state below this point -- always assign explicitly.
        if result.rowcount == 0:
            logger.info("knowledge.research-gaps: race lost for %s", gap.term)
            continue

        await _process_one(session=session, gap=gap, vault_root=vault_root)


async def _process_one(*, session: Session, gap: Gap, vault_root: Path) -> None:
    # gap.note_id is the slug used for both _inbox/research/<slug>.md
    # and _failed_research/<slug>-<N>.md. Schema permits NULL, but a
    # classified external gap reaching this point must have one (the
    # reconciler always links a stub note before classification).
    # Assert to fail loudly rather than write files literally named
    # 'None.md'.
    assert gap.note_id is not None, f"gap {gap.id} ({gap.term}) has no note_id"

    researched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        result: ResearchResult = await run_research(
            term=gap.term, vault_root=vault_root
        )
    except Exception:
        logger.exception(
            "knowledge.research-gaps: research failure on %s; reverting state",
            gap.term,
        )
        gap.state = "classified"
        session.commit()
        return

    if result.disposition == "personal":
        gap.gap_class = "internal"
        gap.state = "classified"
        session.commit()
        _delete_stub(vault_root, gap.note_id)
        logger.info(
            "knowledge.research-gaps: %s -> personal (gap_class=internal); reason=%s",
            gap.term,
            result.reason,
        )
        return

    if result.disposition == "discard":
        gap.gap_class = "parked"
        gap.state = "parked"
        session.commit()
        _delete_stub(vault_root, gap.note_id)
        logger.info(
            "knowledge.research-gaps: %s -> discard (gap_class=parked); reason=%s",
            gap.term,
            result.reason,
        )
        return

    # disposition == "research" beyond this point.
    assert result.note is not None, "research disposition implies note is set"

    if not result.note.claims:
        # All emitted claims failed the mechanical citation filter.
        # Quarantine the draft, bump attempts, park if over threshold.
        attempt = gap.research_attempts + 1
        try:
            quarantine(
                vault_root=vault_root,
                slug=gap.note_id,
                attempt=attempt,
                summary=result.note.summary,
                pre_filter_claims=list(result.raw_claims),
                sources=list(result.sources),
                agent_model=AGENT_MODEL,
                researched_at=researched_at,
            )
        except Exception:
            logger.exception(
                "knowledge.research-gaps: quarantine write failed for %s",
                gap.term,
            )
            gap.state = "classified"
            session.commit()
            return

        gap.research_attempts = attempt
        gap.state = "parked" if attempt >= RESEARCH_PARK_THRESHOLD else "classified"
        session.commit()
        if gap.state == "parked":
            _delete_stub(vault_root, gap.note_id)
        logger.info(
            "knowledge.research-gaps: rejected %s (attempt=%d, state=%s)",
            gap.term,
            attempt,
            gap.state,
        )
        return

    try:
        write_research_raw(
            vault_root=vault_root,
            slug=gap.note_id,
            title=gap.term,
            summary=result.note.summary,
            supported_claims=list(result.note.claims),
            sources=list(result.sources),
            agent_model=AGENT_MODEL,
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
        "knowledge.research-gaps: committed %s (claims=%d)",
        gap.term,
        len(result.note.claims),
    )


__all__ = [
    "RESEARCH_BATCH_SIZE",
    "RESEARCH_PARK_THRESHOLD",
    "research_gaps_handler",
]
