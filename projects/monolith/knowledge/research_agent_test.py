"""Tests for the Qwen-driven research agent."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from knowledge.frontmatter import ParsedFrontmatter
from knowledge.research_agent import (
    Claim,  # noqa: F401  (asserted via ResearchNote.claims item construction below)
    ResearchDeps,
    ResearchNote,
    SourceEntry,  # noqa: F401  (returned indirectly via derive_sources_bundle)
    create_research_agent,
    derive_sources_bundle,
)
from knowledge.store import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixture (duplicated from research_tools_test.py — see Task 4 reviewer note;
# promotion to a shared conftest was deferred since knowledge/ has no top-level
# conftest and existing knowledge tests inline their seed-data fixtures).
# ---------------------------------------------------------------------------


@pytest.fixture(name="session_with_seeded_notes")
def session_with_seeded_notes_fixture():
    """In-memory sqlite session pre-seeded with a few vault notes."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas: dict[str, str] = {}
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


def _seen_tool_names(messages: list) -> set[str]:
    """Inspect message history for which tools have already returned."""
    names: set[str] = set()
    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            if isinstance(part, ToolReturnPart):
                names.add(part.tool_name)
    return names


# ---------------------------------------------------------------------------
# Agent end-to-end via FunctionModel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_research_agent_runs_to_completion_with_function_model(
    tmp_path, session_with_seeded_notes, monkeypatch
):
    """A FunctionModel that drives three tool calls then a structured output.

    Stages:
        1. (no tools seen) -> request web_search
        2. (web_search seen) -> request web_fetch
        3. (web_fetch seen) -> request search_knowledge
        4. (search_knowledge seen) -> emit final_result with the ResearchNote

    final_result is the implicit output tool produced by ``output_type=ResearchNote``;
    a TextPart fallback is never reached because the agent commits via the tool call.
    """

    # Stub the knowledge store's vector-search and the web layer so the tool bodies
    # execute against deterministic data without touching network or pgvector.
    async def fake_embed(self, _text):
        return [0.0] * 1024

    monkeypatch.setattr(
        "shared.embedding.EmbeddingClient.embed", fake_embed, raising=True
    )
    monkeypatch.setattr(
        KnowledgeStore,
        "search_notes_with_context",
        lambda self, query_embedding, limit=5: [
            {
                "note_id": "n0",
                "title": "Merkle Tree",
                "path": "merkle-tree.md",
                "type": "concept",
                "tags": [],
                "score": 0.9,
                "section": "## Overview",
                "snippet": "Merkle tree is a hash tree used for verification.",
                "edges": [],
            }
        ],
    )

    async def fake_web_search(query: str, base_url: str | None = None) -> str:
        return "**Merkle (Wikipedia)**\nA hash tree.\nURL: https://example.com/m"

    async def fake_web_fetch(url: str):
        from knowledge.research_tools import WebFetchResult

        return WebFetchResult(
            url=url,
            body="Merkle trees are binary trees of hashes.",
            content_hash="sha256:deadbeef",
            fetched_at="2026-04-25T09:00:00Z",
            truncated=False,
        )

    monkeypatch.setattr(
        "knowledge.research_agent._web_search_impl", fake_web_search, raising=True
    )
    monkeypatch.setattr(
        "knowledge.research_agent._web_fetch_impl", fake_web_fetch, raising=True
    )

    async def fake_model(messages, info):
        seen = _seen_tool_names(messages)
        if "web_search" not in seen:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="web_search",
                        args={"query": "merkle tree"},
                        tool_call_id="c1",
                    )
                ]
            )
        if "web_fetch" not in seen:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="web_fetch",
                        args={"url": "https://example.com/m"},
                        tool_call_id="c2",
                    )
                ]
            )
        if "search_knowledge" not in seen:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search_knowledge",
                        args={"query": "merkle"},
                        tool_call_id="c3",
                    )
                ]
            )
        # Commit the structured output via the implicit final_result tool.
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args={
                        "summary": "A Merkle tree is a hash tree used to verify data integrity.",
                        "claims": [
                            {
                                "text": "A Merkle tree hashes leaves pairwise up to a root."
                            }
                        ],
                    },
                    tool_call_id="cf",
                )
            ]
        )

    agent = create_research_agent(model=FunctionModel(fake_model))
    deps = ResearchDeps(session=session_with_seeded_notes, vault_root=tmp_path)
    result = await agent.run("Research: merkle tree", deps=deps)

    assert isinstance(result.output, ResearchNote)
    assert result.output.claims
    assert result.output.claims[0].text.startswith("A Merkle tree")


# ---------------------------------------------------------------------------
# derive_sources_bundle — pure parsing of tool-call audit trail
# ---------------------------------------------------------------------------


def test_derive_sources_bundle_extracts_tool_calls():
    """Sources bundle is reconstructed from tool-call audit trail, not from prose."""
    history = [
        ToolCallPart(tool_name="web_fetch", args={"url": "https://a.com"}),
        ToolReturnPart(
            tool_name="web_fetch",
            content={
                "url": "https://a.com",
                "content_hash": "sha256:abc",
                "fetched_at": "2026-04-25T09:00:00Z",
                "skipped_reason": None,
            },
        ),
        ToolCallPart(tool_name="search_knowledge", args={"query": "x"}),
        ToolReturnPart(
            tool_name="search_knowledge", content={"note_ids": ["n1", "n2"]}
        ),
        ToolCallPart(tool_name="web_search", args={"query": "x explained"}),
        ToolReturnPart(
            tool_name="web_search",
            content="**Title**\nsnippet\nURL: https://b.com\n\n**T2**\ns2\nURL: https://c.com",
        ),
    ]

    bundle = derive_sources_bundle(history)

    kinds = [s.tool for s in bundle]
    assert "web_fetch" in kinds
    assert "search_knowledge" in kinds
    assert "web_search" in kinds

    fetch = next(s for s in bundle if s.tool == "web_fetch")
    assert fetch.url == "https://a.com"
    assert fetch.content_hash == "sha256:abc"

    skg = next(s for s in bundle if s.tool == "search_knowledge")
    assert skg.note_ids == ["n1", "n2"]

    ws = next(s for s in bundle if s.tool == "web_search")
    assert "https://b.com" in ws.result_urls
    assert "https://c.com" in ws.result_urls
