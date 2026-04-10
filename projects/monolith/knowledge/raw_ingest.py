"""Raw ingest pipeline: Phase A (move) and Phase B (reconcile)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from knowledge import frontmatter
from knowledge.raw_paths import (
    RAW_ROOT_NAME,
    compute_raw_id,
    raw_target_path,
)

logger = logging.getLogger("monolith.knowledge.raw_ingest")

_EXCLUDED_TOP_LEVEL = {
    RAW_ROOT_NAME,
    "_processed",
    "_deleted_with_ttl",
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
