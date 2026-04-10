"""HTTP API for the knowledge search overlay.

Two endpoints back the cmdk-style search UI:

- ``GET /api/knowledge/search`` — embed the query via ``EmbeddingClient`` and
  hand off to ``KnowledgeStore.search_notes_with_context``.
- ``GET /api/knowledge/notes/{note_id}`` — fetch a note by id and read its
  vault markdown off disk so the preview pane can render it.

The embedding client is injected through ``get_embedding_client`` so e2e tests
can override it with a deterministic fake via ``app.dependency_overrides``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from knowledge.service import _DEFAULT_VAULT_ROOT, _VAULT_ROOT_ENV
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def get_embedding_client() -> EmbeddingClient:
    """DI seam for the embedding client.

    Tests override this via ``app.dependency_overrides[get_embedding_client]``
    to inject a deterministic fake.
    """
    return EmbeddingClient()


@router.get("/search")
async def search_knowledge(
    q: str = "",
    type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    embed_client: EmbeddingClient = Depends(get_embedding_client),
) -> dict:
    # Mirror the frontend's 2-char debounce threshold: skip the embed call
    # entirely for empty / single-char queries so we never hit the embed
    # service for no reason.
    if len(q) < 2:
        return {"results": []}

    try:
        vector = await embed_client.embed(q)
    except Exception:
        logger.exception("knowledge.search: embedding call failed")
        raise HTTPException(status_code=503, detail="embedding unavailable")

    results = KnowledgeStore(session).search_notes_with_context(
        query_embedding=vector,
        limit=limit,
        type_filter=type,
    )
    return {"results": results}


@router.get("/notes/{note_id}")
def get_knowledge_note(
    note_id: int,
    session: Session = Depends(get_session),
) -> dict:
    note = KnowledgeStore(session).get_note_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    file_path = vault_root / note["path"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="vault file missing")

    return {**note, "content": file_path.read_text()}
