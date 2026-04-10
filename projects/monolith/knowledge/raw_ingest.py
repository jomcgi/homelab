"""Raw ingest pipeline: Phase A (move) and Phase B (reconcile)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from knowledge import frontmatter
from knowledge.models import Note, RawInput
from knowledge.raw_paths import (
    GRANDFATHERED_SUBDIR,
    RAW_ROOT_NAME,
    compute_raw_id,
    raw_target_path,
)

logger = logging.getLogger("monolith.knowledge.raw_ingest")

_EXCLUDED_TOP_LEVEL = {
    RAW_ROOT_NAME,
    "_processed",
    ".obsidian",
    ".trash",
}


@dataclass(frozen=True)
class MovePhaseStats:
    moved: int
    deduped: int


def _discover_vault_root_drops(vault_root: Path) -> list[Path]:
    """Find .md files outside managed directories."""
    drops: list[Path] = []
    if not vault_root.exists():
        return drops
    for entry in vault_root.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.name in _EXCLUDED_TOP_LEVEL:
            continue
        if entry.is_file():
            if entry.suffix == ".md":
                drops.append(entry)
            continue
        if entry.is_dir():
            for p in entry.rglob("*.md"):
                rel = p.relative_to(vault_root)
                if any(part.startswith(".") for part in rel.parts):
                    continue
                drops.append(p)
    return sorted(drops)


def move_phase(*, vault_root: Path, now: datetime) -> MovePhaseStats:
    """Atomically move vault-root .md drops into _raw/YYYY/MM/DD/.

    Idempotent: if the target already exists (same content_hash) the
    source is deleted as a dedup.
    """
    moved = 0
    deduped = 0
    for source in _discover_vault_root_drops(vault_root):
        try:
            content = source.read_text(encoding="utf-8")
        except OSError as read_err:
            logger.warning("move_phase: failed to read %s: %s", source, read_err)
            continue

        raw_id = compute_raw_id(content)
        try:
            meta, _ = frontmatter.parse(content)
            title = meta.title or source.stem
        except Exception:
            title = source.stem

        target = raw_target_path(
            vault_root=vault_root,
            raw_id=raw_id,
            title=title,
            created_at=now,
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            # Same content already captured -- delete source.
            source.unlink()
            deduped += 1
            continue

        source.replace(target)  # atomic rename within the same filesystem
        moved += 1

    return MovePhaseStats(moved=moved, deduped=deduped)


@dataclass(frozen=True)
class ReconcileRawStats:
    inserted: int
    skipped: int


def _infer_source(meta_source: str | None, rel_parts: tuple[str, ...]) -> str:
    if meta_source:
        return meta_source
    if GRANDFATHERED_SUBDIR in rel_parts:
        return "grandfathered"
    return "vault-drop"


def reconcile_raw_phase(*, vault_root: Path, session: Session) -> ReconcileRawStats:
    """Mirror _raw/ contents into knowledge.raw_inputs + notes(type='raw').

    Idempotent on path: already-reconciled files are skipped.
    The caller is responsible for committing the session.
    """
    raw_root = vault_root / RAW_ROOT_NAME
    if not raw_root.exists():
        return ReconcileRawStats(inserted=0, skipped=0)

    inserted = 0
    skipped = 0

    existing_paths = set(session.exec(select(RawInput.path)).all())

    for file_path in sorted(raw_root.rglob("*.md")):
        rel = file_path.relative_to(vault_root).as_posix()
        if rel in existing_paths:
            skipped += 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as read_err:
            logger.warning(
                "reconcile_raw_phase: failed to read %s: %s", file_path, read_err
            )
            continue

        try:
            meta, _body = frontmatter.parse(content)
        except Exception:
            meta = None

        raw_id = compute_raw_id(content)
        title = meta.title if meta and meta.title else file_path.stem
        source = _infer_source(
            meta.source if meta else None,
            file_path.relative_to(vault_root).parts,
        )
        original_path = None
        if meta and meta.extra:
            original_path = meta.extra.get("original_path")

        ri = RawInput(
            raw_id=raw_id,
            path=rel,
            source=source,
            original_path=original_path,
            content=content,
            content_hash=raw_id,
        )
        note = Note(
            note_id=raw_id,
            path=rel,
            title=title,
            content_hash=raw_id,
            type="raw",
            source=source,
            indexed_at=datetime.now(timezone.utc),
        )
        try:
            with session.begin_nested():
                session.add(ri)
                session.add(note)
        except Exception:
            logger.warning(
                "reconcile_raw_phase: failed to insert %s", rel, exc_info=True
            )
            continue
        inserted += 1

    return ReconcileRawStats(inserted=inserted, skipped=skipped)
