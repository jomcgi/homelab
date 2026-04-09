"""Knowledge gardener — decomposes raw vault notes into typed knowledge artifacts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from knowledge import frontmatter

if TYPE_CHECKING:
    from knowledge.store import KnowledgeStore

logger = logging.getLogger("monolith.knowledge.gardener")

_EXCLUDED_DIRS = {"_processed", "_deleted_with_ttl", ".obsidian", ".trash"}
_TTL_HOURS = 24


@dataclass(frozen=True)
class GardenStats:
    ingested: int
    failed: int
    ttl_cleaned: int


class _Embedder(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class Gardener:
    def __init__(
        self,
        *,
        vault_root: Path,
        anthropic_client: object | None,
        store: "KnowledgeStore | None",
        embed_client: _Embedder | None,
    ) -> None:
        self.vault_root = Path(vault_root)
        self.anthropic_client = anthropic_client
        self.store = store
        self.embed_client = embed_client
        self.processed_root = self.vault_root / "_processed"
        self.deleted_root = self.vault_root / "_deleted_with_ttl"

    async def run(self) -> GardenStats:
        """Run one gardening cycle: ingest raw files, then TTL cleanup."""
        raw_files = self._discover_raw_files()
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
        for p in self.vault_root.rglob("*.md"):
            rel = p.relative_to(self.vault_root)
            parts = rel.parts
            # Skip excluded directories and dotfiles/dotdirs
            if any(part in _EXCLUDED_DIRS or part.startswith(".") for part in parts):
                continue
            raw.append(p)
        return sorted(raw)

    async def _ingest_one(self, path: Path) -> None:
        """Decompose a single raw note via Sonnet. Implemented in Task 4."""
        raise NotImplementedError("LLM ingest not yet implemented")

    def _soft_delete(self, source: Path) -> None:
        """Move a raw file to _deleted_with_ttl/ with a TTL in frontmatter."""
        rel = source.relative_to(self.vault_root)
        dest = self.deleted_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        raw = source.read_text(encoding="utf-8")
        ttl_dt = datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)

        meta_match = frontmatter._FRONTMATTER_RE.match(raw)
        if meta_match:
            # Inject ttl into existing frontmatter
            block = meta_match.group(1)
            body = raw[meta_match.end() :]
            new_raw = f'---\nttl: "{ttl_dt.isoformat()}"\n{block}\n---\n{body}'
        else:
            new_raw = f'---\nttl: "{ttl_dt.isoformat()}"\n---\n{raw}'

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
            except Exception:
                logger.exception("gardener: failed to check TTL for %s", p)
        return cleaned
