# External Research Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a scheduled research pipeline that drains `external+classified` gap stubs through a Qwen+Sonnet model spine and lands validated research notes in `_inbox/research/`, where the existing raw_ingest → reconciler → gardener pipeline produces atoms with proper provenance.

**Architecture:** New scheduled job `knowledge.research-gaps` runs every 5 minutes, batches 3 gaps per tick. For each gap: a Pydantic AI agent on local Qwen with three retrieval tools (`search_knowledge`, `web_search` via SearXNG, `web_fetch`) produces a `ResearchNote(summary, claims)`; the harness mechanically derives a sources bundle from the agent's tool-call audit trail; Sonnet (via `claude` CLI subprocess) validates per-claim; supported claims land as a `type: research` raw in `_inbox/research/<slug>.md` (gap → `committed`); fully-rejected drafts go to `_failed_research/<slug>-<N>.md` with `research_attempts++`; gap parks at `attempts >= 3`. Infrastructure failures (Qwen/Sonnet down) revert state without burning attempts.

**Tech Stack:** Python 3.13, Pydantic AI on llama.cpp (OpenAI-compatible), `claude` CLI subprocess for Sonnet, httpx for `web_fetch`, SQLModel/SQLAlchemy, Atlas migrations, PyYAML, pytest, Bazel/BuildBuddy, Helm/ArgoCD.

**Worktree:** `/tmp/claude-worktrees/external-research-pipeline` on `feat/external-research-pipeline` off `1ca4b7dfe`.

**Design doc:** `docs/plans/2026-04-25-external-research-pipeline-design.md` — read this for the why behind each decision.

---

## Repo conventions every implementer must respect

- **Commit messages:** Conventional Commits (`fix:`, `feat:`, `chore:`, `test:`, `refactor:`). A `commit-msg` hook enforces this.
- **Do NOT run tests locally.** No `pytest`, no `bb remote test`, no `bazel test`. The BuildBuddy `workflows` pool has no darwin runners and the linux fallback is too unreliable for an inner loop. **Implement, format, commit. The CI run on push verifies.** TDD discipline still applies (write failing test first, then implementation), but verification of red→green happens at end-of-plan when CI runs on the pushed branch. The "Step N: Run test to verify it fails/passes" lines below are _intent_ statements — verification is deferred to CI.
- **Format before commit:** run `format` (vendored shell alias) once after Python changes — runs ruff + gazelle and may touch BUILD files. If `format` is not on PATH, fall back to `bazel/tools/format/fast-format.sh` from the repo root. Stash unrelated noise (`git stash push -u`) before committing your task — only commit files relevant to the task.
- **Atlas checksum:** the `Update Atlas migration checksums` pre-commit hook updates `chart/migrations/atlas.sum` automatically when you stage a new SQL migration. Don't compute the hash by hand.
- **Worktree boundary:** every change must land in `/tmp/claude-worktrees/external-research-pipeline`. Never commit to `~/repos/homelab` directly.
- **Claude calls use the `claude` CLI subprocess pattern**, not the Anthropic Python SDK. This keeps usage on Joe's Claude Max subscription billing rather than a separate Anthropic API account. Mirror `projects/monolith/knowledge/gap_classifier.py:classify_stubs` for the subprocess invocation pattern (HOME=/tmp env override, asyncio.create_subprocess_exec, timeout handling).

## Verification model

Each task ships with TDD-shaped instructions (write test first, then implementation), but the **only place tests actually execute is BuildBuddy CI** after the branch is pushed. Implementer subagents:

1. Write the failing test as specified.
2. Write the implementation as specified.
3. Format + commit.
4. **Do not** invoke `bb remote test` / `bazel test` / `pytest`.

Spec and code-quality reviewers review the diff against the spec; they do not run tests either. After all tasks land, a final task pushes the branch, opens the PR, and monitors the CI run for the actual red/green signal.

---

## Task 1: Migration — add `Gap.research_attempts` column

**Files:**

- Create: `projects/monolith/chart/migrations/20260425030000_knowledge_gaps_research_attempts.sql`
- Modify: `projects/monolith/chart/migrations/atlas.sum` (auto-updated by pre-commit hook)

**Step 1: Write the migration.**

Create `projects/monolith/chart/migrations/20260425030000_knowledge_gaps_research_attempts.sql`:

```sql
-- knowledge.gaps: track research attempt count for the external research
-- pipeline. After 3 consecutive Sonnet rejections, the research worker
-- parks the gap (state='parked'). See
-- docs/plans/2026-04-25-external-research-pipeline-design.md.
ALTER TABLE knowledge.gaps
  ADD COLUMN research_attempts INTEGER NOT NULL DEFAULT 0;
```

**Step 2: Stage and commit.**

```bash
cd /tmp/claude-worktrees/external-research-pipeline
git add projects/monolith/chart/migrations/20260425030000_knowledge_gaps_research_attempts.sql \
        projects/monolith/chart/migrations/atlas.sum
git commit -m "feat(knowledge): add research_attempts column to gaps table"
```

The pre-commit hook will populate `atlas.sum` automatically; if `atlas.sum` is not staged at commit time, re-run `git add` and re-commit.

---

## Task 2: Update `Gap` SQLModel + new state values

**Files:**

- Modify: `projects/monolith/knowledge/models.py` (Gap class — add `research_attempts` field)
- Modify: `projects/monolith/knowledge/gap_model_test.py` (add field-presence test, new state value tests)

**Step 1: Write the failing tests.**

Add to `gap_model_test.py`:

```python
def test_gap_has_research_attempts_field_default_zero(session):
    """research_attempts defaults to 0 and is non-nullable."""
    from knowledge.models import Gap

    gap = Gap(term="x", note_id="x", pipeline_version="test")
    session.add(gap)
    session.commit()

    fetched = session.execute(select(Gap).where(Gap.term == "x")).scalar_one()
    assert fetched.research_attempts == 0


def test_gap_research_attempts_increments(session):
    """research_attempts is a normal int column — bump and persist."""
    from knowledge.models import Gap

    gap = Gap(term="x", note_id="x", pipeline_version="test")
    session.add(gap)
    session.commit()

    gap.research_attempts = 2
    session.commit()

    fetched = session.execute(select(Gap).where(Gap.term == "x")).scalar_one()
    assert fetched.research_attempts == 2


def test_gap_state_accepts_research_pipeline_values(session):
    """New state values from the research pipeline are not constrained at the
    SQLModel layer — accept researching/committed/parked alongside the
    existing classifier states."""
    from knowledge.models import Gap

    for state in ("researching", "committed", "parked"):
        gap = Gap(term=f"x-{state}", note_id=f"x-{state}", state=state, pipeline_version="test")
        session.add(gap)
    session.commit()

    rows = session.execute(select(Gap)).scalars().all()
    states = {r.state for r in rows}
    assert {"researching", "committed", "parked"}.issubset(states)
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — `research_attempts` field does not exist on `Gap`.

**Step 3: Update the SQLModel.**

In `projects/monolith/knowledge/models.py`, find the `Gap` class. Add the field between the existing `state` field and `__table_args__`:

```python
    research_attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
```

(`Integer` and `Column` should already be imported alongside the other SQLAlchemy column types — if not, add the imports.)

**Step 4: Run tests to verify they pass (intent).**

Expected: PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/models.py projects/monolith/knowledge/gap_model_test.py
git commit -m "feat(knowledge): add research_attempts field to Gap model"
```

---

## Task 3: `research_tools.py` — `web_fetch`

**Files:**

- Create: `projects/monolith/knowledge/research_tools.py`
- Create: `projects/monolith/knowledge/research_tools_test.py`
- Modify: `projects/monolith/BUILD` (add `knowledge_research_tools_test` py_test target)

**Why first:** `web_fetch` is the simplest new tool, with no model/LLM dependencies, so it's a clean kickoff that validates the test-mocking approach (httpx) before the more complex Pydantic AI plumbing in Task 5.

**Step 1: Write the failing tests.**

`research_tools_test.py`:

```python
"""Tests for the three Pydantic AI tools used by the research agent."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from knowledge.research_tools import (
    MAX_FETCH_BYTES,
    WEB_FETCH_TIMEOUT_SECS,
    WebFetchResult,
    web_fetch,
)


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
        build.return_value = httpx.AsyncClient(transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS)
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
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS)
        result = await web_fetch("https://example.com/foo.pdf")

    assert result.body == ""
    assert result.skipped_reason == "non-text content-type: application/pdf"


@pytest.mark.asyncio
async def test_web_fetch_truncates_at_max_bytes():
    """Bodies larger than MAX_FETCH_BYTES are truncated, not rejected."""
    big_body = "x" * (MAX_FETCH_BYTES * 2)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, text=big_body)

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS)
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
        build.return_value = httpx.AsyncClient(transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS)
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
        build.return_value = httpx.AsyncClient(transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS)
        result = await web_fetch("https://example.com/missing")

    assert result.body == ""
    assert "404" in (result.skipped_reason or "")
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL with `ModuleNotFoundError: No module named 'knowledge.research_tools'`.

**Step 3: Implement `web_fetch`.**

Create `projects/monolith/knowledge/research_tools.py`:

```python
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

logger = logging.getLogger(__name__)

WEB_FETCH_TIMEOUT_SECS = 15.0
MAX_FETCH_BYTES = 200_000  # ~50 pages of plain text; enough to synthesize from
_TEXTUAL_CONTENT_TYPES = ("text/", "application/json", "application/xml", "application/xhtml+xml")


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
    skipped result rather than raising — the agent loop should be able
    to continue with partial evidence.
    """
    client = _build_client()
    try:
        try:
            resp = await client.get(url)
        except httpx.TimeoutException as e:
            return WebFetchResult(
                url=url, body="", content_hash="", fetched_at=_now_iso(),
                skipped_reason=f"request timed out: {e}",
            )
        except httpx.HTTPError as e:
            return WebFetchResult(
                url=url, body="", content_hash="", fetched_at=_now_iso(),
                skipped_reason=f"http error: {e}",
            )

        if resp.status_code != 200:
            return WebFetchResult(
                url=url, body="", content_hash="", fetched_at=_now_iso(),
                skipped_reason=f"http {resp.status_code}",
            )

        ct = resp.headers.get("content-type", "")
        if not any(ct.startswith(prefix) for prefix in _TEXTUAL_CONTENT_TYPES):
            return WebFetchResult(
                url=url, body="", content_hash="", fetched_at=_now_iso(),
                skipped_reason=f"non-text content-type: {ct}",
            )

        body = resp.text
        truncated = False
        if len(body) > MAX_FETCH_BYTES:
            body = body[:MAX_FETCH_BYTES]
            truncated = True

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return WebFetchResult(
            url=url, body=body, content_hash=f"sha256:{digest}",
            fetched_at=_now_iso(), truncated=truncated,
        )
    finally:
        await client.aclose()
```

**Step 4: Add a BUILD target.**

Mirror an existing knowledge test target. In `projects/monolith/BUILD`, find an existing `py_test` named e.g. `knowledge_gap_stubs_test` and add a sibling target plus a `py_library` for the new module.

**Step 5: Run tests to verify they pass (intent).**

Expected: 5 tests PASS.

**Step 6: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_tools.py \
        projects/monolith/knowledge/research_tools_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add web_fetch tool for research agent"
```

---

## Task 4: `research_tools.py` — `search_knowledge` + `web_search` re-export

**Files:**

- Modify: `projects/monolith/knowledge/research_tools.py` (add `search_knowledge`, re-export `web_search`)
- Modify: `projects/monolith/knowledge/research_tools_test.py` (add tests)

**Step 1: Write the failing tests.**

Add to `research_tools_test.py`:

```python
@pytest.mark.asyncio
async def test_search_knowledge_returns_top_n_excerpts(session_with_seeded_notes):
    """search_knowledge wraps KnowledgeStore.search_notes_with_context and returns
    a tool-friendly text response for the agent to consume."""
    from knowledge.research_tools import search_knowledge

    result = await search_knowledge(session=session_with_seeded_notes, query="merkle tree", limit=3)

    assert result.note_ids  # non-empty when seeded
    assert len(result.note_ids) <= 3
    assert isinstance(result.text, str) and result.text


def test_web_search_re_exported():
    """web_search is the same callable as chat.web_search.search_web — same
    SearXNG instance, same headers, same trimming."""
    from knowledge.research_tools import web_search
    from chat.web_search import search_web

    assert web_search is search_web
```

The `session_with_seeded_notes` fixture should match the existing convention used in `store_gap_queries_test.py`. If a comparable fixture exists, reuse it; otherwise add one to `research_tools_test.py` that seeds 2-3 notes via `KnowledgeStore.upsert_note`.

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — `search_knowledge`, `web_search` not yet exported.

**Step 3: Extend `research_tools.py`.**

Append to `projects/monolith/knowledge/research_tools.py`:

```python
from chat.web_search import search_web as web_search  # re-export, identity-equal

from sqlmodel import Session

from knowledge.store import KnowledgeStore


@dataclass(frozen=True)
class SearchKnowledgeResult:
    text: str
    note_ids: list[str]


async def search_knowledge(*, session: Session, query: str, limit: int = 5) -> SearchKnowledgeResult:
    """Query the knowledge KG via vector search.

    Wraps ``KnowledgeStore.search_notes_with_context`` and formats the
    response as a tool-call return value the research agent can consume.
    Returns a small structured dataclass so the harness can also extract
    note_ids for the sources_bundle (without re-parsing the text).
    """
    store = KnowledgeStore(session)
    rows = store.search_notes_with_context(query=query, limit=limit)
    if not rows:
        return SearchKnowledgeResult(text="(no matching vault notes)", note_ids=[])

    lines = []
    note_ids: list[str] = []
    for row in rows:
        # row shape: depends on what search_notes_with_context returns; check
        # store.py for the exact row type and fields. Adjust as needed.
        note_ids.append(row.note_id)
        lines.append(
            f"**{row.title}** (id={row.note_id}, type={row.type})\n{row.snippet}"
        )
    return SearchKnowledgeResult(text="\n\n".join(lines), note_ids=note_ids)
```

(Adjust the row-unpacking based on the actual return shape of `search_notes_with_context` — read `projects/monolith/knowledge/store.py:189-310` to confirm. The pattern is the same regardless of exact field names.)

**Step 4: Run tests to verify they pass (intent).**

Expected: 7 tests PASS (5 from Task 3 + 2 new).

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_tools.py \
        projects/monolith/knowledge/research_tools_test.py
git commit -m "feat(knowledge): add search_knowledge + web_search tools for research agent"
```

---

## Task 5: `research_agent.py` — Pydantic AI agent factory

**Files:**

- Create: `projects/monolith/knowledge/research_agent.py`
- Create: `projects/monolith/knowledge/research_agent_test.py`
- Modify: `projects/monolith/BUILD`

**Step 1: Write the failing test.**

`research_agent_test.py`:

```python
"""Tests for the Qwen-driven research agent."""

from __future__ import annotations

import pytest

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from knowledge.research_agent import (
    Claim,
    ResearchDeps,
    ResearchNote,
    SourceEntry,
    create_research_agent,
    derive_sources_bundle,
)


@pytest.mark.asyncio
async def test_create_research_agent_runs_to_completion_with_function_model(tmp_path, session_with_seeded_notes):
    """A FunctionModel that returns a structured ResearchNote drives the agent loop end-to-end."""
    async def fake_model(messages, info):
        # Simulate one tool call to web_search, one to web_fetch, one to
        # search_knowledge, then return the structured ResearchNote.
        if not info.tool_calls:
            return ModelResponse(parts=[
                ToolCallPart(tool_name="web_search", args={"query": "merkle tree"}),
                ToolCallPart(tool_name="web_fetch", args={"url": "https://example.com/m"}),
                ToolCallPart(tool_name="search_knowledge", args={"query": "merkle"}),
            ])
        return ModelResponse(parts=[TextPart(content='{"summary":"...","claims":[{"text":"X is Y"}]}')])

    agent = create_research_agent(model=FunctionModel(fake_model))
    deps = ResearchDeps(session=session_with_seeded_notes, vault_root=tmp_path)
    result = await agent.run("Research: merkle tree", deps=deps)

    assert isinstance(result.output, ResearchNote)
    assert result.output.claims


def test_derive_sources_bundle_extracts_tool_calls():
    """Sources bundle is reconstructed from tool-call audit trail, not from prose."""
    history = [
        ToolCallPart(tool_name="web_fetch", args={"url": "https://a.com"}),
        ToolReturnPart(tool_name="web_fetch", content={
            "url": "https://a.com",
            "content_hash": "sha256:abc",
            "fetched_at": "2026-04-25T09:00:00Z",
            "skipped_reason": None,
        }),
        ToolCallPart(tool_name="search_knowledge", args={"query": "x"}),
        ToolReturnPart(tool_name="search_knowledge", content={"note_ids": ["n1", "n2"]}),
        ToolCallPart(tool_name="web_search", args={"query": "x explained"}),
        ToolReturnPart(tool_name="web_search", content="**Title**\nsnippet\nURL: https://b.com\n\n**T2**\ns2\nURL: https://c.com"),
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
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — module missing.

**Step 3: Implement the agent module.**

Create `projects/monolith/knowledge/research_agent.py`:

```python
"""Qwen-driven research agent (Pydantic AI on llama.cpp).

Mirrors chat/agent.py shape but with a research-focused system prompt,
three retrieval tools, and a structured ResearchNote output type.
Sources are reconstructed mechanically from the agent's tool-call audit
trail (see derive_sources_bundle) — Qwen's prose is never trusted to
faithfully list its own citations.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel import Session

from knowledge.research_tools import (
    SearchKnowledgeResult,
    WebFetchResult,
    search_knowledge as _search_knowledge_impl,
    web_fetch as _web_fetch_impl,
    web_search as _web_search_impl,
)

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "http://llama-cpp.llama-cpp.svc.cluster.local:8080")
QWEN_MODEL_ID = "qwen3.6-27b"
PIPELINE_VERSION = "research-pipeline@v1"


_RESEARCH_SYSTEM_PROMPT = """\
You are a research agent for a knowledge graph. Your job is to research a
single term — referenced in the user's vault but not yet defined — and
produce a structured ResearchNote.

You have three tools:

- **search_knowledge(query)** — query the user's existing vault notes.
  Use this FIRST. The user's prior thinking is more trusted than any web
  source.
- **web_search(query)** — search the open web (SearXNG). Returns titles,
  snippets, and URLs.
- **web_fetch(url)** — fetch a single URL's body. Use this to get the
  actual page content for the URLs that look most relevant from
  web_search results. Snippets alone are not enough to substantiate
  claims.

## Output

Return a ResearchNote with:
- ``summary`` (3-5 sentences): what the term means and why it matters.
- ``claims`` (list of Claim): each claim is one factual statement
  attributable to the evidence you retrieved. Only make a claim if you
  retrieved evidence supporting it. Quality over quantity — 3 strong
  claims is better than 8 weak ones.

Do NOT invent citations. The harness records every tool call you make
and reconstructs the sources bundle automatically — your job is just to
produce supportable claims.
"""


class Claim(BaseModel):
    text: str = Field(description="A single factual claim about the term.")


class ResearchNote(BaseModel):
    summary: str
    claims: list[Claim] = Field(default_factory=list)


@dataclass
class ResearchDeps:
    session: Session
    vault_root: Path


@dataclass(frozen=True)
class SourceEntry:
    tool: str  # "web_fetch" | "web_search" | "search_knowledge"
    url: str | None = None
    content_hash: str | None = None
    fetched_at: str | None = None
    query: str | None = None
    note_ids: list[str] = field(default_factory=list)
    result_urls: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def create_research_agent(*, model: Any | None = None, base_url: str | None = None) -> Agent[ResearchDeps, ResearchNote]:
    """Build the Pydantic AI agent. Pass an explicit ``model`` (e.g.
    pydantic_ai.models.function.FunctionModel) to drive a deterministic
    test loop; otherwise the default Qwen-on-llama.cpp model is used.
    """
    if model is None:
        url = base_url or LLAMA_CPP_URL
        model = OpenAIChatModel(
            QWEN_MODEL_ID,
            provider=OpenAIProvider(base_url=f"{url}/v1", api_key="not-needed"),
        )

    agent: Agent[ResearchDeps, ResearchNote] = Agent(
        model,
        deps_type=ResearchDeps,
        output_type=ResearchNote,
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        model_settings=ModelSettings(
            temperature=0.4,  # lower than chat — research is less creative
            top_p=0.95,
        ),
    )

    @agent.tool
    async def search_knowledge(ctx: RunContext[ResearchDeps], query: str, limit: int = 5) -> str:
        """Query the user's vault for notes matching ``query``. Use first."""
        result = await _search_knowledge_impl(session=ctx.deps.session, query=query, limit=limit)
        return result.text

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the open web. Returns titles + snippets + URLs."""
        return await _web_search_impl(query)

    @agent.tool_plain
    async def web_fetch(url: str) -> str:
        """Fetch a single URL's body. Use after web_search picks a candidate."""
        result = await _web_fetch_impl(url)
        if result.skipped_reason:
            return f"(skipped {url}: {result.skipped_reason})"
        truncated_note = " (truncated)" if result.truncated else ""
        return f"URL: {result.url}{truncated_note}\n\n{result.body}"

    return agent


_URL_RE = re.compile(r"URL:\s*(https?://\S+)")


def derive_sources_bundle(message_history: list[Any]) -> list[SourceEntry]:
    """Reconstruct the sources bundle from the agent's tool-call audit trail.

    Walks the message history pairing ``ToolCallPart`` with the matching
    ``ToolReturnPart``. Knows the shapes of each tool's return value:
    - web_fetch returns the WebFetchResult (or its text rendering).
    - search_knowledge returns either the SearchKnowledgeResult or its text.
    - web_search returns a markdown-ish string with ``URL: <url>`` lines.

    The harness is the source of truth for citations — Qwen's prose
    output is never inspected for source attribution.
    """
    from pydantic_ai.messages import ToolCallPart, ToolReturnPart

    sources: list[SourceEntry] = []
    pending: dict[int, ToolCallPart] = {}
    for i, part in enumerate(message_history):
        if isinstance(part, ToolCallPart):
            pending[i] = part
        elif isinstance(part, ToolReturnPart):
            call = next((c for k, c in reversed(pending.items()) if c.tool_name == part.tool_name), None)
            if call is None:
                continue
            sources.append(_extract_source_entry(call, part))

    return sources


def _extract_source_entry(call: Any, ret: Any) -> SourceEntry:
    name = call.tool_name
    args = getattr(call, "args", {}) or {}
    content = getattr(ret, "content", None)

    if name == "web_fetch":
        url = args.get("url", "")
        if isinstance(content, dict):
            return SourceEntry(
                tool="web_fetch",
                url=content.get("url") or url,
                content_hash=content.get("content_hash"),
                fetched_at=content.get("fetched_at"),
                skipped_reason=content.get("skipped_reason"),
            )
        return SourceEntry(tool="web_fetch", url=url)

    if name == "search_knowledge":
        if isinstance(content, dict):
            return SourceEntry(
                tool="search_knowledge",
                query=args.get("query"),
                note_ids=list(content.get("note_ids", [])),
            )
        return SourceEntry(tool="search_knowledge", query=args.get("query"))

    if name == "web_search":
        urls: list[str] = []
        if isinstance(content, str):
            urls = _URL_RE.findall(content)
        return SourceEntry(tool="web_search", query=args.get("query"), result_urls=urls)

    return SourceEntry(tool=name)
```

**Step 4: Add BUILD targets.**

Mirror Task 3's pattern for `knowledge_research_agent` and `knowledge_research_agent_test`.

**Step 5: Run tests to verify they pass (intent).**

Expected: 2 tests PASS.

**Step 6: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_agent.py \
        projects/monolith/knowledge/research_agent_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add Qwen research agent with three retrieval tools"
```

---

## Task 6: `research_validator.py` — Sonnet-driven per-claim verifier

**Files:**

- Create: `projects/monolith/knowledge/research_validator.py`
- Create: `projects/monolith/knowledge/research_validator_test.py`
- Modify: `projects/monolith/BUILD`

**Step 1: Write the failing tests.**

`research_validator_test.py`:

````python
"""Tests for the Sonnet-driven per-claim research validator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_validator import (
    VALIDATOR_VERSION,
    ValidatedClaim,
    ValidatedResearch,
    validate_research,
)


@pytest.mark.asyncio
async def test_validate_research_parses_per_claim_verdicts():
    """Sonnet returns JSON; we parse it into ValidatedResearch."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y."), Claim(text="X is Z.")])
    sources = [SourceEntry(tool="web_fetch", url="https://example.com/x")]

    fake_stdout = json.dumps({
        "claims": [
            {"text": "X is Y.", "verdict": "supported", "reason": "directly stated in source"},
            {"text": "X is Z.", "verdict": "unsupported", "reason": "no source mentions Z"},
        ]
    }).encode()

    proc = AsyncMock()
    proc.communicate.return_value = (fake_stdout, b"")
    proc.returncode = 0
    with patch("knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc):
        result = await validate_research(note=note, sources=sources)

    assert isinstance(result, ValidatedResearch)
    assert len(result.claims) == 2
    assert result.claims[0].verdict == "supported"
    assert result.claims[1].verdict == "unsupported"


@pytest.mark.asyncio
async def test_validate_research_handles_subprocess_timeout():
    """Subprocess timeout returns ValidatedResearch with empty claims (treated as all-unsupported upstream)."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    proc = AsyncMock()
    proc.communicate.side_effect = TimeoutError()
    proc.kill = AsyncMock()
    proc.wait = AsyncMock()
    proc.returncode = -9
    with patch("knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc):
        with patch("knowledge.research_validator.asyncio.wait_for", side_effect=TimeoutError()):
            result = await validate_research(note=note, sources=[])

    assert result.timed_out is True
    assert result.claims == []


@pytest.mark.asyncio
async def test_validate_research_handles_malformed_json():
    """A non-JSON Sonnet response is parsed leniently — first JSON block, or empty."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    fake_stdout = b"Here are the verdicts:\n```json\n" + json.dumps({
        "claims": [{"text": "X is Y.", "verdict": "supported", "reason": "ok"}]
    }).encode() + b"\n```\nLet me know if you want anything else."

    proc = AsyncMock()
    proc.communicate.return_value = (fake_stdout, b"")
    proc.returncode = 0
    with patch("knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc):
        result = await validate_research(note=note, sources=[])

    assert len(result.claims) == 1
    assert result.claims[0].verdict == "supported"


@pytest.mark.asyncio
async def test_validate_research_handles_unparseable_response():
    """Total parse failure returns empty claims with parse_error set."""
    note = ResearchNote(summary="X is Y.", claims=[Claim(text="X is Y.")])

    proc = AsyncMock()
    proc.communicate.return_value = (b"I cannot help with that request.", b"")
    proc.returncode = 0
    with patch("knowledge.research_validator.asyncio.create_subprocess_exec", return_value=proc):
        result = await validate_research(note=note, sources=[])

    assert result.parse_error is not None
    assert result.claims == []


def test_validated_research_all_unsupported_helper():
    """ValidatedResearch.all_unsupported is the upstream branch signal."""
    none = ValidatedResearch(claims=[])
    assert none.all_unsupported is True

    all_un = ValidatedResearch(claims=[
        ValidatedClaim(text="x", verdict="unsupported", reason="r"),
        ValidatedClaim(text="y", verdict="speculative", reason="r"),
    ])
    assert all_un.all_unsupported is True

    mixed = ValidatedResearch(claims=[
        ValidatedClaim(text="x", verdict="supported", reason="r"),
        ValidatedClaim(text="y", verdict="unsupported", reason="r"),
    ])
    assert mixed.all_unsupported is False
````

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — module missing.

**Step 3: Implement the validator.**

Create `projects/monolith/knowledge/research_validator.py`:

````python
"""Sonnet-driven per-claim research validator (claude CLI subprocess).

Mirrors gap_classifier.py's subprocess pattern: Claude Max ToS-compliant,
HOME=/tmp env override, asyncio.wait_for timeout, stderr capture on
non-zero exit. Output is structured JSON parsed into ValidatedResearch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from knowledge.research_agent import Claim, ResearchNote, SourceEntry

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "sonnet-4-6@v1"

_VALIDATE_TIMEOUT_SECS = 180
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


_VALIDATOR_PROMPT = """\
You are validating a research note against the sources that were retrieved
during research. For each claim in the note, decide one of:

- **supported**: at least one source clearly substantiates the claim.
- **unsupported**: no source substantiates the claim. Treat hedged
  language ("may", "might", "is sometimes") strictly — if the source
  doesn't directly support it, mark unsupported.
- **speculative**: the source touches on the topic but doesn't actually
  back the claim as stated.

Respond with JSON ONLY, in this shape:

```json
{{"claims": [
  {{"text": "<claim text>", "verdict": "supported|unsupported|speculative", "reason": "<one sentence>"}}
]}}
````

Do not include any text outside the JSON block.

## Research note

Summary: {summary}

Claims:
{claims}

## Sources retrieved during research

{sources}
"""

Verdict = Literal["supported", "unsupported", "speculative"]

@dataclass(frozen=True)
class ValidatedClaim:
text: str
verdict: Verdict
reason: str

@dataclass(frozen=True)
class ValidatedResearch:
claims: list[ValidatedClaim] = field(default_factory=list)
timed_out: bool = False
parse_error: Optional[str] = None
duration_ms: int = 0

    @property
    def all_unsupported(self) -> bool:
        if not self.claims:
            return True
        return all(c.verdict != "supported" for c in self.claims)

def \_format_claims(note: ResearchNote) -> str:
return "\n".join(f"- {c.text}" for c in note.claims) or "(none)"

def \_format_sources(sources: list[SourceEntry]) -> str:
if not sources:
return "(none)"
lines = []
for s in sources:
if s.tool == "web_fetch":
lines.append(f"- web_fetch: {s.url} (content_hash={s.content_hash}, fetched_at={s.fetched_at}, skipped={s.skipped_reason})")
elif s.tool == "search_knowledge":
lines.append(f"- search_knowledge: query={s.query!r}, note_ids={s.note_ids}")
elif s.tool == "web_search":
lines.append(f"- web_search: query={s.query!r}, result_urls={s.result_urls}")
return "\n".join(lines)

async def validate_research(
\*,
note: ResearchNote,
sources: list[SourceEntry],
claude_bin: str = "claude",
) -> ValidatedResearch:
"""Run Sonnet against (note, sources) and parse per-claim verdicts."""
prompt = \_VALIDATOR_PROMPT.format(
summary=note.summary,
claims=\_format_claims(note),
sources=\_format_sources(sources),
)

    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        claude_bin, "--print", "--dangerously-skip-permissions", "--model", "sonnet", "-p", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "HOME": "/tmp"},
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_VALIDATE_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("research_validator: subprocess timed out after %ds", _VALIDATE_TIMEOUT_SECS)
        return ValidatedResearch(timed_out=True, duration_ms=duration_ms)

    duration_ms = int((time.monotonic() - start) * 1000)
    if proc.returncode != 0:
        logger.warning(
            "research_validator: subprocess exit=%d; stderr=%s",
            proc.returncode, stderr.decode(errors="replace")[:300],
        )
        return ValidatedResearch(parse_error=f"exit {proc.returncode}", duration_ms=duration_ms)

    parsed = _parse_validator_response(stdout.decode(errors="replace"))
    if parsed is None:
        return ValidatedResearch(parse_error="no JSON block found", duration_ms=duration_ms)

    try:
        claims = [
            ValidatedClaim(text=c["text"], verdict=c["verdict"], reason=c.get("reason", ""))
            for c in parsed.get("claims", [])
            if c.get("verdict") in ("supported", "unsupported", "speculative")
        ]
    except (KeyError, TypeError) as e:
        return ValidatedResearch(parse_error=f"malformed claims: {e}", duration_ms=duration_ms)

    return ValidatedResearch(claims=claims, duration_ms=duration_ms)

def \_parse_validator_response(text: str) -> dict | None:
"""Extract the first JSON object from Claude's response.

    Tolerates prose preambles, fenced ```json blocks, and trailing prose.
    """
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

````

**Step 4: Add BUILD targets.**

Mirror Task 5's pattern.

**Step 5: Run tests to verify they pass (intent).**

Expected: 5 tests PASS.

**Step 6: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_validator.py \
        projects/monolith/knowledge/research_validator_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add Sonnet-driven research validator (claude CLI subprocess)"
````

---

## Task 7: `research_writer.py` — write success + quarantine raws

**Files:**

- Create: `projects/monolith/knowledge/research_writer.py`
- Create: `projects/monolith/knowledge/research_writer_test.py`
- Modify: `projects/monolith/BUILD`

**Step 1: Write the failing tests.**

`research_writer_test.py`:

```python
"""Tests for research raw + quarantine writers."""

from __future__ import annotations

import yaml

from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_validator import ValidatedClaim, ValidatedResearch
from knowledge.research_writer import (
    FAILED_RESEARCH_DIR,
    INBOX_RESEARCH_DIR,
    quarantine,
    write_research_raw,
)


def test_write_research_raw_creates_inbox_research_file_with_full_frontmatter(tmp_path):
    note = ResearchNote(
        summary="A merkle tree is a hash-chained tree.",
        claims=[Claim(text="A merkle tree hashes pairs of children."), Claim(text="Used in Bitcoin.")],
    )
    sources = [
        SourceEntry(tool="web_fetch", url="https://a.com", content_hash="sha256:abc", fetched_at="2026-04-25T09:00:00Z"),
        SourceEntry(tool="search_knowledge", query="merkle", note_ids=["my-note"]),
        SourceEntry(tool="web_search", query="merkle tree", result_urls=["https://b.com"]),
    ]
    supported = [
        ValidatedClaim(text="A merkle tree hashes pairs of children.", verdict="supported", reason="from a.com"),
        ValidatedClaim(text="Used in Bitcoin.", verdict="supported", reason="common knowledge"),
    ]

    path = write_research_raw(
        vault_root=tmp_path,
        slug="merkle-tree",
        title="merkle-tree",
        summary=note.summary,
        supported_claims=supported,
        sources=sources,
        claims_dropped=0,
        qwen_model="qwen3.6-27b",
        sonnet_model="sonnet-4-6",
        researched_at="2026-04-25T10:00:00Z",
    )

    assert path == tmp_path / INBOX_RESEARCH_DIR / "merkle-tree.md"
    text = path.read_text()
    assert text.startswith("---\n")
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["type"] == "research"
    assert fm["id"] == "merkle-tree"
    assert fm["derived_from_gap"] == "merkle-tree"
    assert fm["claims_supported"] == 2
    assert fm["claims_dropped"] == 0
    assert len(fm["sources"]) == 3
    assert fm["sources"][0]["tool"] == "web_fetch"
    assert fm["sources"][0]["url"] == "https://a.com"
    assert "merkle tree hashes pairs" in text
    assert "Used in Bitcoin" in text


def test_write_research_raw_drops_unsupported_claims_from_body(tmp_path):
    """Only supported claims appear in the body — dropped claims live in claims_dropped count."""
    sources = [SourceEntry(tool="web_fetch", url="https://a.com", content_hash="x", fetched_at="t")]
    supported = [ValidatedClaim(text="kept", verdict="supported", reason="ok")]

    path = write_research_raw(
        vault_root=tmp_path,
        slug="x",
        title="x",
        summary="s",
        supported_claims=supported,
        sources=sources,
        claims_dropped=2,
        qwen_model="q",
        sonnet_model="s",
        researched_at="t",
    )

    text = path.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["claims_supported"] == 1
    assert fm["claims_dropped"] == 2
    assert "kept" in text


def test_quarantine_writes_failed_research_file_with_attempt_suffix(tmp_path):
    note = ResearchNote(summary="bad", claims=[Claim(text="unsubstantiated")])
    validated = ValidatedResearch(claims=[
        ValidatedClaim(text="unsubstantiated", verdict="unsupported", reason="no source"),
    ])

    path = quarantine(
        vault_root=tmp_path,
        slug="x",
        attempt=2,
        draft_note=note,
        validated=validated,
        sources=[],
        qwen_model="q",
        sonnet_model="s",
        researched_at="t",
    )

    assert path == tmp_path / FAILED_RESEARCH_DIR / "x-2.md"
    text = path.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert fm["type"] == "failed_research"
    assert fm["attempt"] == 2
    assert fm["derived_from_gap"] == "x"
    assert "unsubstantiated" in text


def test_write_research_raw_byte_stable_on_idempotent_call(tmp_path):
    """Calling write_research_raw twice with identical args produces an identical file (byte-stable)."""
    sources = [SourceEntry(tool="web_fetch", url="https://a.com", content_hash="x", fetched_at="t")]
    supported = [ValidatedClaim(text="kept", verdict="supported", reason="ok")]

    args = dict(
        vault_root=tmp_path, slug="x", title="x", summary="s",
        supported_claims=supported, sources=sources, claims_dropped=0,
        qwen_model="q", sonnet_model="s", researched_at="t",
    )
    path = write_research_raw(**args)
    first = path.read_bytes()
    write_research_raw(**args)
    second = path.read_bytes()
    assert first == second
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — module missing.

**Step 3: Implement the writer.**

Create `projects/monolith/knowledge/research_writer.py`:

```python
"""Vault writers for research raws and failed-research quarantine files.

Both writers produce idempotent, byte-stable markdown with YAML frontmatter
suitable for raw_ingest pickup. The schema of the frontmatter is the
ground-truth provenance for every atom that gets committed downstream.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from knowledge.research_agent import PIPELINE_VERSION, ResearchNote, SourceEntry
from knowledge.research_validator import VALIDATOR_VERSION, ValidatedClaim, ValidatedResearch

INBOX_RESEARCH_DIR = "_inbox/research"
FAILED_RESEARCH_DIR = "_failed_research"


def _source_to_fm(s: SourceEntry) -> dict[str, Any]:
    """Serialize a SourceEntry to a frontmatter-friendly dict, omitting Nones."""
    return {k: v for k, v in asdict(s).items() if v not in (None, [], "")}


def _yaml_dump(fm: dict) -> str:
    return yaml.dump(fm, default_flow_style=False, sort_keys=False)


def write_research_raw(
    *,
    vault_root: Path,
    slug: str,
    title: str,
    summary: str,
    supported_claims: list[ValidatedClaim],
    sources: list[SourceEntry],
    claims_dropped: int,
    qwen_model: str,
    sonnet_model: str,
    researched_at: str,
) -> Path:
    """Write the validated research raw to ``_inbox/research/<slug>.md``."""
    out_dir = vault_root / INBOX_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"

    fm = {
        "type": "research",
        "id": slug,
        "title": f"Research note: {title}",
        "derived_from_gap": slug,
        "qwen_model": qwen_model,
        "sonnet_model": sonnet_model,
        "validator_version": VALIDATOR_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sources": [_source_to_fm(s) for s in sources],
        "claims_supported": len(supported_claims),
        "claims_dropped": claims_dropped,
    }

    body_lines = [
        f"## Summary\n\n{summary}\n",
        "## Supported claims",
    ]
    for c in supported_claims:
        body_lines.append(f"- {c.text} _[{c.reason}]_")
    body_lines.append("")
    body_lines.append("## Sources")
    for s in sources:
        if s.tool == "web_fetch" and s.url:
            body_lines.append(f"- web_fetch: {s.url}")
        elif s.tool == "search_knowledge":
            body_lines.append(f"- search_knowledge: {s.query} → {s.note_ids}")
        elif s.tool == "web_search":
            body_lines.append(f"- web_search: {s.query} → {s.result_urls}")

    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path


def quarantine(
    *,
    vault_root: Path,
    slug: str,
    attempt: int,
    draft_note: ResearchNote,
    validated: ValidatedResearch,
    sources: list[SourceEntry],
    qwen_model: str,
    sonnet_model: str,
    researched_at: str,
) -> Path:
    """Write a fully-rejected research draft to ``_failed_research/<slug>-<N>.md``."""
    out_dir = vault_root / FAILED_RESEARCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}-{attempt}.md"

    fm = {
        "type": "failed_research",
        "id": f"{slug}-{attempt}",
        "derived_from_gap": slug,
        "attempt": attempt,
        "qwen_model": qwen_model,
        "sonnet_model": sonnet_model,
        "validator_version": VALIDATOR_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "researched_at": researched_at,
        "sonnet_reasons": [
            {"claim": c.text, "verdict": c.verdict, "reason": c.reason}
            for c in validated.claims
        ],
        "parse_error": validated.parse_error,
        "timed_out": validated.timed_out,
        "sources_attempted": [_source_to_fm(s) for s in sources],
    }

    body_lines = [f"# Failed research draft (attempt {attempt})", "", "## Summary", "", draft_note.summary, "", "## Claims (Qwen)"]
    for c in draft_note.claims:
        body_lines.append(f"- {c.text}")
    body = "\n".join(body_lines) + "\n"
    out_path.write_text(f"---\n{_yaml_dump(fm)}---\n\n{body}")
    return out_path
```

**Step 4: Add BUILD targets and run tests (intent).**

Expected: 4 tests PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_writer.py \
        projects/monolith/knowledge/research_writer_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add research raw + quarantine vault writers"
```

---

## Task 8: `research_handler.py` — the scheduled-job handler

**Files:**

- Create: `projects/monolith/knowledge/research_handler.py`
- Create: `projects/monolith/knowledge/research_handler_test.py`
- Modify: `projects/monolith/BUILD`

**Step 1: Write the failing tests.**

`research_handler_test.py`:

```python
"""Tests for the knowledge.research-gaps scheduled-job handler.

All three model tiers are mocked; the contract under test is the state
machine — which transitions happen for which validator outcomes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from knowledge.models import Gap
from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_handler import RESEARCH_BATCH_SIZE, research_gaps_handler
from knowledge.research_validator import ValidatedClaim, ValidatedResearch


@pytest.fixture
def seed_classified_external_gaps(session):
    def _seed(n: int) -> list[str]:
        slugs = []
        for i in range(n):
            slug = f"term-{i}"
            session.add(Gap(
                term=slug, note_id=slug, gap_class="external", state="classified",
                pipeline_version="test",
            ))
            slugs.append(slug)
        session.commit()
        return slugs
    return _seed


@pytest.mark.asyncio
async def test_handler_picks_up_to_batch_size_external_classified_gaps(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(RESEARCH_BATCH_SIZE + 2)

    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_sources = [SourceEntry(tool="web_fetch", url="u", content_hash="x", fetched_at="t")]
    fake_validated = ValidatedResearch(claims=[ValidatedClaim(text="c", verdict="supported", reason="r")])

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, fake_sources))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    rows = session.execute(select(Gap)).scalars().all()
    committed = [g for g in rows if g.state == "committed"]
    classified = [g for g in rows if g.state == "classified"]
    assert len(committed) == RESEARCH_BATCH_SIZE
    assert len(classified) == 2  # the leftover that didn't get picked up


@pytest.mark.asyncio
async def test_handler_writes_inbox_research_file_on_supported_claim(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(claims=[ValidatedClaim(text="c", verdict="supported", reason="r")])

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, []))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    assert (tmp_path / "_inbox" / "research" / "term-0.md").is_file()


@pytest.mark.asyncio
async def test_handler_quarantines_and_bumps_attempts_on_all_unsupported(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(claims=[ValidatedClaim(text="c", verdict="unsupported", reason="r")])

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, []))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 1
    assert gap.state == "classified"  # back for retry
    assert (tmp_path / "_failed_research" / "term-0-1.md").is_file()


@pytest.mark.asyncio
async def test_handler_parks_after_three_consecutive_failures(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(claims=[ValidatedClaim(text="c", verdict="unsupported", reason="r")])

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, []))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        for _ in range(3):
            await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 3
    assert gap.state == "parked"
    assert (tmp_path / "_failed_research" / "term-0-1.md").is_file()
    assert (tmp_path / "_failed_research" / "term-0-2.md").is_file()
    assert (tmp_path / "_failed_research" / "term-0-3.md").is_file()


@pytest.mark.asyncio
async def test_handler_does_not_bump_attempts_on_qwen_infra_error(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(1)

    with patch("knowledge.research_handler._run_research", AsyncMock(side_effect=ConnectionError("llama-cpp down"))):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 0
    assert gap.state == "classified"


@pytest.mark.asyncio
async def test_handler_does_not_bump_attempts_on_validator_timeout(session, tmp_path, seed_classified_external_gaps):
    seed_classified_external_gaps(1)
    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(timed_out=True)

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, []))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "term-0")).scalar_one()
    assert gap.research_attempts == 0
    assert gap.state == "classified"


@pytest.mark.asyncio
async def test_handler_skips_non_external_gaps(session, tmp_path, seed_classified_external_gaps):
    """Internal/hybrid gaps are never selected, even if state='classified'."""
    session.add(Gap(term="i", note_id="i", gap_class="internal", state="classified", pipeline_version="t"))
    session.add(Gap(term="h", note_id="h", gap_class="hybrid", state="classified", pipeline_version="t"))
    session.commit()

    fake_note = ResearchNote(summary="s", claims=[Claim(text="c")])
    fake_validated = ValidatedResearch(claims=[ValidatedClaim(text="c", verdict="supported", reason="r")])

    with patch("knowledge.research_handler._run_research", AsyncMock(return_value=(fake_note, []))), \
         patch("knowledge.research_handler.validate_research", AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    rows = session.execute(select(Gap)).scalars().all()
    for g in rows:
        assert g.state == "classified", f"non-external gap {g.term} ({g.gap_class}) was wrongly picked up"
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — module missing.

**Step 3: Implement the handler.**

Create `projects/monolith/knowledge/research_handler.py`:

```python
"""Scheduled-job handler for knowledge.research-gaps.

Every tick: pulls up to RESEARCH_BATCH_SIZE external+classified gaps,
runs Qwen+Sonnet, transitions state per design's state machine.
Infra failures (llama-cpp down, Sonnet timeout) revert state without
burning attempts. Validator rejection (all-unsupported) bumps attempts;
>=3 attempts → parked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from knowledge.models import Gap
from knowledge.research_agent import (
    QWEN_MODEL_ID,
    ResearchDeps,
    ResearchNote,
    SourceEntry,
    create_research_agent,
    derive_sources_bundle,
)
from knowledge.research_validator import (
    ValidatedResearch,
    validate_research,
)
from knowledge.research_writer import quarantine, write_research_raw

logger = logging.getLogger(__name__)

RESEARCH_BATCH_SIZE = 3
RESEARCH_PARK_THRESHOLD = 3
SONNET_MODEL_ID = "sonnet-4-6"


async def research_gaps_handler(
    *,
    session: Session,
    vault_root: Path,
) -> None:
    """Run one tick of the external research pipeline."""
    candidates = session.execute(
        select(Gap)
        .where(Gap.gap_class == "external", Gap.state == "classified")
        .order_by(Gap.id)
        .limit(RESEARCH_BATCH_SIZE)
    ).scalars().all()

    if not candidates:
        logger.info("knowledge.research-gaps: no candidates")
        return

    for gap in candidates:
        # Defense-in-depth privacy guard: even though the SELECT filtered,
        # re-assert before each Qwen call. Cheap, prevents future misroutes.
        if gap.gap_class != "external":
            logger.warning("knowledge.research-gaps: skipping non-external gap %s", gap.term)
            continue

        # Race-safe lock: only proceed if state still 'classified'.
        result = session.execute(
            Gap.__table__.update()
            .where(Gap.id == gap.id, Gap.state == "classified")
            .values(state="researching")
        )
        session.commit()
        if result.rowcount == 0:
            logger.info("knowledge.research-gaps: race lost for %s", gap.term)
            continue

        await _process_one(session=session, gap=gap, vault_root=vault_root)


async def _process_one(*, session: Session, gap: Gap, vault_root: Path) -> None:
    researched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Run Qwen.
    try:
        note, sources = await _run_research(session=session, gap=gap, vault_root=vault_root)
    except Exception:
        logger.exception("knowledge.research-gaps: Qwen failure on %s; reverting state", gap.term)
        gap.state = "classified"
        session.commit()
        return

    # 2. Run Sonnet.
    try:
        validated = await validate_research(note=note, sources=sources)
    except Exception:
        logger.exception("knowledge.research-gaps: validator failure on %s; reverting state", gap.term)
        gap.state = "classified"
        session.commit()
        return

    if validated.timed_out or validated.parse_error:
        logger.warning(
            "knowledge.research-gaps: validator infra issue on %s (timed_out=%s parse_error=%s); reverting state",
            gap.term, validated.timed_out, validated.parse_error,
        )
        gap.state = "classified"
        session.commit()
        return

    # 3. Branch on verdicts.
    if validated.all_unsupported:
        attempt = gap.research_attempts + 1
        try:
            quarantine(
                vault_root=vault_root, slug=gap.note_id, attempt=attempt,
                draft_note=note, validated=validated, sources=sources,
                qwen_model=QWEN_MODEL_ID, sonnet_model=SONNET_MODEL_ID,
                researched_at=researched_at,
            )
        except Exception:
            logger.exception("knowledge.research-gaps: quarantine write failed for %s", gap.term)
            gap.state = "classified"
            session.commit()
            return

        gap.research_attempts = attempt
        gap.state = "parked" if attempt >= RESEARCH_PARK_THRESHOLD else "classified"
        session.commit()
        logger.info(
            "knowledge.research-gaps: rejected %s (attempt=%d, state=%s)",
            gap.term, attempt, gap.state,
        )
        return

    # 4. Supported claims path.
    supported = [c for c in validated.claims if c.verdict == "supported"]
    dropped = len(validated.claims) - len(supported)

    try:
        write_research_raw(
            vault_root=vault_root, slug=gap.note_id, title=gap.term,
            summary=note.summary, supported_claims=supported, sources=sources,
            claims_dropped=dropped, qwen_model=QWEN_MODEL_ID, sonnet_model=SONNET_MODEL_ID,
            researched_at=researched_at,
        )
    except Exception:
        logger.exception("knowledge.research-gaps: raw write failed for %s; reverting state", gap.term)
        gap.state = "classified"
        session.commit()
        return

    gap.state = "committed"
    session.commit()
    logger.info(
        "knowledge.research-gaps: committed %s (supported=%d, dropped=%d)",
        gap.term, len(supported), dropped,
    )


async def _run_research(
    *,
    session: Session,
    gap: Gap,
    vault_root: Path,
) -> tuple[ResearchNote, list[SourceEntry]]:
    """Run the Pydantic AI agent; return (note, sources_bundle).

    Pulled out as a separate function so research_handler_test.py can mock
    it without standing up a real Pydantic AI loop.
    """
    agent = create_research_agent()
    deps = ResearchDeps(session=session, vault_root=vault_root)
    user_prompt = (
        f"Research the term: {gap.term!r}.\n"
        f"Context: this term appears as an unresolved [[wikilink]] in the user's vault. "
        f"Use search_knowledge first, then web_search + web_fetch as needed."
    )
    result = await agent.run(user_prompt, deps=deps)
    sources = derive_sources_bundle(result.all_messages())
    return result.output, sources
```

**Step 4: Add BUILD targets and run tests (intent).**

Expected: 7 tests PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_handler.py \
        projects/monolith/knowledge/research_handler_test.py \
        projects/monolith/BUILD
git commit -m "feat(knowledge): add research_gaps_handler with state-machine transitions"
```

---

## Task 9: Wire the scheduled job in `service.py`

**Files:**

- Modify: `projects/monolith/knowledge/service.py` (add handler wrapper + register_job)
- Modify: `projects/monolith/knowledge/service_test.py` (add registration test)

**Step 1: Write the failing test.**

In `service_test.py`, mirror the existing `test_on_startup_registers_classify_gaps` test (find by grep) and add an analogous one for `knowledge.research-gaps` asserting `interval_secs == 300` and `ttl_secs == 600`.

**Step 2: Run the test to verify it fails (intent).**

Expected: FAIL — job not registered.

**Step 3: Implement the wiring.**

In `projects/monolith/knowledge/service.py`, near the existing `_CLASSIFY_INTERVAL_SECS` constants, add:

```python
_RESEARCH_INTERVAL_SECS = 300
_RESEARCH_TTL_SECS = 600  # 5min interval + 5min headroom (Qwen + Sonnet round-trips)
```

Add a session-bound handler wrapper somewhere near the existing `classify_gaps_handler`:

```python
async def research_gaps_handler(session: Session) -> datetime | None:
    """Scheduler handler: drain the external research pipeline by one batch."""
    if not _vault_sync_ready():
        logger.info("knowledge.research-gaps: vault sync not ready, deferring")
        return None
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        logger.warning("knowledge.research-gaps: CLAUDE_CODE_OAUTH_TOKEN not set, skipping")
        return None
    if not os.environ.get("LLAMA_CPP_URL"):
        logger.warning("knowledge.research-gaps: LLAMA_CPP_URL not set, skipping")
        return None

    vault_root = Path(os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT))

    from knowledge.research_handler import research_gaps_handler as _impl
    await _impl(session=session, vault_root=vault_root)
    return None
```

In `on_startup`, alongside the existing `register_job(...)` calls, add:

```python
register_job(
    session,
    name="knowledge.research-gaps",
    interval_secs=_RESEARCH_INTERVAL_SECS,
    handler=research_gaps_handler,
    ttl_secs=_RESEARCH_TTL_SECS,
)
```

**Step 4: Run the test to verify it passes (intent).**

Expected: PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): register knowledge.research-gaps scheduled job"
```

---

## Task 10: `raw_ingest._infer_source` — recognize `_inbox/research/` prefix

**Files:**

- Modify: `projects/monolith/knowledge/raw_ingest.py` (`_infer_source` function around line 113)
- Modify: whichever test file owns `_infer_source` tests — search first

**Step 1: Write the failing test.**

```python
def test_infer_source_research_subdir_returns_research():
    """A raw under _inbox/research/ is sourced as 'research'."""
    from knowledge.raw_ingest import _infer_source

    assert _infer_source(None, ("_inbox", "research", "merkle-tree.md")) == "research"


def test_infer_source_research_does_not_override_explicit_meta_source():
    """Explicit frontmatter meta_source still wins over directory inference."""
    from knowledge.raw_ingest import _infer_source

    assert _infer_source("manual", ("_inbox", "research", "x.md")) == "manual"
```

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — `_infer_source` returns `"vault-drop"` for the research subdir.

**Step 3: Update `_infer_source`.**

In `projects/monolith/knowledge/raw_ingest.py`:

```python
def _infer_source(meta_source: str | None, rel_parts: tuple[str, ...]) -> str:
    if meta_source:
        return meta_source
    if GRANDFATHERED_SUBDIR in rel_parts:
        return "grandfathered"
    if "research" in rel_parts:
        return "research"
    return "vault-drop"
```

**Step 4: Run tests to verify they pass (intent).**

Expected: PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/raw_ingest.py projects/monolith/knowledge/raw_ingest_test.py
git commit -m "feat(knowledge): infer source='research' for _inbox/research raws"
```

---

## Task 11: `gardener.py` — project `source_tier` onto atoms from research raws

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py` (atom-creation path that handles `type: research` raws)
- Modify: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write the failing tests.**

Add to `gardener_test.py`:

```python
def test_gardener_projects_source_tier_personal_when_no_web_fetch(session, tmp_path, ...):
    """Atoms produced from a research raw with 0 web_fetch sources get source_tier='personal'."""
    # Seed a _processed/raws/research/x.md with:
    #   frontmatter: type=research, sources=[{tool:search_knowledge, query:..., note_ids:[...]}]
    # Mock the Claude decomposition to produce 1 atom file in _processed/atom/.
    # Run gardener.run() once.
    # Read the atom file's frontmatter: assert source_tier == "personal".


def test_gardener_projects_source_tier_direct_with_one_web_fetch(...):
    """Single web_fetch source → source_tier='direct'."""


def test_gardener_projects_source_tier_research_with_multiple_web_fetch(...):
    """Multiple web_fetch sources → source_tier='research' (cross-source synthesis)."""


def test_gardener_does_not_project_source_tier_for_non_research_raws(...):
    """Existing chat/journal/etc raws don't get source_tier projected — backwards compat."""
```

The gardener test fixtures may already mock subprocess output for Claude decomposition — read `gardener_test.py` to find the existing mock pattern and reuse it. Each new atom's frontmatter should be assertable after the gardener run.

**Step 2: Run tests to verify they fail (intent).**

Expected: FAIL — `source_tier` is not present in atom frontmatter.

**Step 3: Implement the projection.**

The cleanest projection point is **post-decomposition**: after the gardener identifies new atom files derived from a research raw, walk each new atom's frontmatter and inject `source_tier`.

Find the gardener method that resolves `AtomRawProvenance.atom_fk` (around line 180 per the design-doc references). After successfully linking an atom to a raw, check the raw's `type`:

```python
def _project_source_tier_if_research(self, atom_path: Path, raw_note: Note) -> None:
    """If the raw is type:research, project source_tier into the atom's frontmatter."""
    raw_meta = parse_frontmatter(raw_note.body)  # match existing utility
    if raw_meta.get("type") != "research":
        return

    sources = raw_meta.get("sources", []) or []
    web_fetch_count = sum(
        1 for s in sources
        if (s or {}).get("tool") == "web_fetch" and (s or {}).get("url")
    )
    if web_fetch_count == 0:
        tier = "personal"
    elif web_fetch_count == 1:
        tier = "direct"
    else:
        tier = "research"

    text = atom_path.read_text()
    if not text.startswith("---\n"):
        return
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return
    fm = yaml.safe_load(parts[1])
    if not isinstance(fm, dict):
        return
    if fm.get("source_tier") == tier:
        return  # idempotent
    fm["source_tier"] = tier
    atom_path.write_text(f"---\n{yaml.dump(fm, default_flow_style=False, sort_keys=False)}---\n{parts[2]}")
```

Wire it into the gardener's atom-resolution loop wherever `atom_fk` gets assigned to a Note row. Use whatever path-resolution helper the gardener already uses to find the atom's vault file.

**Step 4: Run tests to verify they pass (intent).**

Expected: 4 tests PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): project source_tier onto atoms from research raws"
```

---

## Task 12: End-to-end integration test

**Files:**

- Create: `projects/monolith/knowledge/research_end_to_end_test.py`
- Modify: `projects/monolith/BUILD`

**Step 1: Write the golden-path test.**

```python
"""End-to-end integration test for the external research pipeline.

Mocks at the LLM boundaries (Qwen agent run, Sonnet validator) but uses
real DB state, real vault file writes, and the real research handler.
Exercises the full state-machine transition from classified → committed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from knowledge.models import Gap
from knowledge.research_agent import Claim, ResearchNote, SourceEntry
from knowledge.research_handler import research_gaps_handler
from knowledge.research_validator import ValidatedClaim, ValidatedResearch


@pytest.mark.asyncio
async def test_full_research_cycle_lands_validated_raw(session, tmp_path):
    """classified → committed: validated note lands in _inbox/research/."""
    session.add(Gap(
        term="merkle-tree", note_id="merkle-tree", gap_class="external",
        state="classified", pipeline_version="test",
    ))
    session.commit()

    fake_note = ResearchNote(
        summary="A merkle tree is a hash-chained tree.",
        claims=[Claim(text="Merkle trees hash pairs of children.")],
    )
    fake_sources = [SourceEntry(
        tool="web_fetch", url="https://example.com/m",
        content_hash="sha256:abc", fetched_at="2026-04-25T09:00:00Z",
    )]
    fake_validated = ValidatedResearch(claims=[
        ValidatedClaim(text="Merkle trees hash pairs of children.",
                       verdict="supported", reason="from example.com/m"),
    ])

    with patch("knowledge.research_handler._run_research",
               AsyncMock(return_value=(fake_note, fake_sources))), \
         patch("knowledge.research_handler.validate_research",
               AsyncMock(return_value=fake_validated)):
        await research_gaps_handler(session=session, vault_root=tmp_path)

    gap = session.execute(select(Gap).where(Gap.term == "merkle-tree")).scalar_one()
    assert gap.state == "committed"
    assert gap.research_attempts == 0  # no attempts burned on success

    raw = tmp_path / "_inbox" / "research" / "merkle-tree.md"
    assert raw.is_file()
    text = raw.read_text()
    assert "type: research" in text
    assert "Merkle trees hash pairs of children" in text
    assert "https://example.com/m" in text
```

**Step 2: Add BUILD targets and run test (intent).**

Expected: 1 test PASS.

**Step 3: Format and commit.**

```bash
format
git add projects/monolith/knowledge/research_end_to_end_test.py projects/monolith/BUILD
git commit -m "test(knowledge): end-to-end research pipeline cycle"
```

---

## Task 13: Chart bump + release

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` (version `0.53.11` → `0.53.12`)
- Modify: `projects/monolith/deploy/application.yaml` (`targetRevision: 0.53.11` → `0.53.12` on the OCI source)

**Step 1: Confirm `0.53.12` is unclaimed.**

```bash
gh pr list --state all --search "0.53.12 chart" --json number,title,state | head -20
```

Expected: no open PR claims `0.53.12`. If one exists, bump to `0.53.13`.

**Step 2: Bump the chart version.**

In `projects/monolith/chart/Chart.yaml`, change `version: 0.53.11` → `version: 0.53.12`.

**Step 3: Bump the application targetRevision.**

In `projects/monolith/deploy/application.yaml`, change `targetRevision: 0.53.11` → `targetRevision: 0.53.12` on the OCI chart source (NOT the git source — the git source stays at `HEAD`).

**Step 4: Verify the chart still renders cleanly.**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml > /tmp/render.yaml
echo "exit=$?"
wc -l /tmp/render.yaml
```

Expected: exit 0, several thousand lines.

**Step 5: Commit.**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to 0.53.12"
```

---

## Final review and ship

After all 13 tasks land:

**Step 1: Inspect the branch shape.**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

Expected: 13 commits, all conventional-commit prefixed, files match each task's scope.

**Step 2: Push the branch and open the PR.**

Hand off to `superpowers:finishing-a-development-branch` for the push + PR creation flow. After the PR exists, monitor the CI run:

```bash
gh pr checks <pr-number> --watch
# or, for the BuildBuddy invocation directly:
bb view $(gh pr checks <pr-number> --json name,link --jq '.[] | select(.name|test("buildbuddy|test")) | .link' | head -1)
```

**Step 3: Iterate on CI failures by reading the BuildBuddy run output (`bb view <invocation>` / `bb ask`) and pushing fixes.** Don't try to short-circuit with `bb remote test` from your workstation — the pool's darwin runners aren't provisioned and the linux fallback is too flaky for the inner loop.

The PR body should call out:

- New scheduled job `knowledge.research-gaps` drains `external+classified` gaps via Qwen+Sonnet
- Three retrieval tools: `search_knowledge`, `web_search` (SearXNG), `web_fetch`
- Sonnet validates per-claim; supported claims land as `type: research` raws in `_inbox/research/`
- Quarantine path for fully-rejected drafts at `_failed_research/<slug>-<N>.md`
- Gap parks at 3 consecutive validation failures; infra failures don't burn attempts
- New `Gap.research_attempts` column (migration)
- `source_tier` projection (`personal` / `direct` / `research`) onto atoms based on web_fetch count
- Chart bump `0.53.11` → `0.53.12`
- Test plan items: monitor research-gaps cycle metrics in SigNoz, watch `_failed_research/` quarantine count, verify atoms appear in `_processed/atom/` with correct `source_tier`

---

## Plan complete

Plan saved to `docs/plans/2026-04-25-external-research-pipeline-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Parallel Session (separate)** — open a new session with `superpowers:executing-plans` in the worktree, batch execution with checkpoints.

Which approach do you want?
