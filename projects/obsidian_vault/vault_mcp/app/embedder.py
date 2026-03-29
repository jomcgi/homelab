"""Fastembed wrapper for vault embeddings."""

from __future__ import annotations

from fastembed import TextEmbedding


class VaultEmbedder:
    """Embed text using fastembed (CPU, in-process)."""

    def __init__(self, model: str, cache_dir: str):
        self._model = TextEmbedding(model_name=model, cache_dir=cache_dir)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts for indexing."""
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return next(self._model.query_embed(text)).tolist()

    @property
    def dimension(self) -> int:
        return 768
