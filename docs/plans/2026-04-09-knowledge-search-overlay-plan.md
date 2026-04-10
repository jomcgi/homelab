# Knowledge Search Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship ADR 003 — add a ⌘K-triggered full-viewport knowledge search overlay to the homepage, backed by two new FastAPI endpoints over the existing pgvector knowledge store.

**Architecture:** A new `KnowledgeStore.search_notes_with_context()` method runs two batched SQL queries (top-N notes + best chunk per note). A new FastAPI router (`/api/knowledge/search`, `/api/knowledge/notes/{id}`) uses dependency injection for the embedding client so e2e tests can inject a deterministic fake. All frontend state lives inline in `private/+page.svelte`. The monolith e2e Playwright suite covers UI + Postgres + FastAPI integration in one test.

**Tech Stack:** Python 3.12 · FastAPI · SQLModel · pgvector · Svelte 5 runes · Playwright · `bb remote test` for CI iteration.

---

## Context for the engineer

### Repo-specific things you need to know

- **Tests run remotely.** Never run `pytest` locally. Use `bb remote test //projects/monolith/knowledge:<target> --config=ci` to iterate. Only push when green.
- **Never commit to main.** Everything happens in the worktree at `/tmp/claude-worktrees/knowledge-search-overlay` on branch `feat/knowledge-search-overlay`.
- **Format before commit.** Run `format` (vendored). A pre-commit hook will reject unformatted files.
- **Conventional commits required.** `feat(knowledge): …`, `test(knowledge): …`, etc. A `commit-msg` hook enforces this.
- **Embedding is async.** `EmbeddingClient.embed(text)` is a coroutine — `await` it.
- **The embedding server runs at `EMBEDDING_URL`** (real voyage-4-nano). Tests MUST NOT hit it. Use the `deterministic_embedding` helper in `projects/monolith/e2e/conftest.py:414` and `embed_client` fixture at `:424`.
- **No N+1.** The whole point of the second `DISTINCT ON` query is to fetch best-chunk-per-note in one round-trip.

### Files you'll touch

| File                                                         | Action                                                   |
| ------------------------------------------------------------ | -------------------------------------------------------- |
| `projects/monolith/knowledge/store.py`                       | Add `search_notes_with_context()` and `get_note_by_id()` |
| `projects/monolith/knowledge/store_test.py`                  | Add tests for the two new methods                        |
| `projects/monolith/knowledge/router.py`                      | **Create** — new FastAPI router                          |
| `projects/monolith/knowledge/router_test.py`                 | **Create** — unit tests with TestClient                  |
| `projects/monolith/knowledge/BUILD.bazel`                    | Add new `py_library`/`py_test` targets (use `format`)    |
| `projects/monolith/app/main.py`                              | Register the new router                                  |
| `projects/monolith/e2e/conftest.py`                          | Add embedding client override + vault fixture            |
| `projects/monolith/e2e/e2e_playwright_test.py`               | Add knowledge overlay e2e tests                          |
| `projects/monolith/frontend/src/routes/private/+page.svelte` | Add overlay state, markup, styles                        |

### Reference skills

- `@buildbuddy` — when CI fails, pull logs with `bb view`/`bb ask`
- `@bazel` — for BUILD file edits and understanding build targets
- `@superpowers:test-driven-development` — red/green discipline
- `@superpowers:verification-before-completion` — prove every step with command output

---

## Phase 0: Setup verification

### Task 0: Confirm worktree and branch

**Step 1: Verify you are in the worktree**

Run: `pwd && git branch --show-current`
Expected: `/tmp/claude-worktrees/knowledge-search-overlay` and `feat/knowledge-search-overlay`.

**Step 2: Verify the design doc is committed**

Run: `git log --oneline -3 -- docs/plans/`
Expected: most recent commit references `docs(plans): add knowledge search overlay design`.

**Step 3: Verify tests pass on main before touching anything**

Run: `bb remote test //projects/monolith/knowledge:store_test --config=ci`
Expected: PASS. Baseline captured.

---

## Phase 1: Backend store — `search_notes_with_context()`

### Task 1: Write failing test for `search_notes_with_context` happy path

**Files:**

- Modify: `projects/monolith/knowledge/store_test.py` (add a new test class at end)

**Step 1: Write the failing test**

Add at the bottom of `store_test.py`:

```python
class TestSearchNotesWithContext(StoreTestBase):
    """KnowledgeStore.search_notes_with_context — overlay-facing search."""

    def test_returns_type_tags_snippet_and_section(self):
        n1 = self._insert_note(
            note_id="n1",
            path="papers/attention.md",
            title="Attention Is All You Need",
            type="paper",
            tags=["ml", "transformers"],
        )
        self._insert_chunk(
            note_fk=n1.id,
            chunk_index=0,
            section_header="## Architecture",
            chunk_text="The transformer replaces recurrence entirely with attention.",
            embedding=[0.0] * 1024,
        )

        results = self.store.search_notes_with_context(
            query_embedding=[0.0] * 1024, limit=5
        )

        assert len(results) == 1
        r = results[0]
        assert r["note_id"] == "n1"
        assert r["title"] == "Attention Is All You Need"
        assert r["type"] == "paper"
        assert r["tags"] == ["ml", "transformers"]
        assert r["section"] == "## Architecture"
        assert "transformer replaces recurrence" in r["snippet"]
        assert 0.0 <= r["score"] <= 1.0
```

If `StoreTestBase` or the `_insert_note`/`_insert_chunk` helpers don't already exist, look at how existing tests in the file construct test data and mirror that pattern rather than inventing new helpers.

**Step 2: Run test to verify it fails**

Run: `bb remote test //projects/monolith/knowledge:store_test --config=ci --test_filter=TestSearchNotesWithContext`
Expected: FAIL with `AttributeError: 'KnowledgeStore' object has no attribute 'search_notes_with_context'`.

**Step 3: Do not commit yet.** We commit after green.

---

### Task 2: Implement `search_notes_with_context`

**Files:**

- Modify: `projects/monolith/knowledge/store.py` (add a new method after `search_notes`)

**Step 1: Add the method**

```python
def search_notes_with_context(
    self,
    query_embedding: list[float],
    limit: int = 20,
    type_filter: str | None = None,
) -> list[dict]:
    """Semantic search that also returns the best-matching chunk snippet.

    Two round-trips, no N+1:
      1. Top-N notes ranked by min(cosine_distance) over their chunks.
      2. For the returned notes, pick the single closest chunk via
         ``DISTINCT ON (note_fk)`` and stitch snippet + section.
    """
    distance = Chunk.embedding.cosine_distance(query_embedding)
    best_score = (1 - func.min(distance)).label("score")

    note_stmt = (
        select(
            Note.id,
            Note.note_id,
            Note.title,
            Note.path,
            Note.type,
            Note.tags,
            best_score,
        )
        .join(Chunk, Chunk.note_fk == Note.id)
        .group_by(Note.id)
        .order_by(func.min(distance))
        .limit(limit)
    )
    if type_filter:
        note_stmt = note_stmt.where(Note.type == type_filter)

    note_rows = self.session.execute(note_stmt).all()
    if not note_rows:
        return []

    note_fks = [row.id for row in note_rows]

    # Best chunk per note, single round-trip.
    chunk_stmt = (
        select(
            Chunk.note_fk,
            Chunk.section_header,
            Chunk.chunk_text,
        )
        .where(Chunk.note_fk.in_(note_fks))
        .order_by(Chunk.note_fk, distance)
        .distinct(Chunk.note_fk)
    )
    chunks_by_fk = {
        row.note_fk: (row.section_header, row.chunk_text)
        for row in self.session.execute(chunk_stmt).all()
    }

    results: list[dict] = []
    for row in note_rows:
        section, text = chunks_by_fk.get(row.id, ("", ""))
        results.append(
            {
                "note_id": row.note_id,
                "title": row.title,
                "path": row.path,
                "type": row.type,
                "tags": list(row.tags or []),
                "score": float(row.score),
                "section": section,
                "snippet": text[:240],
            }
        )
    return results
```

**Step 2: Run test to verify it passes**

Run: `bb remote test //projects/monolith/knowledge:store_test --config=ci --test_filter=TestSearchNotesWithContext`
Expected: PASS.

**Step 3: Format and commit**

```bash
format
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py
git commit -m "feat(knowledge): add search_notes_with_context store method"
```

---

### Task 3: Add `type_filter` and "no results" tests

**Step 1: Write tests**

Add to `TestSearchNotesWithContext`:

```python
def test_filters_by_type(self):
    n1 = self._insert_note(note_id="n1", path="a.md", title="Paper", type="paper")
    n2 = self._insert_note(note_id="n2", path="b.md", title="Journal", type="journal")
    self._insert_chunk(note_fk=n1.id, chunk_index=0, chunk_text="x", embedding=[0.0] * 1024)
    self._insert_chunk(note_fk=n2.id, chunk_index=0, chunk_text="y", embedding=[0.0] * 1024)

    paper_only = self.store.search_notes_with_context(
        query_embedding=[0.0] * 1024, type_filter="paper"
    )
    assert {r["note_id"] for r in paper_only} == {"n1"}

def test_empty_db_returns_empty_list(self):
    results = self.store.search_notes_with_context(query_embedding=[0.0] * 1024)
    assert results == []
```

**Step 2: Run tests**

Run: `bb remote test //projects/monolith/knowledge:store_test --config=ci --test_filter=TestSearchNotesWithContext`
Expected: PASS (all three tests).

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/store_test.py
git commit -m "test(knowledge): cover type filter and empty-db paths for search_notes_with_context"
```

---

### Task 4: Add `get_note_by_id` with test

**Step 1: Write the failing test**

In `store_test.py`, add:

```python
class TestGetNoteById(StoreTestBase):
    def test_returns_note_metadata(self):
        self._insert_note(
            note_id="n1",
            path="folder/note.md",
            title="My Note",
            type="paper",
            tags=["x"],
        )
        got = self.store.get_note_by_id("n1")
        assert got == {
            "note_id": "n1",
            "title": "My Note",
            "path": "folder/note.md",
            "type": "paper",
            "tags": ["x"],
        }

    def test_returns_none_when_missing(self):
        assert self.store.get_note_by_id("nope") is None
```

**Step 2: Run — expect FAIL** (`AttributeError`).

Run: `bb remote test //projects/monolith/knowledge:store_test --config=ci --test_filter=TestGetNoteById`

**Step 3: Implement in `store.py`**

```python
def get_note_by_id(self, note_id: str) -> dict | None:
    row = self.session.execute(
        select(Note.note_id, Note.title, Note.path, Note.type, Note.tags).where(
            Note.note_id == note_id
        )
    ).first()
    if row is None:
        return None
    return {
        "note_id": row.note_id,
        "title": row.title,
        "path": row.path,
        "type": row.type,
        "tags": list(row.tags or []),
    }
```

**Step 4: Run — expect PASS.**

**Step 5: Format and commit**

```bash
format
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py
git commit -m "feat(knowledge): add get_note_by_id store helper"
```

---

## Phase 2: Backend router

### Task 5: Create router skeleton with dependency injection

**Files:**

- Create: `projects/monolith/knowledge/router.py`
- Modify: `projects/monolith/knowledge/BUILD.bazel` (add `py_library`)
- Modify: `projects/monolith/app/main.py` (register)

**Step 1: Create `router.py`**

```python
"""FastAPI router for the knowledge search overlay (ADR 003)."""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from shared.embedding import EmbeddingClient

from .store import KnowledgeStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
_MIN_QUERY_LENGTH = 2


def get_embedding_client() -> EmbeddingClient:
    """Dependency-injectable EmbeddingClient. Override in tests."""
    return EmbeddingClient()


@router.get("/search")
async def search(
    q: str = Query(default=""),
    type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    embed_client: EmbeddingClient = Depends(get_embedding_client),
) -> dict:
    if len(q) < _MIN_QUERY_LENGTH:
        return {"results": []}
    try:
        vector = await embed_client.embed(q)
    except Exception:  # noqa: BLE001
        logger.exception("knowledge search: embedding failed")
        raise HTTPException(status_code=503, detail="embedding unavailable")
    results = KnowledgeStore(session).search_notes_with_context(
        query_embedding=vector, limit=limit, type_filter=type,
    )
    return {"results": results}


@router.get("/notes/{note_id}")
def get_note(
    note_id: str,
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
```

**Step 2: Wire into `app/main.py`**

Add next to the existing imports:

```python
from knowledge.router import router as knowledge_router
```

And next to the existing `app.include_router(...)` block:

```python
app.include_router(knowledge_router)
```

**Step 3: Update BUILD.bazel**

Add a `py_library` entry for `router.py` mirroring the existing store library. If unsure of exact syntax, run `format` — the bazel gazelle plugin will generate/update BUILD targets automatically.

**Step 4: Verify the whole tree still builds**

Run: `bb remote test //projects/monolith/app:main_test --config=ci`
Expected: PASS (proves the router is importable and `app.main` still assembles).

**Step 5: Commit**

```bash
format
git add projects/monolith/knowledge/router.py projects/monolith/knowledge/BUILD.bazel projects/monolith/app/main.py
git commit -m "feat(knowledge): add search overlay FastAPI router"
```

---

### Task 6: Router unit tests — happy path

**Files:**

- Create: `projects/monolith/knowledge/router_test.py`

**Step 1: Write the tests**

```python
"""Unit tests for knowledge/router.py."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from knowledge.router import get_embedding_client
from knowledge.store import KnowledgeStore


@pytest.fixture()
def client(session, embed_client):
    """TestClient with overridden session and embedding client."""
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_embedding_client] = lambda: embed_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestSearchEndpoint:
    def test_empty_query_returns_empty_results(self, client):
        r = client.get("/api/knowledge/search?q=")
        assert r.status_code == 200
        assert r.json() == {"results": []}

    def test_single_char_query_returns_empty_results(self, client):
        r = client.get("/api/knowledge/search?q=a")
        assert r.status_code == 200
        assert r.json() == {"results": []}

    def test_search_returns_seeded_note(self, client, session):
        # Seed one note + one chunk via KnowledgeStore for realism.
        store = KnowledgeStore(session)
        store.upsert_note(...)  # Use same helper as existing tests — mirror store_test.py
        # ...
        r = client.get("/api/knowledge/search?q=attention")
        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["note_id"] == "seeded"

    def test_embedding_failure_returns_503(self, session):
        app.dependency_overrides[get_session] = lambda: session
        failing = AsyncMock()
        failing.embed.side_effect = RuntimeError("boom")
        app.dependency_overrides[get_embedding_client] = lambda: failing
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/knowledge/search?q=hello")
        app.dependency_overrides.clear()
        assert r.status_code == 503
```

Look at `store_test.py` to see exactly how notes + chunks are seeded — the `...` placeholders above should be filled with that pattern. Do NOT invent new fixtures.

**Step 2: Add `router_test` to BUILD.bazel**

Run: `format` — gazelle will add the `py_test` target. Verify it added a target that depends on `:router` and the test-only deps.

**Step 3: Run the tests**

Run: `bb remote test //projects/monolith/knowledge:router_test --config=ci`
Expected: PASS on all four tests.

**Step 4: Commit**

```bash
git add projects/monolith/knowledge/router_test.py projects/monolith/knowledge/BUILD.bazel
git commit -m "test(knowledge): cover search endpoint happy path and 503"
```

---

### Task 7: Router unit tests — notes endpoint

**Step 1: Add these test cases to `router_test.py`:**

```python
class TestGetNoteEndpoint:
    def test_returns_note_content(self, client, session, tmp_path, monkeypatch):
        # Seed note row
        # ...mirror seeding from store_test.py...
        note_path = tmp_path / "folder" / "note.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text("# Title\n\nBody text.\n")
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))

        r = client.get("/api/knowledge/notes/n1")
        assert r.status_code == 200
        body = r.json()
        assert body["note_id"] == "n1"
        assert "Body text" in body["content"]

    def test_missing_note_row_returns_404(self, client):
        r = client.get("/api/knowledge/notes/does-not-exist")
        assert r.status_code == 404

    def test_missing_vault_file_returns_404(self, client, session, tmp_path, monkeypatch):
        # Seed note row but don't create the file on disk
        # ...
        monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
        r = client.get("/api/knowledge/notes/n1")
        assert r.status_code == 404
```

**Step 2: Run**

Run: `bb remote test //projects/monolith/knowledge:router_test --config=ci`
Expected: PASS on all seven tests.

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/router_test.py
git commit -m "test(knowledge): cover notes endpoint and 404 paths"
```

---

## Phase 3: E2E embedding override + HTTP-level integration test

### Task 8: Add embedding override to the live_server fixture

**Files:**

- Modify: `projects/monolith/e2e/conftest.py`

**Step 1: Add a fixture that overrides the embedding dependency on the live app**

Add after the existing `embed_client` fixture (around line 435):

```python
@pytest.fixture(scope="session")
def live_server_with_fake_embedding(live_server):
    """Override the knowledge router's embedding dependency for the live server.

    The live FastAPI instance reads from the ``app`` module-level singleton
    imported inside ``live_server``. Registering an override on that instance
    is enough to route every ``/api/knowledge/search`` request through the
    deterministic fake.
    """
    from unittest.mock import AsyncMock

    from app.main import app  # noqa: E402
    from knowledge.router import get_embedding_client  # noqa: E402

    fake = AsyncMock()
    fake.embed = AsyncMock(side_effect=deterministic_embedding)

    app.dependency_overrides[get_embedding_client] = lambda: fake
    yield live_server
    app.dependency_overrides.pop(get_embedding_client, None)
```

**Step 2: Sanity check — does the dependency override actually apply?**

Add this HTTP-only test in `e2e_playwright_test.py` under a new class:

```python
class TestKnowledgeSearchHttp:
    """HTTP-level tests for /api/knowledge (no browser needed)."""

    def test_empty_query_returns_empty_results(self, live_server_with_fake_embedding):
        base = live_server_with_fake_embedding
        r = httpx.get(f"{base}/api/knowledge/search?q=")
        assert r.status_code == 200
        assert r.json() == {"results": []}

    def test_search_uses_fake_embedding(self, live_server_with_fake_embedding, pg):
        # Seed a note + chunk directly in pg so we have something to find.
        # Use the same pg fixture + engine pattern the chat tests use.
        # ...
        base = live_server_with_fake_embedding
        r = httpx.get(f"{base}/api/knowledge/search?q=transformers")
        assert r.status_code == 200
        assert len(r.json()["results"]) >= 1
```

**Step 3: Run**

Run: `bb remote test //projects/monolith/e2e:e2e_playwright_test --config=ci --test_filter=TestKnowledgeSearchHttp`
Expected: PASS. (This proves the backend is integrated end-to-end before we touch any JS.)

**Step 4: Commit**

```bash
git add projects/monolith/e2e/conftest.py projects/monolith/e2e/e2e_playwright_test.py
git commit -m "test(e2e): cover knowledge search HTTP endpoints with fake embedding"
```

---

## Phase 4: Frontend — overlay shell + search

### Task 9: Add overlay state and ⌘K open/close

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/+page.svelte`

**Step 1: Add state block**

Inside the `<script>`, after the existing capture state, add:

```js
// ── Knowledge search ─────────────────────────
let searchOpen = $state(false);
let searchQuery = $state("");
let searchResults = $state([]);
let selectedNote = $state(null);
let activeIndex = $state(-1);
let searching = $state(false);
let searchType = $state("all");
let savedCapture = $state("");
let searchInputRef = $state(null);
let searchTimer;

function openSearch() {
  if (searchOpen) return;
  savedCapture = note;
  searchOpen = true;
  setTimeout(() => searchInputRef?.focus(), 0);
}

function closeSearch() {
  searchOpen = false;
  selectedNote = null;
  searchQuery = "";
  searchResults = [];
  activeIndex = -1;
  note = savedCapture;
  setTimeout(() => captureRef?.focus(), 0);
}

$effect(() => {
  function onKeydown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openSearch();
      return;
    }
    if (!searchOpen) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeSearch();
    }
  }
  document.addEventListener("keydown", onKeydown);
  return () => document.removeEventListener("keydown", onKeydown);
});
```

**Step 2: Add minimal overlay markup** (just enough to verify it renders)

Before `</div>` closing `.root`, add:

```svelte
{#if searchOpen}
  <div class="search-overlay">
    <div class="search-overlay-inner">
      <input
        bind:this={searchInputRef}
        class="search-input"
        bind:value={searchQuery}
        placeholder="search notes..."
        spellcheck="false"
      />
    </div>
  </div>
{/if}
```

**Step 3: Add styles inside the existing `<style>` block**

```css
.search-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg);
  z-index: 100;
  overflow-y: auto;
}

.search-overlay-inner {
  max-width: 72ch;
  margin: 0 auto;
  padding: 2.5rem;
}

.search-input {
  width: 100%;
  font-family: var(--font);
  font-size: 1.15rem;
  background: transparent;
  border: none;
  border-bottom: 0.06rem solid var(--border);
  outline: none;
  color: var(--fg);
  padding: 0.5rem 0;
}
```

**Step 4: Smoke test the frontend build**

Run: `bb remote test //projects/monolith/frontend:build --config=ci` (or whatever the frontend build target is — check `projects/monolith/frontend/BUILD.bazel`)
Expected: PASS.

**Step 5: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/+page.svelte
git commit -m "feat(frontend): add knowledge search overlay shell with cmdk toggle"
```

---

### Task 10: Debounced search + results rendering

**Step 1: Add the debounced fetch effect below the keydown effect**

```js
$effect(() => {
  clearTimeout(searchTimer);
  const q = searchQuery;
  if (q.length < 2) {
    searchResults = [];
    searching = false;
    return;
  }
  searching = true;
  searchTimer = setTimeout(async () => {
    const params = new URLSearchParams({ q });
    if (searchType !== "all") params.set("type", searchType);
    try {
      const res = await fetch(`/api/knowledge/search?${params}`);
      if (res.ok) {
        searchResults = (await res.json()).results;
        activeIndex = -1;
      }
    } finally {
      searching = false;
    }
  }, 300);
});
```

**Step 2: Add results list markup after the `<input>`**

```svelte
{#if searchQuery.length < 2}
  <!-- idle state, no message -->
{:else if searching && searchResults.length === 0}
  <p class="search-hint">searching...</p>
{:else if searchResults.length === 0}
  <p class="search-hint">no results</p>
{:else}
  <ul class="search-results" class:search-results--ghost={searching}>
    {#each searchResults as r, i}
      <li
        class="search-result"
        class:search-result--active={i === activeIndex}
        onclick={() => openPreview(r)}
        role="button"
        tabindex="0"
      >
        <div class="search-result-title">{r.title}</div>
        <div class="search-result-section">{r.section}</div>
        <div class="search-result-snippet">{r.snippet}</div>
      </li>
    {/each}
  </ul>
{/if}
```

Add the navigation handler to the existing `$effect` keydown listener (inside the `if (!searchOpen) return;` branch):

```js
if (e.key === "ArrowDown") {
  e.preventDefault();
  activeIndex = Math.min(activeIndex + 1, searchResults.length - 1);
} else if (e.key === "ArrowUp") {
  e.preventDefault();
  activeIndex = Math.max(activeIndex - 1, -1);
} else if (e.key === "Enter" && activeIndex >= 0) {
  e.preventDefault();
  openPreview(searchResults[activeIndex]);
}
```

Add stub `openPreview`:

```js
function openPreview(result) {
  selectedNote = { ...result, content: null };
  // Phase 5 will fetch and render
}
```

**Step 3: Add styles for results**

```css
.search-hint {
  color: var(--fg-tertiary);
  font-size: 0.85rem;
  margin-top: 1rem;
}

.search-results {
  list-style: none;
  padding: 0;
  margin: 1.5rem 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.search-results--ghost {
  opacity: 0.5;
}

.search-result {
  cursor: pointer;
  padding: 0.5rem 0;
  border-bottom: 0.04rem solid var(--border);
}

.search-result--active {
  background: var(--surface);
}

.search-result-title {
  font-weight: 700;
  font-size: 0.95rem;
}

.search-result-section {
  font-size: 0.7rem;
  color: var(--fg-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.search-result-snippet {
  font-size: 0.85rem;
  color: var(--fg-secondary);
  margin-top: 0.2rem;
}
```

**Step 4: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/+page.svelte
git commit -m "feat(frontend): add debounced search and results list to overlay"
```

---

## Phase 5: Frontend — note preview with section scroll

### Task 11: Preview fetch + heading-only renderer

**Step 1: Add the renderer helpers at the top of the `<script>`**

```js
function slugify(s) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function renderNote(md) {
  const body = md.replace(/^---\n[\s\S]*?\n---\n?/, "");
  return body.split(/\n\n+/).map((block) => {
    const h = block.match(/^(#{1,3}) (.+)$/);
    if (h) {
      const level = h[1].length;
      return { tag: `h${level}`, id: slugify(h[2]), text: h[2] };
    }
    return { tag: "p", text: block };
  });
}
```

**Step 2: Replace the stub `openPreview` with a real fetch**

```js
async function openPreview(result) {
  selectedNote = { ...result, content: null, blocks: [] };
  const res = await fetch(`/api/knowledge/notes/${result.note_id}`);
  if (!res.ok) {
    selectedNote = {
      ...result,
      content: "note not found",
      blocks: [{ tag: "p", text: "note not found" }],
    };
    return;
  }
  const body = await res.json();
  selectedNote = {
    ...result,
    content: body.content,
    blocks: renderNote(body.content),
  };
  // Scroll to matching section on next tick
  setTimeout(() => {
    const slug = slugify(result.section.replace(/^#+\s*/, ""));
    document.getElementById(slug)?.scrollIntoView({ block: "start" });
  }, 0);
}

function closePreview() {
  selectedNote = null;
}
```

**Step 3: Wire `Esc`/`←` handling**

In the keydown handler, replace the single `Escape` branch with:

```js
if (e.key === "Escape") {
  e.preventDefault();
  if (selectedNote) {
    closePreview();
  } else {
    closeSearch();
  }
  return;
}
if (e.key === "ArrowLeft" && selectedNote) {
  e.preventDefault();
  closePreview();
  return;
}
```

**Step 4: Add preview markup inside the overlay, conditional on `selectedNote`**

Replace the results block with:

```svelte
{#if selectedNote && selectedNote.blocks}
  <div class="preview">
    <button class="preview-back" onclick={closePreview}>← back · esc</button>
    <article class="preview-body">
      {#each selectedNote.blocks as block}
        {#if block.tag === "h1"}
          <h1 id={block.id}>{block.text}</h1>
        {:else if block.tag === "h2"}
          <h2 id={block.id}>{block.text}</h2>
        {:else if block.tag === "h3"}
          <h3 id={block.id}>{block.text}</h3>
        {:else}
          <p>{block.text}</p>
        {/if}
      {/each}
    </article>
  </div>
{:else}
  <!-- ... existing results list markup ... -->
{/if}
```

**Step 5: Add preview styles**

```css
.preview {
  position: relative;
}

.preview-back {
  position: sticky;
  top: 0;
  background: var(--bg);
  border: none;
  color: var(--fg-tertiary);
  font-family: var(--font);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.5rem 0;
  cursor: pointer;
}

.preview-body {
  padding-top: 1rem;
}

.preview-body h1,
.preview-body h2,
.preview-body h3 {
  font-weight: 700;
  margin: 1.5rem 0 0.5rem;
}

.preview-body p {
  margin: 0.75rem 0;
  line-height: 1.7;
}
```

**Step 6: Commit**

```bash
format
git add projects/monolith/frontend/src/routes/private/+page.svelte
git commit -m "feat(frontend): add note preview with heading-only markdown and section scroll"
```

---

## Phase 6: E2E Playwright coverage

### Task 12: Overlay open/close and capture preservation

**Files:**

- Modify: `projects/monolith/e2e/e2e_playwright_test.py`

**Step 1: Add test class**

```python
class TestKnowledgeSearchOverlay:
    def test_cmdk_opens_and_esc_closes(self, page, sveltekit_server, live_server_with_fake_embedding):
        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".capture-input")
        page.keyboard.press("Meta+k")
        page.wait_for_selector(".search-overlay")
        page.keyboard.press("Escape")
        assert page.locator(".search-overlay").count() == 0

    def test_cmdk_preserves_capture_value(self, page, sveltekit_server, live_server_with_fake_embedding):
        page.goto(f"{sveltekit_server}/private")
        capture = page.locator(".capture-input")
        capture.fill("draft thought")
        page.keyboard.press("Meta+k")
        page.wait_for_selector(".search-overlay")
        page.keyboard.press("Escape")
        # Capture textarea should still contain the draft
        assert capture.input_value() == "draft thought"
```

**Step 2: Run**

Run: `bb remote test //projects/monolith/e2e:e2e_playwright_test --config=ci --test_filter=TestKnowledgeSearchOverlay`
Expected: PASS.

**Step 3: Commit**

```bash
git add projects/monolith/e2e/e2e_playwright_test.py
git commit -m "test(e2e): cover knowledge overlay open/close and capture preservation"
```

---

### Task 13: Search results + preview + zero results

**Step 1: Add tests. Seed a note in `pg` using the same helper the HTTP test added in Task 8.**

```python
def test_search_renders_results_and_opens_preview(
    self, page, sveltekit_server, live_server_with_fake_embedding, pg, tmp_path, monkeypatch
):
    # Seed one note in pg + write file to tmp vault; point the live server at it
    # via VAULT_ROOT env override. ⚠ The live_server fixture is session-scoped, so
    # the env var must be set before that fixture instantiates — use a session-scoped
    # autouse fixture that sets VAULT_ROOT to a stable tmp dir, then write files into it.
    # ...seed note id=n1 with a chunk whose text contains "attention"...

    page.goto(f"{sveltekit_server}/private")
    page.keyboard.press("Meta+k")
    page.wait_for_selector(".search-input")
    page.locator(".search-input").fill("attention")
    page.wait_for_selector(".search-result")
    assert page.locator(".search-result").count() >= 1

    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_selector(".preview-body")
    assert "attention" in page.locator(".preview-body").inner_text().lower()

def test_zero_results_shows_hint(
    self, page, sveltekit_server, live_server_with_fake_embedding
):
    page.goto(f"{sveltekit_server}/private")
    page.keyboard.press("Meta+k")
    page.locator(".search-input").fill("zxqvfnonsense")
    page.wait_for_selector(".search-hint")
    assert "no results" in page.locator(".search-hint").inner_text()
```

**Step 2: Important — `VAULT_ROOT` handling**

The `live_server` fixture sets env vars before importing `app.main`. You'll need to add `VAULT_ROOT` setup to the same place (around `projects/monolith/e2e/conftest.py:473`) so both the HTTP tests (Task 8) and the Playwright tests find vault files. Use a session-scoped `tmp_path_factory.mktemp("vault")` and call `os.environ["VAULT_ROOT"] = str(...)` before `from app.main import app`.

Refactor Task 8's HTTP test seed helper into a reusable `knowledge_seed` session fixture that the Playwright test can share.

**Step 3: Run**

Run: `bb remote test //projects/monolith/e2e:e2e_playwright_test --config=ci --test_filter=TestKnowledgeSearchOverlay`
Expected: PASS on all four tests.

**Step 4: Commit**

```bash
git add projects/monolith/e2e/conftest.py projects/monolith/e2e/e2e_playwright_test.py
git commit -m "test(e2e): cover knowledge search results, preview, and zero results"
```

---

## Phase 7: Final integration check and PR

### Task 14: Full knowledge + e2e test suite green

**Step 1: Run the full test set**

Run:

```
bb remote test //projects/monolith/knowledge/... --config=ci
bb remote test //projects/monolith/e2e:e2e_playwright_test --config=ci
bb remote test //projects/monolith/app:main_test --config=ci
```

Expected: all PASS.

**Step 2: Verify nothing else broke**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS. If anything downstream fails, read the BuildBuddy log via `bb view` before patching.

**Step 3: Verify the frontend hint is wired**

Visually check the capture footer in `+page.svelte` — add a `⌘ k` hint alongside the existing `⌘ enter` hint. Trivial edit, no new tests needed since the visual change is cosmetic.

```svelte
<span class="capture-hint">... ⌘ k search</span>
```

Commit:

```bash
format
git add projects/monolith/frontend/src/routes/private/+page.svelte
git commit -m "feat(frontend): add cmdk search hint to capture footer"
```

---

### Task 15: Push and open PR

**Step 1: Push**

```bash
git push -u origin feat/knowledge-search-overlay
```

**Step 2: Open PR**

```bash
gh pr create --title "feat(knowledge): add knowledge search overlay to homepage" --body "$(cat <<'EOF'
## Summary

Implements [ADR 003](../decisions/services/003-knowledge-search-overlay.md): a ⌘K-triggered full-viewport knowledge search overlay on the homepage, backed by two new FastAPI endpoints over the existing pgvector knowledge store.

- New `KnowledgeStore.search_notes_with_context()` — top-N notes + batched best-chunk lookup, no N+1
- New `/api/knowledge/search` and `/api/knowledge/notes/{id}` endpoints with DI-swappable embedding client
- New overlay + preview state in `private/+page.svelte`, heading-only markdown renderer for section-level scroll targeting
- Playwright e2e coverage against real FastAPI + real Postgres with deterministic fake embedding

## Test plan

- [ ] `bb remote test //projects/monolith/knowledge/... --config=ci`
- [ ] `bb remote test //projects/monolith/e2e:e2e_playwright_test --config=ci`
- [ ] Manual: open homepage, press ⌘K, type a query, navigate results with arrows, open preview, verify section scroll
- [ ] Manual: verify capture textarea value is preserved across ⌘K open/close

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Enable auto-merge if desired**

```bash
gh pr merge --auto --rebase
```

**Step 4: Poll until merged**

Per CLAUDE.md: `gh pr view <number> --json state,mergeStateStatus` until merged, then verify the rollout via ArgoCD MCP tools.

---

## Summary of commits the plan produces

1. `feat(knowledge): add search_notes_with_context store method`
2. `test(knowledge): cover type filter and empty-db paths for search_notes_with_context`
3. `feat(knowledge): add get_note_by_id store helper`
4. `feat(knowledge): add search overlay FastAPI router`
5. `test(knowledge): cover search endpoint happy path and 503`
6. `test(knowledge): cover notes endpoint and 404 paths`
7. `test(e2e): cover knowledge search HTTP endpoints with fake embedding`
8. `feat(frontend): add knowledge search overlay shell with cmdk toggle`
9. `feat(frontend): add debounced search and results list to overlay`
10. `feat(frontend): add note preview with heading-only markdown and section scroll`
11. `test(e2e): cover knowledge overlay open/close and capture preservation`
12. `test(e2e): cover knowledge search results, preview, and zero results`
13. `feat(frontend): add cmdk search hint to capture footer`

Fifteen short-lived tasks, each independently testable and revertible.
