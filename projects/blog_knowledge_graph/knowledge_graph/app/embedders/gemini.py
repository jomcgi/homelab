"""Gemini embedding provider."""

from __future__ import annotations

import httpx


class GeminiEmbedder:
    """Embed text using the Gemini embedding API."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-embedding-001"):
        self._api_key = api_key
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        requests_payload = [
            {
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": t}]},
                "taskType": "RETRIEVAL_DOCUMENT",
            }
            for t in texts
        ]
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.ENDPOINT}/{self._model}:batchEmbedContents",
                params={"key": self._api_key},
                json={"requests": requests_payload},
            )
            response.raise_for_status()
            data = response.json()
            return [e["values"] for e in data["embeddings"]]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.ENDPOINT}/{self._model}:embedContent",
                params={"key": self._api_key},
                json={
                    "model": f"models/{self._model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_QUERY",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]["values"]

    @property
    def dimension(self) -> int:
        return 768
