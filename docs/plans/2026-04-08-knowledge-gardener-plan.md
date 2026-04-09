# Knowledge Gardener Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a scheduled gardener that decomposes raw vault notes into typed knowledge artifacts (atoms, facts, active) using Claude Sonnet via the Anthropic SDK, with soft-delete TTL cleanup.

**Architecture:** A `knowledge.garden` scheduled job walks the vault root for unprocessed `.md` files, calls Claude Sonnet with tool-use to decompose each into typed notes written to `_processed/`, then moves originals to `_deleted_with_ttl/` with a 24h TTL. A TTL cleanup phase purges expired soft-deleted files. The existing reconciler picks up new files in `_processed/` on its next cycle.

**Tech Stack:** Python 3.13, Anthropic SDK (`anthropic`), SQLModel/SQLAlchemy (pgvector), Bazel (`@pip//anthropic`), Helm/ArgoCD for deployment.

---

### Task 1: Add `search_notes` to `KnowledgeStore`

The gardener's LLM tools need semantic search over existing notes. The store currently only has `get_indexed()` (path→hash map) and `upsert_note`. We need a vector similarity search method.

**Files:**

- Modify: `projects/monolith/knowledge/store.py`
- Create: `projects/monolith/knowledge/store_search_test.py` (or add to existing `store_test.py`)

**Step 1: Write the failing test**

Add to `projects/monolith/knowledge/store_test.py`:

```python
class TestSearchNotes:
    def test_returns_similar_notes(self, session):
        """search_notes returns notes ranked by embedding similarity."""
        store = KnowledgeStore(session=session)
        # Insert two notes with known embeddings
        _insert_note(session, store, note_id="close", title="Close", embedding=[1.0] * 1024)
        _insert_note(session, store, note_id="far", title="Far", embedding=[-1.0] * 1024)
        results = store.search_notes(query_embedding=[1.0] * 1024, limit=5)
        assert len(results) >= 1
        assert results[0]["note_id"] == "close"

    def test_excludes_specified_note_ids(self, session):
        """search_notes can exclude notes by id (e.g. the source note)."""
        store = KnowledgeStore(session=session)
        _insert_note(session, store, note_id="a", title="A", embedding=[1.0] * 1024)
        _insert_note(session, store, note_id="b", title="B", embedding=[0.9] * 1024)
        results = store.search_notes(query_embedding=[1.0] * 1024, limit=5, exclude_ids=["a"])
        assert all(r["note_id"] != "a" for r in results)

    def test_respects_limit(self, session):
        """search_notes returns at most `limit` results."""
        store = KnowledgeStore(session=session)
        for i in range(5):
            _insert_note(session, store, note_id=f"n{i}", title=f"N{i}", embedding=[1.0] * 1024)
        results = store.search_notes(query_embedding=[1.0] * 1024, limit=2)
        assert len(results) <= 2

    def test_returns_empty_when_no_notes(self, session):
        store = KnowledgeStore(session=session)
        results = store.search_notes(query_embedding=[1.0] * 1024, limit=5)
        assert results == []
```

You'll need a helper `_insert_note` that creates a Note + Chunk with an embedding. Use the existing `session_fixture` from `store_test.py` or `reconciler_test.py`.

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:store_search_test --config=ci`
Expected: FAIL — `search_notes` doesn't exist yet

**Step 3: Implement `search_notes`**

Add to `projects/monolith/knowledge/store.py`:

```python
def search_notes(
    self,
    query_embedding: list[float],
    *,
    limit: int = 5,
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """Return notes ranked by cosine similarity to query_embedding.

    Each result is a dict with keys: note_id, title, path, score.
    Searches against chunk embeddings and groups by parent note,
    returning the best chunk score per note.
    """
    from sqlalchemy import func

    query = (
        select(
            Note.note_id,
            Note.title,
            Note.path,
            func.min(Chunk.embedding.cosine_distance(query_embedding)).label("distance"),
        )
        .join(Chunk, Chunk.note_fk == Note.id)
        .group_by(Note.id, Note.note_id, Note.title, Note.path)
        .order_by("distance")
        .limit(limit)
    )
    if exclude_ids:
        query = query.where(Note.note_id.notin_(exclude_ids))

    rows = self.session.execute(query).all()
    return [
        {
            "note_id": row.note_id,
            "title": row.title,
            "path": row.path,
            "score": round(1.0 - row.distance, 4),
        }
        for row in rows
    ]
```

**Important:** pgvector's `cosine_distance` returns a distance (0 = identical), so we convert to a similarity score (1 - distance). In SQLite tests, pgvector operations aren't available, so we may need to skip these tests or provide a SQLite-compatible fallback. Check whether the existing test fixtures handle this — if the `session_fixture` in `reconciler_test.py` uses SQLite with `StaticPool`, the vector operations will likely fail. You may need to mark these tests as `@pytest.mark.postgres` or implement the search differently for tests.

**Step 4: Run test to verify it passes**

Run: `bb remote test //projects/monolith:store_search_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py
git commit -m "feat(knowledge): add semantic search_notes to KnowledgeStore"
```

---

### Task 2: Add `anthropic` dependency

**Files:**

- Modify: `bazel/requirements/all.txt` — add `anthropic` line
- Modify: `projects/monolith/BUILD` — add `"@pip//anthropic"` to `monolith_backend` deps

**Step 1: Add to requirements**

Add `anthropic` to `bazel/requirements/all.txt` (alphabetically sorted).

**Step 2: Add to BUILD deps**

In `projects/monolith/BUILD`, add `"@pip//anthropic",` to the `monolith_backend` `py_library` deps list (line ~63, alphabetically before `@pip//discord_py`).

**Step 3: Run format to regenerate lock files**

```bash
format
```

This will update any lock files and BUILD file formatting.

**Step 4: Verify the dependency resolves**

```bash
bb remote build //projects/monolith:monolith_backend --config=ci
```

Expected: BUILD succeeds

**Step 5: Commit**

```bash
git add bazel/requirements/all.txt projects/monolith/BUILD
git commit -m "build(knowledge): add anthropic SDK dependency"
```

---

### Task 3: Gardener core — file discovery and TTL cleanup

Build the non-LLM parts of the gardener first: discovering raw files and cleaning up expired soft-deletes.

**Files:**

- Create: `projects/monolith/knowledge/gardener.py`
- Create: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write the failing tests**

```python
"""Tests for the knowledge gardener."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from knowledge.gardener import Gardener, GardenStats


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestDiscoverRawFiles:
    def test_finds_md_files_outside_processed_and_deleted(self, tmp_path):
        _write(tmp_path, "inbox/new-note.md", "---\ntitle: New\n---\nBody.")
        _write(tmp_path, "_processed/existing.md", "---\nid: e\ntitle: E\n---\nBody.")
        _write(tmp_path, "_deleted_with_ttl/old.md", "---\nttl: 2026-01-01T00:00:00Z\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1
        assert raw[0].name == "new-note.md"

    def test_ignores_non_md_files(self, tmp_path):
        _write(tmp_path, "inbox/image.png", "not markdown")
        _write(tmp_path, "inbox/note.md", "---\ntitle: Note\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1

    def test_ignores_dotfiles_and_dot_directories(self, tmp_path):
        _write(tmp_path, ".obsidian/config.md", "config")
        _write(tmp_path, "inbox/.hidden.md", "hidden")
        _write(tmp_path, "inbox/visible.md", "---\ntitle: V\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        raw = gardener._discover_raw_files()
        assert len(raw) == 1


class TestTtlCleanup:
    def test_deletes_expired_files(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(tmp_path, "_deleted_with_ttl/old.md", f"---\nttl: \"{expired}\"\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "old.md").exists()

    def test_keeps_non_expired_files(self, tmp_path):
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        _write(tmp_path, "_deleted_with_ttl/recent.md", f"---\nttl: \"{future}\"\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
        assert (tmp_path / "_deleted_with_ttl" / "recent.md").exists()

    def test_handles_missing_ttl_frontmatter(self, tmp_path):
        _write(tmp_path, "_deleted_with_ttl/no-ttl.md", "---\ntitle: Oops\n---\nBody.")
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        cleaned = gardener._cleanup_ttl()
        # No ttl = don't delete (conservative)
        assert cleaned == 0

    def test_handles_empty_deleted_dir(self, tmp_path):
        gardener = Gardener(vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None)
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:gardener_test --config=ci`
Expected: FAIL — `gardener` module doesn't exist

**Step 3: Implement `Gardener` skeleton**

Create `projects/monolith/knowledge/gardener.py`:

```python
"""Knowledge gardener — decomposes raw vault notes into typed knowledge artifacts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import yaml

from knowledge import frontmatter
from knowledge.store import KnowledgeStore

logger = logging.getLogger("monolith.knowledge.gardener")

_EXCLUDED_DIRS = {"_processed", "_deleted_with_ttl", ".obsidian", ".trash"}
_TTL_HOURS = 24


@dataclass(frozen=True)
class GardenStats:
    ingested: int
    failed: int
    ttl_cleaned: int


class _Embedder(Protocol):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class Gardener:
    def __init__(
        self,
        *,
        vault_root: Path,
        anthropic_client: object | None,
        store: KnowledgeStore | None,
        embed_client: _Embedder | None,
    ) -> None:
        self.vault_root = Path(vault_root)
        self.anthropic_client = anthropic_client
        self.store = store
        self.embed_client = embed_client
        self.processed_root = self.vault_root / "_processed"
        self.deleted_root = self.vault_root / "_deleted_with_ttl"

    async def run(self) -> GardenStats:
        """Run one gardening cycle: ingest raw files, then TTL cleanup."""
        raw_files = self._discover_raw_files()
        ingested = 0
        failed = 0
        for path in raw_files:
            try:
                await self._ingest_one(path)
                ingested += 1
            except Exception:
                logger.exception("gardener: failed to ingest %s", path)
                failed += 1
        ttl_cleaned = self._cleanup_ttl()
        stats = GardenStats(ingested=ingested, failed=failed, ttl_cleaned=ttl_cleaned)
        logger.info(
            "knowledge.garden: ingested=%d failed=%d ttl_cleaned=%d",
            stats.ingested,
            stats.failed,
            stats.ttl_cleaned,
        )
        return stats

    def _discover_raw_files(self) -> list[Path]:
        """Find .md files in the vault root that are not in excluded directories."""
        raw: list[Path] = []
        for p in self.vault_root.rglob("*.md"):
            rel = p.relative_to(self.vault_root)
            parts = rel.parts
            # Skip excluded directories and dotfiles/dotdirs
            if any(part in _EXCLUDED_DIRS or part.startswith(".") for part in parts):
                continue
            raw.append(p)
        return sorted(raw)

    async def _ingest_one(self, path: Path) -> None:
        """Decompose a single raw note via Sonnet. Implemented in Task 4."""
        raise NotImplementedError("LLM ingest not yet implemented")

    def _soft_delete(self, source: Path) -> None:
        """Move a raw file to _deleted_with_ttl/ with a TTL in frontmatter."""
        rel = source.relative_to(self.vault_root)
        dest = self.deleted_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        raw = source.read_text(encoding="utf-8")
        ttl_dt = datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)

        meta_match = frontmatter._FRONTMATTER_RE.match(raw)
        if meta_match:
            # Inject ttl into existing frontmatter
            block = meta_match.group(1)
            body = raw[meta_match.end():]
            new_raw = f"---\nttl: \"{ttl_dt.isoformat()}\"\n{block}\n---\n{body}"
        else:
            new_raw = f"---\nttl: \"{ttl_dt.isoformat()}\"\n---\n{raw}"

        dest.write_text(new_raw, encoding="utf-8")
        source.unlink()

    def _cleanup_ttl(self) -> int:
        """Delete files in _deleted_with_ttl/ whose TTL has expired."""
        if not self.deleted_root.exists():
            return 0
        now = datetime.now(timezone.utc)
        cleaned = 0
        for p in list(self.deleted_root.rglob("*.md")):
            try:
                raw = p.read_text(encoding="utf-8")
                meta, _ = frontmatter.parse(raw)
                ttl_str = meta.extra.get("ttl")
                if not ttl_str:
                    continue
                ttl_dt = datetime.fromisoformat(str(ttl_str))
                if ttl_dt.tzinfo is None:
                    ttl_dt = ttl_dt.replace(tzinfo=timezone.utc)
                if now >= ttl_dt:
                    p.unlink()
                    cleaned += 1
            except Exception:
                logger.exception("gardener: failed to check TTL for %s", p)
        return cleaned
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:gardener_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): add gardener file discovery and TTL cleanup"
```

---

### Task 4: Gardener LLM ingest — Anthropic tool-use loop

Wire up the Sonnet tool-use loop that decomposes raw notes into typed knowledge artifacts.

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`
- Modify: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write the failing tests**

Add to `gardener_test.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_anthropic(tool_use_responses):
    """Create a mock anthropic client that returns canned tool-use responses.

    tool_use_responses is a list of lists of tool-use blocks. Each outer
    element is one API call's response. The gardener loop calls the API
    repeatedly until it gets a response with stop_reason='end_turn'.
    """
    client = MagicMock()
    messages = client.messages
    call_idx = {"n": 0}

    def create(**kwargs):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(tool_use_responses):
            return tool_use_responses[idx]
        # Final response — no more tool use
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []
        return resp

    messages.create = create
    return client


class TestIngestOne:
    @pytest.mark.asyncio
    async def test_creates_note_files_from_tool_calls(self, tmp_path):
        """Sonnet tool-use creates typed notes in _processed/."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Kubernetes Networking\n---\nCNI plugins handle pod networking.")

        # Mock a Sonnet response that calls create_note
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "call_1"
        tool_block.name = "create_note"
        tool_block.input = {
            "type": "atom",
            "title": "CNI plugins handle pod networking",
            "tags": ["kubernetes", "networking"],
            "edges": {},
            "body": "In Kubernetes, Container Network Interface (CNI) plugins are responsible for pod-to-pod networking.",
        }
        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [tool_block]

        mock_client = _make_mock_anthropic([resp])
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.1] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=None,
            embed_client=mock_embed,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        # Verify a note was created in _processed/
        created = list((tmp_path / "_processed").rglob("*.md"))
        assert len(created) == 1
        content = created[0].read_text()
        assert "type: atom" in content
        assert "CNI plugins handle pod networking" in content

    @pytest.mark.asyncio
    async def test_soft_deletes_raw_file_after_ingest(self, tmp_path):
        """After successful ingest, raw file moves to _deleted_with_ttl/."""
        _write(tmp_path, "inbox/raw.md", "---\ntitle: Test\n---\nBody.")

        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = []

        mock_client = _make_mock_anthropic([resp])
        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=mock_client,
            store=None,
            embed_client=None,
        )
        await gardener._ingest_one(tmp_path / "inbox" / "raw.md")

        assert not (tmp_path / "inbox" / "raw.md").exists()
        deleted = list((tmp_path / "_deleted_with_ttl").rglob("*.md"))
        assert len(deleted) == 1
        content = deleted[0].read_text()
        assert "ttl:" in content


class TestSearchNotesTool:
    @pytest.mark.asyncio
    async def test_search_tool_returns_results(self, tmp_path):
        """The search_notes tool handler queries the store and returns results."""
        mock_store = MagicMock()
        mock_store.search_notes.return_value = [
            {"note_id": "a", "title": "Existing Note", "path": "_processed/a.md", "score": 0.92}
        ]
        mock_embed = AsyncMock()
        mock_embed.embed.return_value = [0.1] * 1024

        gardener = Gardener(
            vault_root=tmp_path,
            anthropic_client=None,
            store=mock_store,
            embed_client=mock_embed,
        )
        result = await gardener._handle_search_notes({"query": "some query"})
        assert "Existing Note" in result
        mock_embed.embed.assert_called_once_with("some query")
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:gardener_test --config=ci`
Expected: FAIL

**Step 3: Implement the LLM ingest loop**

Update `projects/monolith/knowledge/gardener.py` — replace `_ingest_one` and add tool handlers:

```python
import hashlib
import json
import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Anthropic tool definitions for Sonnet
_TOOLS = [
    {
        "name": "search_notes",
        "description": "Search existing notes by semantic similarity. Use this to find related existing notes before creating new ones, so you can set appropriate edges.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search for similar notes.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_note",
        "description": "Read the full content of an existing note by its note_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The note_id (frontmatter id) of the note to read.",
                }
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new typed knowledge note. Each note should be atomic — one concept, one fact, or one actionable item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["atom", "fact", "active"],
                    "description": "atom = distilled concept/principle, fact = specific verifiable claim, active = temporal/actionable item (journal, TODO).",
                },
                "title": {
                    "type": "string",
                    "description": "Concise title for the note.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant tags for categorization.",
                },
                "edges": {
                    "type": "object",
                    "description": "Typed edges to other notes. Keys are edge types (refines, generalizes, related, contradicts, derives_from, supersedes), values are arrays of note_ids.",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "body": {
                    "type": "string",
                    "description": "The markdown body content of the note.",
                },
            },
            "required": ["type", "title", "body"],
        },
    },
    {
        "name": "patch_edges",
        "description": "Add edges to an existing note's frontmatter. Use this to link existing notes to the new notes you create.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The note_id of the existing note to patch.",
                },
                "edges": {
                    "type": "object",
                    "description": "Edges to add. Keys are edge types, values are arrays of note_ids.",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "required": ["note_id", "edges"],
        },
    },
]

_SYSTEM_PROMPT = """\
You are a knowledge gardener. Your job is to decompose a raw note into \
atomic knowledge artifacts.

For each raw note, you should:
1. First, search for related existing notes using search_notes.
2. Read any closely related notes using get_note to understand existing coverage.
3. Decompose the raw note into one or more typed notes using create_note:
   - atom: a distilled concept or principle
   - fact: a specific, verifiable claim
   - active: a temporal or actionable item (journal entry, TODO, reminder)
4. Set appropriate edges on new notes (especially derives_from to link to related existing notes).
5. Optionally use patch_edges to add edges from existing notes back to the new ones.

Each created note should be atomic — covering exactly one concept, fact, or action. \
Prefer multiple small notes over one large note. Use clear, descriptive titles.\
"""
```

Then implement the methods:

```python
async def _ingest_one(self, path: Path) -> None:
    """Decompose a single raw note via Sonnet tool-use loop."""
    raw = path.read_text(encoding="utf-8")
    meta, body = frontmatter.parse(raw)
    title = meta.title or path.stem

    messages = [
        {"role": "user", "content": f"Decompose this note:\n\nTitle: {title}\n\n{body}"}
    ]

    # Tool-use loop
    while True:
        response = self.anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = await self._handle_tool(block.name, block.input)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # Soft-delete the original
    self._soft_delete(path)

async def _handle_tool(self, name: str, input_data: dict) -> str:
    """Dispatch a tool call and return the result as a string."""
    if name == "search_notes":
        return await self._handle_search_notes(input_data)
    elif name == "get_note":
        return self._handle_get_note(input_data)
    elif name == "create_note":
        return self._handle_create_note(input_data)
    elif name == "patch_edges":
        return self._handle_patch_edges(input_data)
    return json.dumps({"error": f"unknown tool: {name}"})

async def _handle_search_notes(self, input_data: dict) -> str:
    query = input_data["query"]
    embedding = await self.embed_client.embed(query)
    results = self.store.search_notes(query_embedding=embedding, limit=5)
    return json.dumps(results)

def _handle_get_note(self, input_data: dict) -> str:
    note_id = input_data["note_id"]
    # Read from _processed/ by finding the note's path in the store
    from sqlmodel import select
    from knowledge.models import Note
    note = self.store.session.execute(
        select(Note).where(Note.note_id == note_id)
    ).scalar_one_or_none()
    if not note:
        return json.dumps({"error": f"note {note_id} not found"})
    path = self.vault_root / note.path
    if not path.exists():
        return json.dumps({"error": f"file not found for {note_id}"})
    return path.read_text(encoding="utf-8")

def _handle_create_note(self, input_data: dict) -> str:
    note_type = input_data["type"]
    title = input_data["title"]
    tags = input_data.get("tags", [])
    edges = input_data.get("edges", {})
    body = input_data["body"]

    note_id = _slugify(title)

    # Build frontmatter
    fm: dict = {"id": note_id, "title": title, "type": note_type}
    if tags:
        fm["tags"] = tags
    if edges:
        fm["edges"] = edges

    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    content = f"---\n{fm_str}\n---\n{body}\n"

    # Write to _processed/
    self.processed_root.mkdir(parents=True, exist_ok=True)
    dest = self.processed_root / f"{note_id}.md"
    # Avoid collisions
    counter = 1
    while dest.exists():
        dest = self.processed_root / f"{note_id}-{counter}.md"
        counter += 1
    dest.write_text(content, encoding="utf-8")
    logger.info("gardener: created %s (%s)", dest.name, note_type)
    return json.dumps({"created": dest.name, "note_id": note_id})

def _handle_patch_edges(self, input_data: dict) -> str:
    note_id = input_data["note_id"]
    new_edges = input_data["edges"]
    from sqlmodel import select
    from knowledge.models import Note
    note = self.store.session.execute(
        select(Note).where(Note.note_id == note_id)
    ).scalar_one_or_none()
    if not note:
        return json.dumps({"error": f"note {note_id} not found"})
    path = self.vault_root / note.path
    if not path.exists():
        return json.dumps({"error": f"file not found for {note_id}"})

    raw = path.read_text(encoding="utf-8")
    meta, body = frontmatter.parse(raw)
    # Merge edges
    for edge_type, targets in new_edges.items():
        existing = meta.edges.get(edge_type, [])
        merged = list(dict.fromkeys(existing + targets))  # dedupe, preserve order
        meta.edges[edge_type] = merged

    # Rebuild frontmatter
    fm: dict = {}
    if meta.note_id:
        fm["id"] = meta.note_id
    if meta.title:
        fm["title"] = meta.title
    if meta.type:
        fm["type"] = meta.type
    if meta.status:
        fm["status"] = meta.status
    if meta.source:
        fm["source"] = meta.source
    if meta.tags:
        fm["tags"] = meta.tags
    if meta.aliases:
        fm["aliases"] = meta.aliases
    if meta.edges:
        fm["edges"] = meta.edges
    if meta.extra:
        fm.update(meta.extra)

    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    new_raw = f"---\n{fm_str}\n---\n{body}"
    path.write_text(new_raw, encoding="utf-8")
    return json.dumps({"patched": note_id, "edges": meta.edges})
```

Add `_slugify` (same as reconciler's, or import from a shared location):

```python
def _slugify(text_in: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_in)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    return slug or "note"
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:gardener_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): implement gardener LLM ingest with Sonnet tool-use"
```

---

### Task 5: Register `knowledge.garden` scheduled job

Wire the gardener into the scheduler alongside the existing reconciler.

**Files:**

- Modify: `projects/monolith/knowledge/service.py`
- Add tests to verify registration

**Step 1: Write the failing test**

Add a test file or extend existing tests:

```python
"""Tests for knowledge service startup registration."""

from unittest.mock import patch, MagicMock

from knowledge.service import on_startup


class TestOnStartup:
    def test_registers_garden_and_reconcile_jobs(self):
        """on_startup registers both knowledge.garden and knowledge.reconcile."""
        session = MagicMock()
        with patch("shared.scheduler.register_job") as mock_register:
            on_startup(session)
        names = [call.kwargs["name"] for call in mock_register.call_args_list]
        assert "knowledge.garden" in names
        assert "knowledge.reconcile" in names

    def test_garden_registered_before_reconcile(self):
        """knowledge.garden is registered before knowledge.reconcile."""
        session = MagicMock()
        order = []
        with patch("shared.scheduler.register_job", side_effect=lambda *a, **kw: order.append(kw["name"])):
            on_startup(session)
        assert order.index("knowledge.garden") < order.index("knowledge.reconcile")
```

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: FAIL — only `knowledge.reconcile` is registered

**Step 3: Update `service.py`**

```python
"""Startup hook that registers the knowledge scheduled jobs."""

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from knowledge.gardener import Gardener
from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
_INTERVAL_SECS = 300
_TTL_SECS = 600


async def garden_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge gardener."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_api_key:
        logger.warning("knowledge.garden: ANTHROPIC_API_KEY not set, skipping")
        return None

    import anthropic

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    gardener = Gardener(
        vault_root=vault_root,
        anthropic_client=client,
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
    )
    stats = await gardener.run()
    logger.info(
        "knowledge.garden complete",
        extra={
            "ingested": stats.ingested,
            "failed": stats.failed,
            "ttl_cleaned": stats.ttl_cleaned,
        },
    )
    return None


async def reconcile_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge vault reconciler."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    reconciler = Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
        vault_root=vault_root,
    )
    stats = await reconciler.run()
    logger.info(
        "knowledge.reconcile complete",
        extra={
            "upserted": stats.upserted,
            "deleted": stats.deleted,
            "unchanged": stats.unchanged,
            "failed": stats.failed,
            "skipped_locked": stats.skipped_locked,
        },
    )
    return None


def on_startup(session: Session) -> None:
    """Register knowledge jobs with the scheduler."""
    from shared.scheduler import register_job

    # Garden runs first — it produces files that the reconciler indexes.
    register_job(
        session,
        name="knowledge.garden",
        interval_secs=_INTERVAL_SECS,
        handler=garden_handler,
        ttl_secs=_TTL_SECS,
    )
    register_job(
        session,
        name="knowledge.reconcile",
        interval_secs=_INTERVAL_SECS,
        handler=reconcile_handler,
        ttl_secs=_TTL_SECS,
    )
```

**Step 4: Run tests**

Run: `bb remote test //projects/monolith:knowledge_service_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/knowledge_service_test.py
git commit -m "feat(knowledge): register knowledge.garden scheduled job"
```

---

### Task 6: Helm chart — add ANTHROPIC_API_KEY secret

Wire the API key through 1Password → Kubernetes secret → env var.

**Files:**

- Create: `projects/monolith/chart/templates/onepassworditem-gardener.yaml`
- Modify: `projects/monolith/chart/templates/deployment.yaml`
- Modify: `projects/monolith/chart/values.yaml` — add `gardener` config section
- Modify: `projects/monolith/deploy/values.yaml` — add gardener config with 1Password path

**Step 1: Create OnePasswordItem template**

Create `projects/monolith/chart/templates/onepassworditem-gardener.yaml`:

```yaml
{{- if and .Values.gardener.enabled .Values.gardener.onepassword.itemPath }}
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: {{ include "monolith.fullname" . }}-gardener
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "monolith.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.gardener.onepassword.itemPath | quote }}
{{- end }}
```

**Step 2: Add env var to deployment.yaml**

In `projects/monolith/chart/templates/deployment.yaml`, in the backend container's `env:` section, add after the existing knowledge/chat env vars:

```yaml
            {{- if .Values.gardener.enabled }}
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ include "monolith.fullname" . }}-gardener
                  key: ANTHROPIC_API_KEY
            {{- end }}
```

**Step 3: Add chart defaults**

Add to `projects/monolith/chart/values.yaml`:

```yaml
gardener:
  enabled: false
  onepassword:
    itemPath: ""
```

**Step 4: Add deploy overrides**

Add to `projects/monolith/deploy/values.yaml`:

```yaml
gardener:
  enabled: true
  onepassword:
    itemPath: "vaults/k8s-homelab/items/anthropic"
```

**Step 5: Verify Helm renders correctly**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A5 ANTHROPIC
```

Expected: Shows the `ANTHROPIC_API_KEY` env var with secretKeyRef.

**Step 6: Bump chart version**

Bump `version` in `projects/monolith/chart/Chart.yaml` and `targetRevision` in `projects/monolith/deploy/application.yaml` (both must match — see CLAUDE.md anti-patterns).

**Step 7: Commit**

```bash
git add projects/monolith/chart/ projects/monolith/deploy/values.yaml
git commit -m "feat(knowledge): add gardener Helm config with Anthropic API key"
```

---

### Task 7: Create 1Password item for Anthropic API key

**This is a manual step.** Create an item named `anthropic` in the `k8s-homelab` vault in 1Password with a field called `ANTHROPIC_API_KEY` containing the API key. The 1Password Operator will sync it into the Kubernetes secret automatically.

---

### Task 8: End-to-end test and PR

**Step 1: Run all knowledge tests**

```bash
bb remote test //projects/monolith:gardener_test //projects/monolith:reconciler_test //projects/monolith:store_test --config=ci
```

Expected: All PASS

**Step 2: Run full monolith tests**

```bash
bb remote test //projects/monolith/... --config=ci
```

Expected: All PASS

**Step 3: Create PR**

```bash
git push -u origin feat/knowledge-gardener
gh pr create --title "feat(knowledge): add gardener for LLM-driven note decomposition" --body "$(cat <<'EOF'
## Summary
- Adds a `knowledge.garden` scheduled job that decomposes raw vault notes into typed knowledge artifacts (atoms, facts, active) using Claude Sonnet via the Anthropic SDK
- Tool-use loop gives Sonnet access to: `search_notes`, `get_note`, `create_note`, `patch_edges`
- Raw inputs soft-deleted to `_deleted_with_ttl/` with 24h TTL
- TTL cleanup phase purges expired files
- Adds `search_notes` semantic search method to `KnowledgeStore`
- Helm chart wires `ANTHROPIC_API_KEY` via 1Password

## Design
See `docs/plans/2026-04-08-knowledge-gardener-design.md`

## Test plan
- [ ] Unit tests for file discovery, TTL cleanup, tool handlers
- [ ] Mocked Sonnet responses for ingest loop
- [ ] Helm template renders correctly
- [ ] Manual: add test note to vault, verify gardener decomposes it on next cycle
- [ ] Manual: verify soft-deleted files cleaned up after 24h

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
