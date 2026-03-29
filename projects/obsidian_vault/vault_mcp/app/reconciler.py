"""Stateless vault reconciler — syncs vault files to Qdrant."""

from __future__ import annotations

import asyncio
import gc
import hashlib
import logging
from pathlib import Path

from projects.obsidian_vault.vault_mcp.app.chunker import chunk_markdown
from projects.obsidian_vault.vault_mcp.app.embedder import VaultEmbedder
from projects.obsidian_vault.vault_mcp.app.qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


class VaultReconciler:
    def __init__(
        self,
        vault_path: str,
        embedder: VaultEmbedder,
        qdrant: QdrantClient,
    ):
        self._vault = Path(vault_path)
        self._embedder = embedder
        self._qdrant = qdrant

    def _walk_vault(self) -> dict[str, str]:
        """Walk vault, return {source_url: content_hash} for all .md files."""
        files: dict[str, str] = {}
        for md in self._vault.rglob("*.md"):
            rel = md.relative_to(self._vault)
            if any(part.startswith(".") for part in rel.parts):
                continue
            content = md.read_text()
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            files[f"vault://{rel}"] = content_hash
        return files

    async def run(self) -> None:
        """Run one reconciliation cycle."""
        on_disk = self._walk_vault()
        indexed = await self._qdrant.get_indexed_sources()

        to_embed: list[str] = []
        to_delete: list[str] = []

        for source_url, disk_hash in on_disk.items():
            if source_url not in indexed:
                to_embed.append(source_url)
            elif indexed[source_url] != disk_hash:
                to_delete.append(source_url)
                to_embed.append(source_url)

        for source_url in indexed:
            if source_url not in on_disk:
                to_delete.append(source_url)

        for source_url in to_delete:
            await self._qdrant.delete_by_source_url(source_url)

        for source_url in to_embed:
            rel_path = source_url.removeprefix("vault://")
            content = (self._vault / rel_path).read_text()
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            chunks = chunk_markdown(
                content=content,
                content_hash=content_hash,
                source_url=source_url,
                title=rel_path,
            )
            if not chunks:
                continue
            texts = [c["chunk_text"] for c in chunks]
            loop = asyncio.get_running_loop()
            vectors = await loop.run_in_executor(
                None, self._embedder.embed, texts
            )
            await self._qdrant.upsert_chunks(chunks, vectors)
            del texts, vectors, chunks
            gc.collect()

        logger.info(
            "Reconciled: %d embedded, %d deleted, %d unchanged",
            len(to_embed),
            len(to_delete),
            len(on_disk) - len(to_embed),
        )
