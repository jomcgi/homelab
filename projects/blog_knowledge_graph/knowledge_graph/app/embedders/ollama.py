"""Ollama embedding provider."""

from __future__ import annotations

import httpx


class OllamaEmbedder:
    """Embed text using Ollama's /api/embed endpoint."""

    def __init__(
        self, url: str = "http://localhost:11434", model: str = "nomic-embed-text"
    ):
        self._url = url.rstrip("/")
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Nomic expects search_document: prefix for indexing
        prefixed = [f"search_document: {t}" for t in texts]
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._url}/api/embed",
                json={"model": self._model, "input": prefixed},
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (uses search_query: prefix for Nomic)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._url}/api/embed",
                json={"model": self._model, "input": [f"search_query: {text}"]},
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"][0]

    @property
    def dimension(self) -> int:
        return 768
