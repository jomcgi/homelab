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
        ToolCallPart(
            tool_name="web_fetch", args={"url": "https://a.com"}, tool_call_id="t1"
        ),
        ToolReturnPart(
            tool_name="web_fetch",
            content={
                "url": "https://a.com",
                "content_hash": "sha256:abc",
                "fetched_at": "2026-04-25T09:00:00Z",
                "skipped_reason": None,
            },
            tool_call_id="t1",
        ),
        ToolCallPart(
            tool_name="search_knowledge", args={"query": "x"}, tool_call_id="t2"
        ),
        ToolReturnPart(
            tool_name="search_knowledge",
            content={"note_ids": ["n1", "n2"]},
            tool_call_id="t2",
        ),
        ToolCallPart(
            tool_name="web_search", args={"query": "x explained"}, tool_call_id="t3"
        ),
        ToolReturnPart(
            tool_name="web_search",
            content="**Title**\nsnippet\nURL: https://b.com\n\n**T2**\ns2\nURL: https://c.com",
            tool_call_id="t3",
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


# ---------------------------------------------------------------------------
# derive_sources_bundle — production message shapes
# ---------------------------------------------------------------------------


def test_derive_sources_bundle_handles_production_modelmessage_shape():
    """Production callers pass ``result.all_messages()``: a list of
    ``ModelRequest``/``ModelResponse`` objects whose ``.parts`` carry the
    actual tool-call/return parts. The bundle must flatten and pair correctly,
    not silently return ``[]`` because the top-level items aren't bare parts.
    """
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart

    history = [
        ModelRequest(parts=[UserPromptPart(content="Research: merkle tree")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="web_fetch",
                    args={"url": "https://a.com"},
                    tool_call_id="abc",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="web_fetch",
                    content={
                        "url": "https://a.com",
                        "content_hash": "sha256:abc",
                        "fetched_at": "2026-04-25T09:00:00Z",
                        "skipped_reason": None,
                        "text": "URL: https://a.com\n\nbody",
                    },
                    tool_call_id="abc",
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="search_knowledge",
                    args={"query": "merkle"},
                    tool_call_id="def",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content={"text": "...", "note_ids": ["n0", "n1"]},
                    tool_call_id="def",
                )
            ]
        ),
    ]

    bundle = derive_sources_bundle(history)

    assert {s.tool for s in bundle} == {"web_fetch", "search_knowledge"}
    fetch = next(s for s in bundle if s.tool == "web_fetch")
    assert fetch.url == "https://a.com"
    assert fetch.content_hash == "sha256:abc"
    skg = next(s for s in bundle if s.tool == "search_knowledge")
    assert skg.note_ids == ["n0", "n1"]


# ---------------------------------------------------------------------------
# derive_sources_bundle — args delivered as JSON string (production shape)
# ---------------------------------------------------------------------------


def test_derive_sources_bundle_handles_json_string_args():
    """``ToolCallPart.args`` is a JSON string when populated by the OpenAI
    provider (``dtc.function.arguments``). The harness must use
    ``args_as_dict`` (or equivalent) so the URL/query is still extracted.
    """
    history = [
        ToolCallPart(
            tool_name="web_fetch",
            args='{"url": "https://a.com"}',
            tool_call_id="json1",
        ),
        ToolReturnPart(
            tool_name="web_fetch",
            # No url in content — proves the URL came from args, not content.
            content={
                "content_hash": "sha256:zz",
                "fetched_at": "2026-04-25T09:00:00Z",
                "skipped_reason": None,
            },
            tool_call_id="json1",
        ),
        ToolCallPart(
            tool_name="search_knowledge",
            args='{"query": "merkle tree"}',
            tool_call_id="json2",
        ),
        ToolReturnPart(
            tool_name="search_knowledge",
            content={"note_ids": ["n7"]},
            tool_call_id="json2",
        ),
    ]

    bundle = derive_sources_bundle(history)

    fetch = next(s for s in bundle if s.tool == "web_fetch")
    assert fetch.url == "https://a.com"
    assert fetch.content_hash == "sha256:zz"
    skg = next(s for s in bundle if s.tool == "search_knowledge")
    assert skg.query == "merkle tree"
    assert skg.note_ids == ["n7"]


# ---------------------------------------------------------------------------
# derive_sources_bundle — back-to-back same-tool calls pair by tool_call_id
# ---------------------------------------------------------------------------


def test_derive_sources_bundle_pairs_same_tool_back_to_back_by_id():
    """Two web_fetch calls in a row must pair each ToolReturnPart to its own
    ToolCallPart by ``tool_call_id`` -- a name-based lookup would either
    double-pair or pair with the wrong call.
    """
    history = [
        ToolCallPart(
            tool_name="web_fetch", args={"url": "https://first.com"}, tool_call_id="A"
        ),
        ToolCallPart(
            tool_name="web_fetch",
            args={"url": "https://second.com"},
            tool_call_id="B",
        ),
        ToolReturnPart(
            tool_name="web_fetch",
            content={"url": "https://second.com", "content_hash": "sha256:two"},
            tool_call_id="B",
        ),
        ToolReturnPart(
            tool_name="web_fetch",
            content={"url": "https://first.com", "content_hash": "sha256:one"},
            tool_call_id="A",
        ),
    ]

    bundle = derive_sources_bundle(history)

    assert len(bundle) == 2
    by_url = {s.url: s.content_hash for s in bundle}
    assert by_url == {
        "https://first.com": "sha256:one",
        "https://second.com": "sha256:two",
    }


# ---------------------------------------------------------------------------
# derive_sources_bundle — dict tool returns from production wrappers
# ---------------------------------------------------------------------------


def test_derive_sources_bundle_extracts_metadata_from_dict_tool_returns():
    """The wrappers in ``create_research_agent`` return dicts that carry both
    a synth-friendly ``text`` field and the citation metadata. The harness
    must read the metadata fields, not the ``text`` field.
    """
    history = [
        ToolCallPart(
            tool_name="web_fetch", args={"url": "https://x.com"}, tool_call_id="w1"
        ),
        ToolReturnPart(
            tool_name="web_fetch",
            content={
                "url": "https://x.com",
                "content_hash": "sha256:xx",
                "fetched_at": "2026-04-25T09:00:00Z",
                "truncated": False,
                "skipped_reason": None,
                "text": "URL: https://x.com\n\nbody text",
            },
            tool_call_id="w1",
        ),
        ToolCallPart(
            tool_name="search_knowledge",
            args={"query": "merkle"},
            tool_call_id="w2",
        ),
        ToolReturnPart(
            tool_name="search_knowledge",
            content={
                "text": "**Merkle Tree** (id=n0, type=concept)\nMerkle ...",
                "note_ids": ["n0", "n1"],
            },
            tool_call_id="w2",
        ),
    ]

    bundle = derive_sources_bundle(history)

    fetch = next(s for s in bundle if s.tool == "web_fetch")
    assert fetch.content_hash == "sha256:xx"
    assert fetch.fetched_at == "2026-04-25T09:00:00Z"

    skg = next(s for s in bundle if s.tool == "search_knowledge")
    assert skg.note_ids == ["n0", "n1"]
