"""Embedder protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, return list of vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimension."""
        ...
