# Monolith Knowledge MCP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mount a FastMCP sub-app on the monolith at `/mcp` exposing `search_knowledge` and `get_note` tools that call `KnowledgeStore` directly.

**Architecture:** Create `knowledge/mcp.py` defining a `FastMCP` instance with two tools. Mount its ASGI app at `/mcp` in `app/main.py`. Tools manage their own DB sessions via `Session(get_engine())` — the same pattern used by scheduler jobs.

**Tech Stack:** FastMCP 3.2.0 (already in `runtime.txt`), FastAPI (mount), SQLModel (sessions)

---

### Task 1: Add `fastmcp` to monolith BUILD deps

**Files:**

- Modify: `projects/monolith/BUILD` (line ~67-89, `monolith_backend` deps list)

**Step 1: Add the dep**

In the `monolith_backend` `py_library` deps list, add `"@pip//fastmcp"` in alphabetical order (between `@pip//dulwich` and `@pip//fastapi`):

```python
    deps = [
        "@pip//discord_py",
        "@pip//dulwich",
        "@pip//fastapi",
        "@pip//fastmcp",        # <-- add this line
        "@pip//httpx",
        ...
    ],
```

**Step 2: Commit**

```bash
git add projects/monolith/BUILD
git commit -m "build(monolith): add fastmcp dependency"
```

---

### Task 2: Create `knowledge/mcp.py` with tool definitions

**Files:**

- Create: `projects/monolith/knowledge/mcp.py`

**Step 1: Write the failing test**

Create `projects/monolith/knowledge/mcp_test.py`:

```python
"""Unit tests for knowledge/mcp.py — MCP tools for knowledge search and retrieval."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.mcp import get_note, mcp, search_knowledge

FAKE_EMBEDDING = [0.1] * 1024

CANNED_RESULTS = [
    {
        "note_id": "n1",
        "title": "Attention Is All You Need",
        "path": "papers/attention.md",
        "type": "paper",
        "tags": ["ml", "transformers"],
        "score": 0.95,
        "section": "## Architecture",
        "snippet": "The transformer replaces recurrence entirely with attention.",
        "edges": [],
    },
]

SAMPLE_NOTE = {
    "note_id": "n1",
    "title": "Attention Is All You Need",
    "path": "papers/attention.md",
    "type": "paper",
    "tags": ["ml", "transformers"],
}


class TestSearchKnowledge:
    """Tests for the search_knowledge MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_results(self):
        mock_session = MagicMock()
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = FAKE_EMBEDDING

        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.search_notes_with_context.return_value = (
                CANNED_RESULTS
            )
            result = await search_knowledge("attention")

        assert len(result["results"]) == 1
        assert result["results"][0]["note_id"] == "n1"
        mock_embed.embed.assert_awaited_once_with("attention")

    @pytest.mark.asyncio
    async def test_short_query_returns_empty(self):
        result = await search_knowledge("a")
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        result = await search_knowledge("")
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_limit_and_type_forwarded(self):
        mock_session = MagicMock()
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = FAKE_EMBEDDING

        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.search_notes_with_context.return_value = []
            await search_knowledge("attention", limit=5, type="paper")

            MockStore.return_value.search_notes_with_context.assert_called_once_with(
                query_embedding=FAKE_EMBEDDING,
                limit=5,
                type_filter="paper",
            )

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_error(self):
        mock_embed = AsyncMock()
        mock_embed.embed.side_effect = RuntimeError("boom")

        with (
            patch("knowledge.mcp.Session"),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.EmbeddingClient", return_value=mock_embed),
        ):
            result = await search_knowledge("hello")

        assert "error" in result


class TestGetNote:
    """Tests for the get_note MCP tool."""

    @pytest.mark.asyncio
    async def test_returns_note_with_content(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "attention.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("# Attention\n\nSelf-attention mechanism.")

        monkeypatch.setenv("KNOWLEDGE_VAULT_ROOT", str(vault_dir))

        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = SAMPLE_NOTE
            MockStore.return_value.get_note_links.return_value = []
            result = await get_note("n1")

        assert result["note_id"] == "n1"
        assert result["content"] == "# Attention\n\nSelf-attention mechanism."
        assert result["edges"] == []

    @pytest.mark.asyncio
    async def test_missing_note_returns_error(self):
        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = None
            result = await get_note("nonexistent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_vault_file_returns_error(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setenv("KNOWLEDGE_VAULT_ROOT", str(vault_dir))

        mock_session = MagicMock()
        with (
            patch("knowledge.mcp.Session", return_value=mock_session),
            patch("knowledge.mcp.get_engine"),
            patch("knowledge.mcp.KnowledgeStore") as MockStore,
        ):
            MockStore.return_value.get_note_by_id.return_value = {
                **SAMPLE_NOTE,
                "path": "nonexistent/missing.md",
            }
            result = await get_note("n1")

        assert "error" in result
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_mcp_test --config=ci`
Expected: FAIL — `knowledge/mcp.py` does not exist yet.

**Step 3: Write the implementation**

Create `projects/monolith/knowledge/mcp.py`:

```python
"""MCP tools for knowledge graph search and note retrieval.

Exposes two FastMCP tools that call KnowledgeStore directly (no HTTP
round-trip). Mounted as a sub-app on the monolith at ``/mcp``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastmcp import FastMCP
from sqlmodel import Session

from app.db import get_engine
from knowledge.service import DEFAULT_VAULT_ROOT, VAULT_ROOT_ENV
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

mcp = FastMCP("Knowledge")


@mcp.tool
async def search_knowledge(
    query: str,
    limit: int = 20,
    type: str | None = None,
) -> dict:
    """Semantic search over the knowledge graph.

    Embeds the query and searches notes by cosine similarity.
    Returns ranked results with title, type, tags, best-matching
    section, a 240-char snippet, and graph edges.

    Args:
        query: Natural language search query (minimum 2 characters).
        limit: Maximum results to return (default 20, max 100).
        type: Optional note type filter (e.g. "concept", "paper").
    """
    if len(query) < 2:
        return {"results": []}

    embed_client = EmbeddingClient()
    try:
        vector = await embed_client.embed(query)
    except Exception:
        logger.exception("knowledge mcp: embedding call failed")
        return {"error": "embedding unavailable"}

    with Session(get_engine()) as session:
        results = KnowledgeStore(session).search_notes_with_context(
            query_embedding=vector,
            limit=min(limit, 100),
            type_filter=type,
        )
    return {"results": results}


@mcp.tool
async def get_note(note_id: str) -> dict:
    """Retrieve a knowledge note by its stable ID.

    Returns note metadata (title, type, tags), the full markdown
    content read from the vault, and all outgoing graph edges.

    Args:
        note_id: The stable note identifier (e.g. "attention-is-all-you-need").
    """
    with Session(get_engine()) as session:
        store = KnowledgeStore(session)
        note = store.get_note_by_id(note_id)
        if note is None:
            return {"error": f"note not found: {note_id}"}

        vault_root = Path(
            os.environ.get(VAULT_ROOT_ENV, DEFAULT_VAULT_ROOT)
        ).resolve()
        resolved = (vault_root / note["path"]).resolve()
        if not resolved.is_relative_to(vault_root) or not resolved.is_file():
            return {"error": f"vault file missing for {note_id}"}

        edges = store.get_note_links(note_id)
        return {**note, "content": resolved.read_text(), "edges": edges}
```

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:knowledge_mcp_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/mcp.py projects/monolith/knowledge/mcp_test.py
git commit -m "feat(monolith): add knowledge MCP tools"
```

---

### Task 3: Add BUILD test target for `knowledge/mcp_test.py`

**Files:**

- Modify: `projects/monolith/BUILD`

**Step 1: Add the test target**

Add after the existing `knowledge_router_test` block (around line 2196):

```python
py_test(
    name = "knowledge_mcp_test",
    srcs = ["knowledge/mcp_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

**Step 2: Run the test via BuildBuddy**

Run: `bb remote test //projects/monolith:knowledge_mcp_test --config=ci`
Expected: PASS

**Step 3: Commit**

```bash
git add projects/monolith/BUILD
git commit -m "test(monolith): add BUILD target for knowledge MCP tests"
```

---

### Task 4: Mount MCP sub-app in `app/main.py`

**Files:**

- Modify: `projects/monolith/app/main.py` (lines ~170-185)

**Step 1: Add the mount**

After the router includes (line 171) and before the `/healthz` route (line 174), add:

```python
from knowledge.mcp import mcp as knowledge_mcp

app.mount("/mcp", knowledge_mcp.http_app())
```

The full section should read:

```python
app.include_router(knowledge_router)
app.include_router(observability_router)

from knowledge.mcp import mcp as knowledge_mcp

app.mount("/mcp", knowledge_mcp.http_app())


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
```

**Step 2: Verify existing tests still pass**

Run: `bb remote test //projects/monolith:knowledge_router_test //projects/monolith:home_router_test --config=ci`
Expected: PASS — mounting the sub-app should not break existing routes.

**Step 3: Commit**

```bash
git add projects/monolith/app/main.py
git commit -m "feat(monolith): mount knowledge MCP sub-app at /mcp"
```

---

### Task 5: Run full test suite and push

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: All pass.

**Step 2: Push and open PR**

```bash
git push -u origin feat/monolith-knowledge-mcp
gh pr create --title "feat(monolith): add knowledge MCP endpoint" --body "..."
```
