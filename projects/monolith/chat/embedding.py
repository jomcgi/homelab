"""Embedding client -- calls voyage-4-nano via llama.cpp /v1/embeddings."""

import os

import httpx

EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "")


class EmbeddingClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or EMBEDDING_URL

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, returning a 1024-dim vector."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": text, "model": "voyage-4-nano"},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
