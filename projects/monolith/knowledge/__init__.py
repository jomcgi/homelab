"""Knowledge domain — knowledge graph CRUD, search, tasks, and dead-letter management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

if TYPE_CHECKING:
    from sqlmodel import Session


def register(app: FastAPI) -> None:
    """Register knowledge domain routers with the app."""
    from knowledge.router import router
    from knowledge.tasks_router import router as tasks_router

    app.include_router(router)
    app.include_router(tasks_router)


def search_notes(session: "Session", query_embedding: list[float], **kwargs):
    """Search knowledge notes by embedding similarity."""
    from knowledge.store import KnowledgeStore

    return KnowledgeStore(session).search_notes_with_context(
        query_embedding=query_embedding, **kwargs
    )


def get_store(session: "Session"):
    """Return a KnowledgeStore instance for the given session."""
    from knowledge.store import KnowledgeStore

    return KnowledgeStore(session)


def get_embedding_client():
    """Return an embedding client instance (DI seam for tests)."""
    from shared.embedding import EmbeddingClient

    return EmbeddingClient()
