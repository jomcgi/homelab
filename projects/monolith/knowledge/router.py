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
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from knowledge.gardener import Gardener
from knowledge.ingest_queue import IngestQueueItem
from knowledge.models import AtomRawProvenance, RawInput
from knowledge.service import DEFAULT_VAULT_ROOT, VAULT_ROOT_ENV
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
    note_id: str,
    session: Session = Depends(get_session),
) -> dict:
    store = KnowledgeStore(session)
    note = store.get_note_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)).resolve()
    resolved = (vault_root / note["path"]).resolve()
    if not resolved.is_relative_to(vault_root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="vault file missing")

    edges = store.get_note_links(note_id)
    return {**note, "content": resolved.read_text(), "edges": edges}


class IngestRequest(BaseModel):
    url: str
    source_type: Literal["youtube", "webpage"]


@router.post("/ingest", status_code=201)
def queue_ingest(
    data: IngestRequest,
    session: Session = Depends(get_session),
) -> dict:
    if not data.url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    item = IngestQueueItem(url=data.url.strip(), source_type=data.source_type)
    session.add(item)
    session.commit()
    return {"queued": True}


@router.get("/dead-letter")
def list_dead_letters(
    session: Session = Depends(get_session),
) -> dict:
    """List raws that have exhausted all retry attempts."""
    stmt = (
        select(RawInput, AtomRawProvenance)
        .join(AtomRawProvenance, AtomRawProvenance.raw_fk == RawInput.id)
        .where(AtomRawProvenance.derived_note_id == "failed")
        .where(AtomRawProvenance.retry_count >= Gardener._MAX_RETRIES)
    )
    results = session.exec(stmt).all()
    items = [
        {
            "id": raw.id,
            "path": raw.path,
            "source": raw.source,
            "error": prov.error,
            "retry_count": prov.retry_count,
            "last_failed_at": prov.created_at.isoformat(),
        }
        for raw, prov in results
    ]
    return {"items": items}


@router.post("/dead-letter/{raw_id}/replay")
def replay_dead_letter(
    raw_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Replay a dead-lettered raw by removing its failed provenance row."""
    raw = session.get(RawInput, raw_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="raw not found")

    prov = session.exec(
        select(AtomRawProvenance).where(
            AtomRawProvenance.raw_fk == raw_id,
            AtomRawProvenance.derived_note_id == "failed",
            AtomRawProvenance.retry_count >= Gardener._MAX_RETRIES,
        )
    ).first()
    if prov is None:
        raise HTTPException(status_code=404, detail="raw is not dead-lettered")

    session.delete(prov)
    session.commit()
    return {"replayed": True}
