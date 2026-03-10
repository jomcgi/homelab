"""Qdrant vector database operations via HTTP API."""

from __future__ import annotations

import logging
import uuid

import httpx

from services.knowledge_graph.app.models import ChunkPayload

logger = logging.getLogger(__name__)


class QdrantClient:
    def __init__(self, url: str, collection: str):
        self._url = url.rstrip("/")
        self._collection = collection

    async def ensure_collection(self, vector_size: int) -> None:
        """Create collection if it doesn't exist."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._url}/collections/{self._collection}", timeout=10.0
            )
            if resp.status_code == 200:
                return

            resp = await client.put(
                f"{self._url}/collections/{self._collection}",
                json={
                    "vectors": {"size": vector_size, "distance": "Cosine"},
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("Created Qdrant collection %s", self._collection)

    async def upsert_chunks(
        self,
        chunks: list[ChunkPayload],
        vectors: list[list[float]],
    ) -> None:
        """Upsert points with deterministic UUID5 IDs."""
        _namespace = uuid.UUID("00000000-0000-0000-0000-000000000000")
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = str(
                uuid.uuid5(
                    _namespace, f"{chunk['content_hash']}_{chunk['chunk_index']}"
                )
            )
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "source_type": chunk["source_type"],
                        "source_url": chunk["source_url"],
                        "title": chunk["title"],
                        "author": chunk["author"],
                        "section_header": chunk["section_header"],
                        "chunk_index": chunk["chunk_index"],
                        "chunk_text": chunk["chunk_text"],
                        "content_hash": chunk["content_hash"],
                    },
                }
            )

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self._url}/collections/{self._collection}/points",
                json={"points": points},
                timeout=30.0,
            )
            resp.raise_for_status()

    async def search(self, vector: list[float], limit: int = 5) -> list[dict]:
        """Semantic search, return payloads with scores."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/collections/{self._collection}/points/query",
                json={
                    "query": vector,
                    "limit": limit,
                    "with_payload": True,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for point in data.get("result", {}).get("points", []):
            results.append(
                {
                    "score": point.get("score", 0),
                    **point.get("payload", {}),
                }
            )
        return results

    async def has_content_hash(self, content_hash: str) -> bool:
        """Check if any chunks for this content_hash exist."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/collections/{self._collection}/points/scroll",
                json={
                    "filter": {
                        "must": [
                            {
                                "key": "content_hash",
                                "match": {"value": content_hash},
                            }
                        ]
                    },
                    "limit": 1,
                    "with_payload": False,
                    "with_vector": False,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            points = data.get("result", {}).get("points", [])
            return len(points) > 0
