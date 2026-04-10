"""Knowledge gardener — decomposes raw vault notes into typed knowledge artifacts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import not_, or_
from sqlmodel import Session, select

from knowledge import frontmatter
from knowledge.models import AtomRawProvenance, RawInput

logger = logging.getLogger("monolith.knowledge.gardener")

_EXCLUDED_DIRS = {"_processed", "_raw", ".obsidian", ".trash"}

# Version stamp recorded on every provenance row the gardener produces.
# Bump this when the prompt or model changes to trigger a manual reprocess.
GARDENER_VERSION = "claude-sonnet-4-6@v1"

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CLAUDE_PROMPT_HEADER = """\
You are a knowledge gardener. Decompose the raw note below into atomic knowledge artifacts.

Source raw_id: {raw_id}
Include `derived_from_raw: {raw_id}` as a frontmatter field in every note you create.

Steps:
1. Run `knowledge-search "<topic>"` (Bash) to find related existing notes.
2. Read related notes from {processed_root}/ using the Read tool.
3. Create each atomic note as a new file in {processed_root}/ using the Write tool.
   Allowed types: atom (concept/principle), fact (verifiable claim), active (journal/TODO).
4. Each file must start with YAML frontmatter:
---
id: <slug-of-title>
title: "<concise title — MUST be quoted if it contains a colon>"
type: atom|fact|active
derived_from_raw: {raw_id}
tags: [optional]
edges:
  derives_from: [source-slug]   # allowed edge types: derives_from | refines | generalizes | related | contradicts | supersedes
---
<markdown body>
   IMPORTANT: Always wrap the title value in double quotes to avoid YAML parse errors
   (e.g. `title: "Atomic Note: One Concept"`, NOT `title: Atomic Note: One Concept`).
5. Patch edges on related existing notes using the Edit tool.
6. Each note covers exactly one concept. Prefer many small notes over one large note.

Title: {title}

"""

_CLAUDE_TIMEOUT_SECS = 300


def _slugify(text_in: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_in)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug or "note"


@dataclass(frozen=True)
class GardenStats:
    ingested: int
    failed: int
    moved: int = 0
    deduped: int = 0
    reconciled: int = 0


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """Return (meta_dict, body) split from a markdown file's frontmatter.

    Returns ({}, raw) if no frontmatter block is present.
    """
    if not raw.startswith("---"):
        return {}, raw
    # Find the closing --- on its own line
    lines = raw.splitlines(keepends=True)
    if not lines or not lines[0].rstrip("\r\n") == "---":
        return {}, raw
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, raw
    block = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    try:
        meta = yaml.safe_load(frontmatter._sanitize_yaml_block(block)) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(meta, dict):
        return {}, raw
    return meta, body


_DEFAULT_MAX_FILES_PER_RUN = 10


class Gardener:
    def __init__(
        self,
        *,
        vault_root: Path,
        max_files_per_run: int = _DEFAULT_MAX_FILES_PER_RUN,
        claude_bin: str = "claude",
        session: Session | None = None,
    ) -> None:
        self.vault_root = Path(vault_root)
        # Cap the number of raw files processed per cycle. The claude subprocess
        # can take up to _CLAUDE_TIMEOUT_SECS per file, so an uncapped cycle
        # over a large vault could run for hours. A value <= 0 disables the cap.
        self.max_files_per_run = max_files_per_run
        self.claude_bin = claude_bin
        self.session = session
        self.processed_root = self.vault_root / "_processed"

    def _raws_needing_decomposition(self) -> list[RawInput]:
        """Return raws that have no current-version provenance and no sentinel."""
        if self.session is None:
            return []

        handled_subq = (
            select(AtomRawProvenance.raw_fk)
            .where(AtomRawProvenance.raw_fk.is_not(None))
            .where(
                or_(
                    AtomRawProvenance.gardener_version == GARDENER_VERSION,
                    AtomRawProvenance.gardener_version == "pre-migration",
                )
            )
            .subquery()
        )
        stmt = (
            select(RawInput)
            .where(not_(RawInput.id.in_(select(handled_subq.c.raw_fk))))
            .order_by(RawInput.created_at.asc().nullslast(), RawInput.id.asc())
        )
        return list(self.session.exec(stmt).all())

    async def run(self) -> GardenStats:
        """Run one gardening cycle: move -> reconcile -> decompose."""
        from knowledge.raw_ingest import move_phase, reconcile_raw_phase

        now = datetime.now(timezone.utc)
        move_stats = move_phase(vault_root=self.vault_root, now=now)

        reconcile_stats = None
        if self.session is not None:
            reconcile_stats = reconcile_raw_phase(
                vault_root=self.vault_root, session=self.session
            )
            self.session.commit()

        raws = self._raws_needing_decomposition()
        if self.max_files_per_run > 0 and len(raws) > self.max_files_per_run:
            logger.info(
                "gardener: %d raws need decomposition, capping to %d",
                len(raws),
                self.max_files_per_run,
            )
            raws = raws[: self.max_files_per_run]

        ingested = 0
        failed = 0
        for raw in raws:
            try:
                await self._ingest_one(self.vault_root / raw.path)
                ingested += 1
            except Exception:
                logger.exception("gardener: failed to ingest %s", raw.path)
                failed += 1

        stats = GardenStats(
            ingested=ingested,
            failed=failed,
            moved=move_stats.moved,
            deduped=move_stats.deduped,
            reconciled=(reconcile_stats.inserted if reconcile_stats else 0),
        )
        logger.info(
            "knowledge.garden: moved=%d deduped=%d reconciled=%d ingested=%d failed=%d",
            stats.moved,
            stats.deduped,
            stats.reconciled,
            stats.ingested,
            stats.failed,
        )
        return stats

    def _discover_raw_files(self) -> list[Path]:
        """Find .md files in the vault root that are not in excluded directories."""
        raw: list[Path] = []
        if not self.vault_root.exists():
            return raw
        for entry in self.vault_root.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.name in _EXCLUDED_DIRS:
                continue
            if entry.is_file():
                if entry.suffix == ".md":
                    raw.append(entry)
                continue
            if entry.is_dir():
                for p in entry.rglob("*.md"):
                    rel = p.relative_to(self.vault_root)
                    if any(part.startswith(".") for part in rel.parts):
                        continue
                    raw.append(p)
        return sorted(raw)

    async def _run_claude_subprocess(self, prompt: str) -> None:
        """Spawn a claude Code subprocess and wait for completion."""
        proc = await asyncio.create_subprocess_exec(
            self.claude_bin,
            "--print",
            "--dangerously-skip-permissions",
            "--allowedTools",
            "Bash,Read,Write,Edit",
            "-p",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.vault_root,
            # HOME=/ in the container (non-root uid 65532) is not writable, so
            # claude cannot create ~/.claude/ and exits silently with code 0.
            # Override HOME to /tmp which is always writable.
            env={**os.environ, "HOME": "/tmp"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_CLAUDE_TIMEOUT_SECS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"claude timed out after {_CLAUDE_TIMEOUT_SECS}s")

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited {proc.returncode}: "
                f"{stderr.decode(errors='replace')[:300]}"
            )

        self._last_stdout = stdout

    async def _ingest_one(self, path: Path) -> None:
        """Decompose a single raw note by spawning a claude Code subprocess."""
        raw_text = path.read_text(encoding="utf-8")
        meta, body = frontmatter.parse(raw_text)
        title = meta.title or path.stem

        # Look up RawInput row for raw_id breadcrumb and provenance.
        raw_row: RawInput | None = None
        raw_id = ""
        if self.session is not None:
            raw_row = self.session.exec(
                select(RawInput).where(
                    RawInput.path == str(path.relative_to(self.vault_root))
                )
            ).first()
            if raw_row is not None:
                raw_id = raw_row.raw_id

        prompt = (
            _CLAUDE_PROMPT_HEADER.format(
                processed_root=self.processed_root,
                title=title,
                raw_id=raw_id,
            )
            + raw_text
        )

        before = (
            set(self.processed_root.glob("*.md"))
            if self.processed_root.exists()
            else set()
        )

        self._last_stdout = b""
        await self._run_claude_subprocess(prompt)

        after = (
            set(self.processed_root.glob("*.md"))
            if self.processed_root.exists()
            else set()
        )
        new_files = sorted(after - before)
        if not new_files:
            logger.warning(
                "gardener: claude produced no notes for %s; leaving raw file in place\n"
                "  stdout: %s",
                path,
                self._last_stdout.decode(errors="replace")[:500],
            )
            return

        if raw_row is not None and self.session is not None:
            for new_file in new_files:
                try:
                    file_meta, _ = frontmatter.parse(
                        new_file.read_text(encoding="utf-8")
                    )
                    note_id = file_meta.note_id
                except Exception:
                    continue
                if not note_id:
                    continue
                self.session.add(
                    AtomRawProvenance(
                        raw_fk=raw_row.id,
                        derived_note_id=note_id,
                        gardener_version=GARDENER_VERSION,
                    )
                )
            self.session.commit()
