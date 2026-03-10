"""Embedding pipeline entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from projects.blog_knowledge_graph.knowledge_graph.app.chunker import chunk_markdown
from projects.blog_knowledge_graph.knowledge_graph.app.config import EmbedderSettings
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.gemini import (
    GeminiEmbedder,
)
from projects.blog_knowledge_graph.knowledge_graph.app.embedders.ollama import (
    OllamaEmbedder,
)
from projects.blog_knowledge_graph.knowledge_graph.app.qdrant_client import QdrantClient
from projects.blog_knowledge_graph.knowledge_graph.app.storage import S3Storage
from projects.blog_knowledge_graph.knowledge_graph.app.telemetry import (
    setup_telemetry,
    trace_span,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _create_embedder(settings: EmbedderSettings):
    if settings.provider == "gemini":
        return GeminiEmbedder(
            api_key=settings.gemini_api_key, model=settings.gemini_model
        )
    return OllamaEmbedder(url=settings.ollama_url, model=settings.ollama_model)


async def run_embedding_pipeline(settings: EmbedderSettings) -> None:
    storage = S3Storage(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    qdrant = QdrantClient(
        url=settings.qdrant_url, collection=settings.qdrant_collection
    )
    embedder = _create_embedder(settings)

    await qdrant.ensure_collection(vector_size=settings.vector_size)

    all_hashes = storage.list_all_hashes()
    logger.info("Found %d documents in S3", len(all_hashes))

    embedded_count = 0
    skipped_count = 0

    for hash_key in all_hashes:
        with trace_span(f"embed:{hash_key[:12]}"):
            # Check if already embedded
            if await qdrant.has_content_hash(hash_key):
                skipped_count += 1
                continue

            content = storage.get_content(hash_key)
            meta = storage.get_meta(hash_key)
            if not content or not meta:
                logger.warning("Missing content or meta for %s", hash_key)
                continue

            # Chunk
            chunks = chunk_markdown(
                content=content,
                content_hash=hash_key,
                source_url=meta.get("source_url", ""),
                source_type=meta.get("source_type", ""),
                title=meta.get("title", ""),
                author=meta.get("author"),
                published_at=meta.get("published_at"),
                max_tokens=settings.chunk_max_tokens,
                min_tokens=settings.chunk_min_tokens,
            )

            if not chunks:
                logger.warning("No chunks produced for %s", hash_key)
                continue

            # Embed in batches
            texts = [c["chunk_text"] for c in chunks]
            batch_size = 32
            all_vectors: list[list[float]] = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                vectors = await embedder.embed(batch)
                all_vectors.extend(vectors)

            # Upsert to Qdrant
            await qdrant.upsert_chunks(chunks, all_vectors)
            embedded_count += 1
            logger.info(
                "Embedded %s: %d chunks (%s)",
                hash_key[:12],
                len(chunks),
                meta.get("title", ""),
            )

    logger.info(
        "Embedding pipeline complete: %d embedded, %d skipped",
        embedded_count,
        skipped_count,
    )


def main() -> int:
    settings = EmbedderSettings()
    setup_telemetry("knowledge-graph-embedder")
    asyncio.run(run_embedding_pipeline(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
