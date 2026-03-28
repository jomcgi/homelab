"""Qdrant vector database operations via HTTP API."""

from __future__ import annotations

import logging
import uuid

import httpx

from projects.obsidian_vault.vault_mcp.app.chunker import ChunkPayload

logger = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")


class QdrantClient:
    def __init__(self, url: str, collection: str):
        self._url = url.rstrip("/")
        self._collection = collection

    async def ensure_collection(self, vector_size: int) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._url}/collections/{self._collection}")
            if resp.status_code == 200:
                return
            resp = await client.put(
                f"{self._url}/collections/{self._collection}",
                json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            )
            resp.raise_for_status()
            logger.info("Created Qdrant collection %s", self._collection)

    async def upsert_chunks(
        self,
        chunks: list[ChunkPayload],
        vectors: list[list[float]],
    ) -> None:
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = str(
                uuid.uuid5(
                    _NAMESPACE, f"{chunk['content_hash']}_{chunk['chunk_index']}"
                )
            )
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "source_url": chunk["source_url"],
                        "title": chunk["title"],
                        "section_header": chunk["section_header"],
                        "chunk_index": chunk["chunk_index"],
                        "chunk_text": chunk["chunk_text"],
                        "content_hash": chunk["content_hash"],
                    },
                }
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{self._url}/collections/{self._collection}/points",
                json={"points": points},
            )
            resp.raise_for_status()

    async def search(self, vector: list[float], limit: int = 5) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._url}/collections/{self._collection}/points/query",
                json={"query": vector, "limit": limit, "with_payload": True},
            )
            resp.raise_for_status()
            data = resp.json()
        results = []
        for point in data.get("result", {}).get("points", []):
            results.append({"score": point.get("score", 0), **point.get("payload", {})})
        return results

    async def delete_by_source_url(self, source_url: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._url}/collections/{self._collection}/points/delete",
                json={
                    "filter": {
                        "must": [{"key": "source_url", "match": {"value": source_url}}]
                    }
                },
            )
            resp.raise_for_status()

    async def get_indexed_sources(self) -> dict[str, str]:
        sources: dict[str, str] = {}
        offset = None
        while True:
            body: dict = {
                "limit": 100,
                "with_payload": ["source_url", "content_hash"],
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._url}/collections/{self._collection}/points/scroll",
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
            for point in data.get("result", {}).get("points", []):
                payload = point.get("payload", {})
                url = payload.get("source_url", "")
                h = payload.get("content_hash", "")
                if url and url not in sources:
                    sources[url] = h
            next_offset = data.get("result", {}).get("next_page_offset")
            if next_offset is None:
                break
            offset = next_offset
        return sources
