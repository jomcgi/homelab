"""Knowledge gardener — decomposes raw vault notes into typed knowledge artifacts."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from knowledge import frontmatter

logger = logging.getLogger("monolith.knowledge.gardener")

_EXCLUDED_DIRS = {"_processed", "_deleted_with_ttl", ".obsidian", ".trash"}
_TTL_HOURS = 24

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CLAUDE_PROMPT_HEADER = """\
You are a knowledge gardener. Decompose the raw note below into atomic knowledge artifacts.

Steps:
1. Run `knowledge-search "<topic>"` (Bash) to find related existing notes.
2. Read related notes from {processed_root}/ using the Read tool.
3. Create each atomic note as a new file in {processed_root}/ using the Write tool.
   Allowed types: atom (concept/principle), fact (verifiable claim), active (journal/TODO).
4. Each file must start with YAML frontmatter:
---
id: <slug-of-title>
title: <concise title>
type: atom|fact|active
tags: [optional]
edges:
  derives_from: [source-slug]
---
<markdown body>
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
    ttl_cleaned: int


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
        meta = yaml.safe_load(block) or {}
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
    ) -> None:
        self.vault_root = Path(vault_root)
        # Cap the number of raw files processed per cycle. The claude subprocess
        # can take up to _CLAUDE_TIMEOUT_SECS per file, so an uncapped cycle
        # over a large vault could run for hours. A value <= 0 disables the cap.
        self.max_files_per_run = max_files_per_run
        self.claude_bin = claude_bin
        self.processed_root = self.vault_root / "_processed"
        self.deleted_root = self.vault_root / "_deleted_with_ttl"

    async def run(self) -> GardenStats:
        """Run one gardening cycle: ingest raw files, then TTL cleanup."""
        raw_files = self._discover_raw_files()
        if self.max_files_per_run > 0 and len(raw_files) > self.max_files_per_run:
            logger.info(
                "gardener: discovered %d raw files, capping this run at %d",
                len(raw_files),
                self.max_files_per_run,
            )
            raw_files = raw_files[: self.max_files_per_run]
        ingested = 0
        failed = 0
        for path in raw_files:
            try:
                await self._ingest_one(path)
                ingested += 1
            except Exception:
                logger.exception("gardener: failed to ingest %s", path)
                failed += 1
        ttl_cleaned = self._cleanup_ttl()
        stats = GardenStats(ingested=ingested, failed=failed, ttl_cleaned=ttl_cleaned)
        logger.info(
            "knowledge.garden: ingested=%d failed=%d ttl_cleaned=%d",
            stats.ingested,
            stats.failed,
            stats.ttl_cleaned,
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

    async def _ingest_one(self, path: Path) -> None:
        """Decompose a single raw note by spawning a claude Code subprocess."""
        raw = path.read_text(encoding="utf-8")
        meta, body = frontmatter.parse(raw)
        title = meta.title or path.stem

        prompt = (
            _CLAUDE_PROMPT_HEADER.format(
                processed_root=self.processed_root,
                title=title,
            )
            + body
        )

        before = (
            set(self.processed_root.glob("*.md"))
            if self.processed_root.exists()
            else set()
        )

        proc = await asyncio.create_subprocess_exec(
            self.claude_bin,
            "--print",
            "--allowedTools",
            "Bash,Read,Write,Edit",
            "-p",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_CLAUDE_TIMEOUT_SECS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"claude timed out after {_CLAUDE_TIMEOUT_SECS}s for {path}"
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited {proc.returncode}: "
                f"{stderr.decode(errors='replace')[:300]}"
            )

        after = (
            set(self.processed_root.glob("*.md"))
            if self.processed_root.exists()
            else set()
        )
        if not (after - before):
            logger.warning(
                "gardener: claude produced no notes for %s; leaving raw file in place",
                path,
            )
            return

        self._soft_delete(path)

    def _soft_delete(self, source: Path) -> None:
        """Move a raw file to _deleted_with_ttl/ with a TTL in frontmatter."""
        rel = source.relative_to(self.vault_root)
        dest = self.deleted_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        raw = source.read_text(encoding="utf-8")
        ttl_dt = datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)
        ttl_iso = ttl_dt.isoformat()

        meta_dict, body = _split_frontmatter(raw)
        meta_dict["ttl"] = ttl_iso  # Overwrites any existing ttl

        new_raw = (
            f"---\n{yaml.safe_dump(meta_dict, sort_keys=False).rstrip()}\n---\n{body}"
        )

        dest.write_text(new_raw, encoding="utf-8")
        source.unlink()

    def _cleanup_ttl(self) -> int:
        """Delete files in _deleted_with_ttl/ whose TTL has expired."""
        if not self.deleted_root.exists():
            return 0
        now = datetime.now(timezone.utc)
        cleaned = 0
        for p in list(self.deleted_root.rglob("*.md")):
            try:
                raw = p.read_text(encoding="utf-8")
                meta, _ = frontmatter.parse(raw)
                ttl_str = meta.extra.get("ttl")
                if not ttl_str:
                    continue
                ttl_dt = datetime.fromisoformat(str(ttl_str))
                if ttl_dt.tzinfo is None:
                    ttl_dt = ttl_dt.replace(tzinfo=timezone.utc)
                if now >= ttl_dt:
                    p.unlink()
                    cleaned += 1
            except (
                ValueError,
                OSError,
                yaml.YAMLError,
                frontmatter.FrontmatterError,
            ) as exc:
                logger.warning("gardener: failed to check TTL for %s: %s", p, exc)
        return cleaned
