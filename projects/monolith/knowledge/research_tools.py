"""Pydantic AI tools used by the research agent.

Three tools are exposed: ``web_fetch`` (new), ``web_search`` (re-exported
from ``chat.web_search``), and ``search_knowledge`` (a thin wrapper over
the existing knowledge KG search). All three are async and return
plain-text or structured results suitable for an LLM tool-call response.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlmodel import Session

from chat.web_search import search_web as web_search  # re-export, identity-equal
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_FETCH_BYTES",
    "WEB_FETCH_TIMEOUT_SECS",
    "SearchKnowledgeResult",
    "WebFetchResult",
    "search_knowledge",
    "web_fetch",
    "web_search",
]

WEB_FETCH_TIMEOUT_SECS = 15.0
MAX_FETCH_BYTES = 200_000  # ~50 pages of plain text; enough to synthesize from
_TEXTUAL_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
)


@dataclass(frozen=True)
class WebFetchResult:
    url: str
    body: str
    content_hash: str
    fetched_at: str
    truncated: bool = False
    skipped_reason: Optional[str] = None


def _build_client() -> httpx.AsyncClient:
    """Factory used by tests to mock-transport the client."""
    return httpx.AsyncClient(timeout=WEB_FETCH_TIMEOUT_SECS, follow_redirects=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def web_fetch(url: str) -> WebFetchResult:
    """Fetch a URL, returning at most MAX_FETCH_BYTES of decoded body text.

    Non-text content types are skipped (returned with empty body and a
    skipped_reason). Timeouts and non-200 responses also produce a
    skipped result rather than raising -- the agent loop should be able
    to continue with partial evidence.
    """
    client = _build_client()
    try:
        try:
            resp = await client.get(url)
        except httpx.TimeoutException as e:
            return WebFetchResult(
                url=url,
                body="",
                content_hash="",
                fetched_at=_now_iso(),
                skipped_reason=f"request timed out: {e}",
            )
        except httpx.HTTPError as e:
            return WebFetchResult(
                url=url,
                body="",
                content_hash="",
                fetched_at=_now_iso(),
                skipped_reason=f"http error: {e}",
            )

        if resp.status_code != 200:
            return WebFetchResult(
                url=url,
                body="",
                content_hash="",
                fetched_at=_now_iso(),
                skipped_reason=f"http {resp.status_code}",
            )

        ct = resp.headers.get("content-type", "")
        if not any(ct.startswith(prefix) for prefix in _TEXTUAL_CONTENT_TYPES):
            return WebFetchResult(
                url=url,
                body="",
                content_hash="",
                fetched_at=_now_iso(),
                skipped_reason=f"non-text content-type: {ct}",
            )

        body = resp.text
        truncated = False
        if len(body) > MAX_FETCH_BYTES:
            body = body[:MAX_FETCH_BYTES]
            truncated = True

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return WebFetchResult(
            url=url,
            body=body,
            content_hash=f"sha256:{digest}",
            fetched_at=_now_iso(),
            truncated=truncated,
        )
    finally:
        await client.aclose()


@dataclass(frozen=True)
class SearchKnowledgeResult:
    text: str
    note_ids: list[str]


async def search_knowledge(
    *, session: Session, query: str, limit: int = 5
) -> SearchKnowledgeResult:
    """Query the knowledge KG via vector search.

    Wraps :meth:`KnowledgeStore.search_notes_with_context` and formats the
    response as a tool-call return value the research agent can consume.
    Returns a small structured dataclass so the harness can also extract
    ``note_ids`` for the sources_bundle (without re-parsing the text).
    """
    embed_client = EmbeddingClient()
    vector = await embed_client.embed(query)

    store = KnowledgeStore(session)
    rows = store.search_notes_with_context(query_embedding=vector, limit=limit)
    if not rows:
        return SearchKnowledgeResult(text="(no matching vault notes)", note_ids=[])

    lines: list[str] = []
    note_ids: list[str] = []
    for row in rows:
        # search_notes_with_context returns dicts with keys: note_id, title,
        # path, type, tags, score, section, snippet, edges
        # (see store.py:289-304).
        note_ids.append(row["note_id"])
        lines.append(
            f"**{row['title']}** (id={row['note_id']}, type={row['type']})\n"
            f"{row['snippet']}"
        )
    return SearchKnowledgeResult(text="\n\n".join(lines), note_ids=note_ids)
