"""Gap discovery, classification, review queue, and answer capture.

A "gap" is an unresolved ``[[wikilink]]`` — a body-text reference whose
target note does not (yet) exist in the graph. The four functions in this
module together drive the gap lifecycle:

    discover_gaps  → ingest unresolved links into the gaps table
    classify_gaps  → route each gap to external/internal/hybrid/parked
    list_review_queue  → enumerate gaps awaiting a user answer
    answer_gap     → accept a user answer, emit a personal-tier atom

All four are pure-ish functions taking an open ``Session``; the caller
owns the session lifecycle. This matches the rest of the knowledge
module (``store.py``, ``gardener.py``).

Design notes:
    * ``classifier`` is an injected callable — the real Claude-backed
      classifier is wired in separately (Task 3). Leaving it ``None`` is
      the privacy-conservative fallback: everything routes to ``internal``
      so the user reviews it, nothing escapes to the web.
    * Consolidation never mutates committed atoms — ``answer_gap``
      creates a brand-new file and leaves the rest of the vault alone.
    * We deliberately do *not* reconcile the new file into the DB here;
      the reconciler picks it up on its next tick, matching the existing
      ``create_note`` HTTP endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml
from sqlmodel import Session, select

from knowledge.gardener import _slugify
from knowledge.models import Gap, Note, NoteLink

logger = logging.getLogger(__name__)

GAPS_PIPELINE_VERSION = "gaps@v1"

# Privacy-conservative default: uncertain → internal (route to user, not web).
_DEFAULT_GAP_CLASS = "internal"

# Classes that are ready for user review after classification.
_USER_REVIEW_CLASSES = {"internal", "hybrid"}

# Valid classifier outputs — mirrors the CHECK constraint on gaps.gap_class.
_VALID_GAP_CLASSES = frozenset({"external", "internal", "hybrid", "parked"})


def discover_gaps(session: Session) -> int:
    """Scan note_links for unresolved wikilinks; insert new Gap rows.

    Returns the number of newly-inserted gaps (not the total). Idempotent:
    subsequent calls surface only previously-unseen (term, source_note_fk)
    pairs thanks to a pre-check against the UNIQUE constraint.
    """
    # Collect existing note_ids once so the unresolved filter is a set
    # membership check (avoids a correlated subquery per row).
    existing_note_ids = set(session.execute(select(Note.note_id)).scalars().all())

    # All body-wikilink rows. Frontmatter edges (kind='edge') are not
    # treated as gaps — those are typed assertions, not unresolved
    # references that a human would be expected to answer.
    link_rows = session.execute(
        select(
            NoteLink.src_note_fk,
            NoteLink.target_id,
            Note.title,
        )
        .join(Note, Note.id == NoteLink.src_note_fk)
        .where(NoteLink.kind == "link")
    ).all()

    # Pre-load existing (term, source_note_fk) pairs to avoid an
    # IntegrityError round-trip for gaps we already know about.
    existing_gap_keys = set(session.execute(select(Gap.term, Gap.source_note_fk)).all())

    created = 0
    for row in link_rows:
        target_id = row.target_id
        if target_id in existing_note_ids:
            continue
        key = (target_id, row.src_note_fk)
        if key in existing_gap_keys:
            continue

        # SAVEPOINT per insert: even though we pre-check the UNIQUE key, a
        # concurrent discoverer could insert the same (term, source_note_fk)
        # between SELECT and INSERT. Nesting the add lets that single row
        # fail without rolling back every gap already inserted this cycle.
        with session.begin_nested():
            session.add(
                Gap(
                    term=target_id,
                    context=row.title or "",
                    source_note_fk=row.src_note_fk,
                    pipeline_version=GAPS_PIPELINE_VERSION,
                    state="discovered",
                )
            )
        existing_gap_keys.add(key)
        created += 1

    if created:
        session.commit()
        logger.info("gaps.discover_gaps: inserted %d new gaps", created)
    return created


def classify_gaps(
    session: Session,
    classifier: Callable[[str, str], str] | None = None,
) -> int:
    """Classify every ``state='discovered'`` gap.

    ``classifier`` receives ``(term, context)`` and returns one of
    ``external``, ``internal``, ``hybrid``, ``parked``. When ``None``,
    every gap is routed to ``internal`` — the privacy-conservative
    fallback that keeps the first slice working without any model wired
    in (Task 3 injects the real classifier).

    State transitions:
        * ``internal`` / ``hybrid`` → ``in_review`` (ready for user)
        * ``external`` → ``classified`` (research pipeline deferred)
        * ``parked`` → ``classified`` (queryable, not budget-consuming)

    Returns the number of gaps classified.
    """
    rows = session.execute(select(Gap).where(Gap.state == "discovered")).scalars().all()

    classified = 0
    now = datetime.now(timezone.utc)
    for gap in rows:
        if classifier is None:
            gap_class = _DEFAULT_GAP_CLASS
        else:
            gap_class = classifier(gap.term, gap.context)
            if gap_class not in _VALID_GAP_CLASSES:
                logger.warning(
                    "gaps.classify_gaps: classifier returned invalid class %r "
                    "for gap id=%d; defaulting to internal (privacy-conservative)",
                    gap_class,
                    gap.id,
                )
                gap_class = _DEFAULT_GAP_CLASS

        gap.gap_class = gap_class
        gap.classified_at = now
        if gap_class in _USER_REVIEW_CLASSES:
            gap.state = "in_review"
        else:
            gap.state = "classified"
        classified += 1

    if classified:
        # TODO(task-3): chunk commits (e.g. every 25 gaps) once the real
        # model-backed classifier is wired in. A 100-gap batch × 20s/call holds a
        # 2000s transaction; risks idle_in_transaction_session_timeout and loses
        # progress on crash.
        session.commit()
        logger.info(
            "gaps.classify_gaps: classified %d gaps (classifier=%s)",
            classified,
            "default-internal" if classifier is None else "custom",
        )
    return classified


def list_review_queue(session: Session) -> list[dict]:
    """Return internal/hybrid gaps awaiting a user answer, oldest first."""
    rows = (
        session.execute(
            select(Gap)
            .where(Gap.state == "in_review")
            .where(Gap.gap_class.in_(("internal", "hybrid")))
            .order_by(Gap.created_at.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": gap.id,
            "term": gap.term,
            "context": gap.context,
            "gap_class": gap.gap_class,
            "created_at": gap.created_at,
        }
        for gap in rows
    ]


def answer_gap(
    session: Session,
    gap_id: int,
    answer: str,
    vault_root: Path,
) -> dict:
    """Commit a user answer: emit a personal-tier atom, mark gap committed.

    The new atom is written to ``<vault_root>/_processed/<slug>.md`` with
    frontmatter ``source_tier: personal`` so downstream consumers can
    distinguish user-authored atoms from gardener-derived ones. Filename
    collisions are resolved by appending ``-1``, ``-2``, etc. — same
    pattern as :func:`knowledge.router.create_note`.

    The new file is *not* reconciled into the DB here; the reconciler
    picks it up on its next tick. This matches ``create_note``'s contract.

    Raises:
        ValueError: if ``gap_id`` is unknown or the gap is not in
            ``state='in_review'``.
    """
    gap = session.get(Gap, gap_id)
    if gap is None:
        raise ValueError(f"Gap not found: id={gap_id}")
    if gap.state != "in_review":
        raise ValueError(
            f"Gap id={gap_id} is in state={gap.state!r}, expected 'in_review'"
        )
    if "\n---\n" in f"\n{answer}\n":
        raise ValueError(
            "answer may not contain a frontmatter terminator ('---' on its own line)"
        )

    processed_root = vault_root / "_processed"
    processed_root.mkdir(parents=True, exist_ok=True)

    slug = _slugify(gap.term)
    filename = f"{slug}.md"
    dest = processed_root / filename
    counter = 1
    while dest.exists():
        filename = f"{slug}-{counter}.md"
        dest = processed_root / filename
        counter += 1

    # The id in frontmatter must match the final filename stem so the
    # reconciler resolves the file to a stable note_id.
    note_id = filename[:-3]  # strip .md
    fm = {
        "id": note_id,
        "title": gap.term,
        "type": "atom",
        "source_tier": "personal",
    }
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False)
    file_content = f"---\n{fm_str}---\n\n{answer}\n"
    dest.write_text(file_content)

    gap.answer = answer
    gap.state = "committed"
    gap.resolved_at = datetime.now(timezone.utc)
    # TODO(task-3): make file-write + DB-commit transactional (e.g. write to
    # <dest>.tmp, commit DB, rename). Today a commit failure after write leaves
    # an orphan file that a retry resolves to <slug>-1.md.
    session.commit()

    relative_path = dest.relative_to(vault_root)
    logger.info(
        "gaps.answer_gap: committed gap_id=%d as note_id=%s path=%s",
        gap_id,
        note_id,
        relative_path,
    )
    return {
        "gap_id": gap_id,
        "path": str(relative_path),
        "note_id": note_id,
    }
