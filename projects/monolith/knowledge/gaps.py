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
      a no-op: gaps stay at ``state='discovered'`` until a real classifier
      lands. The "privacy-conservative default" in the design doc is about
      classifier output under uncertainty — not the absence of a
      classifier. Local inference has zero privacy cost; only external
      research does.
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
from sqlalchemy import func
from sqlmodel import Session, select

from knowledge.gap_stubs import RESEARCHING_DIR, write_stub
from knowledge.gardener import _slugify
from knowledge.models import Gap, Note, NoteLink

logger = logging.getLogger(__name__)

GAPS_PIPELINE_VERSION = "gaps@v1"


def split_csv(value: str | None) -> list[str] | None:
    """Split a comma-separated query/tool param into a list, stripping
    whitespace and dropping empty segments. Returns None when input is None
    or all-empty so callers can pass it straight into optional filter kwargs.
    """
    if value is None:
        return None
    parts = [s.strip() for s in value.split(",") if s.strip()]
    return parts or None


# Privacy-conservative fallback used only when a real classifier returns an
# invalid class — route uncertain output to the user (internal), not the web.
# This is NOT used when classifier is absent (that path is a no-op).
_DEFAULT_GAP_CLASS = "internal"

# Classes that are ready for user review after classification.
_USER_REVIEW_CLASSES = {"internal", "hybrid"}

# Valid classifier outputs — mirrors the CHECK constraint on gaps.gap_class.
_VALID_GAP_CLASSES = frozenset({"external", "internal", "hybrid", "parked"})


def discover_gaps(session: Session, vault_root: Path) -> int:
    """Scan note_links for unresolved wikilinks; insert Gap rows and write stubs.

    For each unresolved term:
        * Insert a Gap row if one doesn't already exist (UNIQUE on term).
        * Backfill ``note_id = slug(term)`` on existing rows that pre-date
          this extension.
        * Write a stub note at ``_researching/<slug>.md`` containing the
          accumulated ``referenced_by`` list. ``write_stub`` is idempotent
          so existing stubs (including classifier-edited ones) survive.

    Healing semantics:
        * Gap row exists but stub is missing → write the stub.
        * Stub exists but Gap row is missing → insert the Gap row.
        * Two terms that slug to the same note_id collapse into one Gap row;
          their ``referenced_by`` lists are unioned in the surviving stub.

    Returns the number of "new" items — the count of Gap rows newly inserted
    OR stub files newly written (either side indicates this cycle did work).
    Idempotent: a subsequent run with no changes returns 0.
    """
    # Collect existing note_ids once so the unresolved filter is a set
    # membership check (avoids a correlated subquery per row). Includes
    # slugified frontmatter aliases so wikilinks pointing at a canonical
    # atom under one of its aliases (e.g. `[[Bayes' Theorem]]` slugifies
    # to `bayes-theorem`, but the canonical atom may live at a different
    # slug with "Bayes' Theorem" in `aliases:`) don't get queued as
    # false-positive gaps. Mirrors the gardener atomizer's alias-preserving
    # contract — wherever the gardener writes aliases, the gap-detector
    # consults them.
    existing_note_ids: set[str] = set()
    for note_id, aliases in session.execute(select(Note.note_id, Note.aliases)).all():
        if note_id:
            existing_note_ids.add(note_id)
        for alias in aliases or []:
            existing_note_ids.add(_slugify(alias))

    # All body-wikilink rows. Frontmatter edges (kind='edge') are not
    # treated as gaps — those are typed assertions, not unresolved
    # references that a human would be expected to answer.
    link_rows = session.execute(
        select(
            NoteLink.src_note_fk,
            NoteLink.target_id,
            Note.title,
            Note.note_id,
        )
        .join(Note, Note.id == NoteLink.src_note_fk)
        .where(NoteLink.kind == "link")
    ).all()

    # Phase 1: accumulate per-term breadcrumbs. One term can be referenced
    # by many source notes; the stub's referenced_by reflects that.
    referenced_by: dict[str, set[str]] = {}
    contexts: dict[str, str] = {}
    for row in link_rows:
        target_id = row.target_id
        if target_id in existing_note_ids:
            continue
        referenced_by.setdefault(target_id, set()).add(row.note_id)
        # First-writer wins for context — legacy breadcrumb; the stub's
        # referenced_by is authoritative.
        contexts.setdefault(target_id, row.title or "")

    # Phase 2: fold by slug. Two terms slugging to the same note_id collapse
    # into one slug entry; their referenced_by sets are unioned. Sort terms
    # so the canonical-term-per-slug is reproducible across runs (otherwise
    # the dict-iteration order would pick whichever term landed first).
    slug_refs: dict[str, set[str]] = {}
    slug_canonical_term: dict[str, str] = {}
    slug_context: dict[str, str] = {}
    for term in sorted(referenced_by.keys()):
        slug = _slugify(term)
        slug_refs.setdefault(slug, set()).update(referenced_by[term])
        if slug not in slug_canonical_term:
            slug_canonical_term[slug] = term
            slug_context[slug] = contexts.get(term, "")

    # Pre-load Gap rows by both note_id (post-stub identity) and term (for
    # legacy backfill of rows where note_id is still NULL).
    all_gaps = session.execute(select(Gap)).scalars().all()
    existing_by_note_id: dict[str, Gap] = {g.note_id: g for g in all_gaps if g.note_id}
    existing_by_term: dict[str, Gap] = {g.term: g for g in all_gaps}

    stub_dir = vault_root / RESEARCHING_DIR
    # Canonical Zulu form (no microseconds, no offset) — matches the design
    # doc examples and the test fixture strings, keeps stub frontmatter
    # visually consistent across files.
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserted = 0
    stubs_written = 0
    backfilled = 0
    new_items = 0

    for slug, refs in slug_refs.items():
        canonical_term = slug_canonical_term[slug]
        refs_sorted = sorted(refs)
        row_inserted = False

        existing = existing_by_note_id.get(slug)
        if existing is None:
            legacy = existing_by_term.get(canonical_term)
            if legacy is not None and legacy.note_id is None:
                # Backfill: legacy row pre-dates the stub-notes extension.
                legacy.note_id = slug
                backfilled += 1
            else:
                # SAVEPOINT per insert: a concurrent discoverer could insert
                # the same slug between SELECT and INSERT. Nesting the add lets
                # that single row fail without rolling back every gap this
                # cycle. With Task 1's UNIQUE(note_id) in place this is the
                # last line of defence — slug-folding above already collapses
                # the in-process collisions.
                with session.begin_nested():
                    session.add(
                        Gap(
                            term=canonical_term,
                            context=slug_context[slug],
                            note_id=slug,
                            pipeline_version=GAPS_PIPELINE_VERSION,
                            state="discovered",
                        )
                    )
                inserted += 1
                row_inserted = True

        # Stub write is unconditional — write_stub is idempotent. Track whether
        # a new stub was actually written so we can surface healing work.
        stub_path = stub_dir / f"{slug}.md"
        stub_existed = stub_path.exists()
        write_stub(
            vault_root=vault_root,
            note_id=slug,
            title=slug,
            referenced_by=refs_sorted,
            discovered_at=now_iso,
        )
        stub_newly_written = not stub_existed
        if stub_newly_written:
            stubs_written += 1

        # Count one unit of "work done" per slug where EITHER a new row was
        # inserted OR a new stub was written. Without this OR-collapse, the
        # common case of a first-time discovery would double-count (row + stub)
        # against a single observable gap.
        if row_inserted or stub_newly_written:
            new_items += 1

    if inserted or backfilled:
        session.commit()

    if new_items or backfilled:
        logger.info(
            "gaps.discover_gaps: inserted=%d backfilled_note_id=%d stubs_written=%d",
            inserted,
            backfilled,
            stubs_written,
        )
    return new_items


def classify_gaps(
    session: Session,
    classifier: Callable[[str, str], str] | None = None,
) -> int:
    """Classify every ``state='discovered'`` gap.

    ``classifier`` receives ``(term, context)`` and returns one of
    ``external``, ``internal``, ``hybrid``, ``parked``. If the classifier
    returns an invalid value, falls back to ``internal``
    (privacy-conservative under classifier uncertainty).

    When ``classifier`` is ``None``, this is a no-op: gaps stay at
    ``state='discovered'`` because no classifier is wired in yet. A
    warning is logged when pending gaps exist so the absence is visible.
    The review queue only populates once a real classifier lands (Task 3).

    State transitions (real-classifier path):
        * ``internal`` / ``hybrid`` → ``in_review`` (ready for user)
        * ``external`` → ``classified`` (research pipeline deferred)
        * ``parked`` → ``classified`` (queryable, not budget-consuming)

    Returns the number of gaps classified. When ``classifier`` is ``None``,
    returns 0.
    """
    if classifier is None:
        pending = session.execute(
            select(func.count()).select_from(Gap).where(Gap.state == "discovered")
        ).scalar_one()
        if pending:
            logger.warning(
                "gaps.classify_gaps: %d gaps awaiting classification but no "
                "classifier is wired; leaving them at state='discovered'",
                pending,
            )
        return 0

    rows = session.execute(select(Gap).where(Gap.state == "discovered")).scalars().all()

    classified = 0
    now = datetime.now(timezone.utc)
    for gap in rows:
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
            "gaps.classify_gaps: classified %d gaps",
            classified,
        )
    return classified


def list_review_queue(session: Session) -> list[dict]:
    """Return internal/hybrid gaps awaiting a user answer, oldest first."""
    rows = (
        session.execute(
            select(Gap)
            .where(Gap.state == "in_review")
            .where(Gap.gap_class.in_(("internal", "hybrid")))
            .order_by(Gap.created_at.asc(), Gap.id.asc())
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

    # Remove the stub — its purpose ends once the atom exists. Missing
    # stub is tolerated (user may have hand-deleted it; the atom-at-
    # _processed/ write above is the actual source of truth now). Use
    # the base slug, NOT the collision-suffixed atom note_id — stubs are
    # always created at _researching/<base-slug>.md.
    stub_path = vault_root / RESEARCHING_DIR / f"{slug}.md"
    if stub_path.is_file():
        stub_path.unlink()
        logger.info(
            "gaps.answer_gap: removed stub %s for committed gap_id=%d",
            stub_path.relative_to(vault_root),
            gap_id,
        )

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
