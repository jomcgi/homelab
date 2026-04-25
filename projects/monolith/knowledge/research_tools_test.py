"""Tests for the three Pydantic AI tools used by the research agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.research_tools import (
    MAX_FETCH_BYTES,
    WEB_FETCH_TIMEOUT_SECS,
    WebFetchResult,
    web_fetch,
)
from knowledge.store import KnowledgeStore


@pytest.mark.asyncio
async def test_web_fetch_returns_body_and_content_hash():
    """web_fetch returns (url, body, content_hash, fetched_at)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>hello world</p></body></html>",
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/foo")

    assert isinstance(result, WebFetchResult)
    assert result.url == "https://example.com/foo"
    assert "hello world" in result.body
    assert result.content_hash.startswith("sha256:")
    assert result.fetched_at.endswith("Z")


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_text_content_types():
    """Binary/PDF/etc bodies are not synthesizable; return a clear empty result."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/foo.pdf")

    assert result.body == ""
    assert result.skipped_reason == "non-text content-type: application/pdf"


@pytest.mark.asyncio
async def test_web_fetch_truncates_at_max_bytes():
    """Bodies larger than MAX_FETCH_BYTES are truncated, not rejected."""
    big_body = "x" * (MAX_FETCH_BYTES * 2)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text=big_body
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/big")

    assert len(result.body) == MAX_FETCH_BYTES
    assert result.truncated is True


@pytest.mark.asyncio
async def test_web_fetch_handles_timeout():
    """A timeout returns a result with empty body and a skipped_reason."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/slow")

    assert result.body == ""
    assert "timed out" in (result.skipped_reason or "").lower()


@pytest.mark.asyncio
async def test_web_fetch_handles_non_200():
    """Non-200 responses produce a skipped_reason rather than raising."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/missing")

    assert result.body == ""
    assert "404" in (result.skipped_reason or "")


# ---------------------------------------------------------------------------
# search_knowledge + web_search
# ---------------------------------------------------------------------------


@pytest.fixture(name="session_with_seeded_notes")
def session_with_seeded_notes_fixture():
    """In-memory sqlite session pre-seeded with a few vault notes.

    Mirrors the seeding approach used in ``store_test.py``: clears the
    schema attribute on ``SQLModel`` tables (Postgres-only ``knowledge``
    schema is not supported by sqlite), creates the tables, and uses
    ``KnowledgeStore.upsert_note`` to insert 3 notes. Vector search
    (``search_notes_with_context``) requires pgvector and is mocked in
    callers — the seeding here gives the test real ``note_id`` values to
    assert against.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            store = KnowledgeStore(session=session)
            for i, title in enumerate(["Merkle Tree", "Hash Chain", "Bloom Filter"]):
                store.upsert_note(
                    note_id=f"n{i}",
                    path=f"{title.lower().replace(' ', '-')}.md",
                    content_hash=f"h{i}",
                    title=title,
                    metadata=ParsedFrontmatter(title=title, type="concept"),
                    chunks=[
                        {
                            "index": 0,
                            "section_header": "## Overview",
                            "text": f"{title} explained briefly.",
                        }
                    ],
                    vectors=[[0.0] * 1024],
                    links=[],
                )
            yield session
    finally:
        for table in SQLModel.metadata.tables.values():
            if table.name in original_schemas:
                table.schema = original_schemas[table.name]


@pytest.mark.asyncio
async def test_search_knowledge_returns_top_n_excerpts():
    """search_knowledge wraps KnowledgeStore.search_notes_with_context and
    formats the rows as ``**title** (id=<id>, type=<type>)\\n<snippet>`` blocks
    joined by a blank line — the exact text the research agent receives."""
    from knowledge.research_tools import search_knowledge

    canned = [
        {
            "note_id": "n0",
            "title": "Merkle Tree",
            "path": "merkle-tree.md",
            "type": "atom",
            "tags": ["crypto"],
            "score": 0.92,
            "section": "## Overview",
            "snippet": "A Merkle tree hashes leaves pairwise up to a root.",
            "edges": [],
        },
        {
            "note_id": "n1",
            "title": "Hash Chain",
            "path": "hash-chain.md",
            "type": "atom",
            "tags": ["crypto"],
            "score": 0.71,
            "section": "## Overview",
            "snippet": "A hash chain links values via repeated hashing.",
            "edges": [],
        },
    ]
    mock_session = MagicMock()
    fake_embed = AsyncMock()
    fake_embed.embed = AsyncMock(return_value=[0.0] * 1024)

    with (
        patch("knowledge.research_tools.EmbeddingClient", return_value=fake_embed),
        patch.object(KnowledgeStore, "search_notes_with_context", return_value=canned),
    ):
        result = await search_knowledge(
            session=mock_session, query="merkle tree", limit=3
        )

    # Note ids preserved in source order for the sources_bundle.
    assert result.note_ids == ["n0", "n1"]

    # Text contract: exact format string + blank-line block separator.
    blocks = result.text.split("\n\n")
    assert len(blocks) == 2
    assert "**Merkle Tree**" in result.text
    assert "id=n0" in result.text
    assert "type=atom" in result.text
    assert "A Merkle tree hashes leaves pairwise up to a root." in result.text
    assert "**Hash Chain**" in result.text
    assert "id=n1" in result.text

    # The embedder was awaited with the user's query — guards against
    # accidental hardcoded text or empty-string regressions.
    fake_embed.embed.assert_awaited_once_with("merkle tree")


@pytest.mark.asyncio
async def test_search_knowledge_empty_results():
    """When the KG has no matches, search_knowledge returns an empty
    ``note_ids`` list and a fixed sentinel string. The literal is pinned
    because the research agent's prompt context depends on it."""
    from knowledge.research_tools import search_knowledge

    mock_session = MagicMock()
    fake_embed = AsyncMock()
    fake_embed.embed = AsyncMock(return_value=[0.0] * 1024)

    with (
        patch("knowledge.research_tools.EmbeddingClient", return_value=fake_embed),
        patch.object(KnowledgeStore, "search_notes_with_context", return_value=[]),
    ):
        result = await search_knowledge(
            session=mock_session, query="totally unknown term", limit=5
        )

    assert result.note_ids == []
    assert result.text == "(no matching vault notes)"


def test_web_search_re_exported():
    """web_search is the same callable as chat.web_search.search_web — same
    SearXNG instance, same headers, same trimming."""
    from knowledge.research_tools import web_search
    from chat.web_search import search_web

    assert web_search is search_web
