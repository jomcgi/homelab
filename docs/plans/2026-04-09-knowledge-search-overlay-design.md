# Knowledge Search Overlay — Design

**Date:** 2026-04-09
**Status:** Approved
**ADR:** [003-knowledge-search-overlay](../decisions/services/003-knowledge-search-overlay.md)

---

## Summary

Implement ADR 003 in a single PR: add a ⌘K-triggered full-viewport search
overlay to the homepage, backed by two new FastAPI endpoints that expose the
existing pgvector knowledge store. The monolith e2e Playwright suite (real
FastAPI + real Postgres) covers end-to-end correctness.

This document records the implementation choices that the ADR left to
implementation time, plus gaps found while reading the current code against
the ADR.

---

## Gaps verified against current code

| ADR claim                                | Reality                                                                           |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| `Note.type`, `Note.tags` exist           | ✅ `knowledge/models.py:47,50` — `type: str \| None`, `tags: list[str]`           |
| `Chunk.section_header` exists            | ✅ `knowledge/models.py:65` — `section_header: str = ""`                          |
| `VAULT_ROOT` env var pattern             | ✅ already used in `knowledge/service.py:33`                                      |
| `KnowledgeStore.search_notes()` reusable | ⚠ Returns only `note_id/title/path/score` — needs a sibling method, not a rewrite |
| Playwright e2e covers capture UI         | ✅ `e2e/e2e_playwright_test.py:406` drives `.capture-input` with `Meta+Enter`     |

The store method gap is the only one that shapes the design: a new
`search_notes_with_context()` leaves existing callers (`gardener.py`,
`tools/knowledge-search`, 6+ tests) untouched.

---

## Backend

### New file: `projects/monolith/knowledge/router.py`

```python
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

@router.get("/search")
async def search(q: str, type: str | None = None, limit: int = 20) -> dict:
    if len(q) < 2:
        return {"results": []}
    vector = await EmbeddingClient().embed(q)
    with session_scope() as session:
        results = KnowledgeStore(session).search_notes_with_context(
            query_embedding=vector, type_filter=type, limit=limit,
        )
    return {"results": results}

@router.get("/notes/{note_id}")
def get_note(note_id: str) -> dict:
    with session_scope() as session:
        note = KnowledgeStore(session).get_note_by_id(note_id)
    if note is None:
        raise HTTPException(404, "note not found")
    vault_root = Path(os.environ.get("VAULT_ROOT", "/vault"))
    file_path = vault_root / note["path"]
    if not file_path.is_file():
        raise HTTPException(404, "vault file missing")
    return {**note, "content": file_path.read_text()}
```

Registered in `app/main.py` alongside the existing routers.

### New store method: `search_notes_with_context()`

Additive to `store.py`. Two round-trips, no N+1:

1. **Top-N notes query** — extends the existing cosine-distance `SELECT` with
   `Note.type`, `Note.tags`, and an optional `WHERE Note.type = :type_filter`.
   Same `best_score = 1 - min(distance)` aggregation, same ordering.

2. **Best chunk per note** — single batched query over the returned `note_fk`
   set:

   ```sql
   SELECT DISTINCT ON (note_fk)
     note_fk, section_header, chunk_text
   FROM knowledge.chunks
   WHERE note_fk = ANY(:ids)
   ORDER BY note_fk, embedding <=> :vector
   ```

3. **Stitch** in Python — build result dicts with `{note_id, title, path,
type, tags, score, snippet, section}`. `snippet` is `chunk_text[:240]`.

### New store helper: `get_note_by_id(note_id)`

Trivial `SELECT` that returns `{note_id, title, path, type, tags}`. Used by
`GET /notes/{note_id}`. Returns `None` if missing.

### Error shape

Both endpoints raise `HTTPException` on failure; the frontend distinguishes
`503` (embedding down) from `404` (note missing) and surfaces each with a
distinct message.

---

## Frontend

All state and markup lives in `projects/monolith/frontend/src/routes/private/+page.svelte`.
No new component files — matches the ADR's "mode shift, not modal" principle
and the repo's "don't extract abstractions for one-time use" rule.

### State (Svelte 5 runes)

```js
let searchOpen = $state(false);
let searchQuery = $state("");
let searchResults = $state([]);
let selectedNote = $state(null);
let activeIndex = $state(-1);
let searching = $state(false);
let searchType = $state("all"); // persists across open/close
let savedCapture = $state(""); // preserves textarea value on ⌘K
```

### Global keydown handler

Mounted on `document` via a `$effect` that registers/tears down the listener.

- `⌘K` / `Ctrl+K`: if overlay closed, save `note` → `savedCapture`, set
  `searchOpen = true`, focus search input. If overlay already open, no-op.
- `Esc`: if preview open, close preview entirely (back to closed). If
  only results open, close overlay. Restore `note = savedCapture`.
- `↑`/`↓`: move `activeIndex` within `[-1, results.length - 1]`.
- `Enter`: if `activeIndex >= 0`, fetch note, set `selectedNote`.
- `←` (only in preview): return to results view, keep results and query.

Keys bubble only when the overlay is open, so the capture textarea still
handles `⌘+Enter` normally in its closed state.

### Debounced fetch

```js
let searchTimer;
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
    const res = await fetch(`/api/knowledge/search?${params}`);
    if (res.ok) searchResults = (await res.json()).results;
    searching = false;
  }, 300);
});
```

### Heading-only markdown renderer

Inline function in `+page.svelte`:

```js
function slugify(s) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function renderNote(md) {
  const blocks = md.replace(/^---\n[\s\S]*?\n---\n?/, "").split(/\n\n+/);
  return blocks.map((block) => {
    const h = block.match(/^(#{1,3}) (.+)$/);
    if (h) return { tag: `h${h[1].length}`, id: slugify(h[2]), text: h[2] };
    return { tag: "p", text: block };
  });
}
```

Svelte `{#each}` renders into an `{:else if}` chain over `tag`. Frontmatter
(the leading `---` block) is stripped so users never see YAML in the preview.

On preview mount, a `$effect` calls
`document.getElementById(slug)?.scrollIntoView({ block: "start" })` where
`slug` comes from the result's `section` field.

---

## Tests

### Unit tests (Bazel `py_test`)

- `projects/monolith/knowledge/router_test.py` — new. Covers happy path,
  empty `q`, `type` filter, missing `note_id`, missing vault file, `503` from
  mocked `EmbeddingClient`.
- `projects/monolith/knowledge/store_test.py` — extend with cases for
  `search_notes_with_context` and `get_note_by_id`. Seed notes with `type`
  and `tags`; assert snippet/section present and best chunk picked per note.

### E2E tests (`e2e/e2e_playwright_test.py`)

The real test for UI + Postgres + backend integration:

- `test_knowledge_overlay_opens_and_closes` — `⌘K` opens, `Esc` closes.
- `test_knowledge_overlay_preserves_capture` — type in textarea, press
  `⌘K`, close, verify textarea value restored.
- `test_knowledge_search_returns_results` — seed a known note in the vault +
  DB, type query, assert result row appears with expected title.
- `test_knowledge_search_preview` — `Enter` on result opens preview with
  content; `← back` returns to results; `Esc` closes overlay.
- `test_knowledge_search_zero_results` — query that matches nothing shows
  `no results`.

**Embedding handling in tests:** before writing any test code, check
`e2e_playwright_test.py` and `store_test.py` for the current embedding
stub/fixture. If a stub client already exists, reuse it. If not, introduce a
fixture that injects a deterministic fake `EmbeddingClient` via the FastAPI
dependency system.

---

## Risks & mitigations

| Risk                                                           | Mitigation                                                        |
| -------------------------------------------------------------- | ----------------------------------------------------------------- |
| Embedding latency flakes e2e tests                             | Use a fake embedding client in tests; don't hit voyage-4          |
| PR grows past ~800 LOC                                         | If it does, split backend into its own PR first, UI second        |
| `search_notes_with_context` duplicates SQL with `search_notes` | Acceptable — the alternative is bloating every caller             |
| `⌘K` conflicts with browser defaults                           | `e.preventDefault()` in the global handler; existing apps do this |

---

## Out of scope

- "Open in Obsidian" deep link (ADR notes this as a future enhancement)
- Recent-notes list in the idle state (ADR explicitly rejects this)
- Highlighting search term within the snippet
- Syntax highlighting in the preview
- Any markdown beyond headings and paragraphs (no lists, links, code fences)

---

## References

- [ADR 003: Knowledge Search Overlay](../decisions/services/003-knowledge-search-overlay.md)
- `projects/monolith/knowledge/store.py` — existing `search_notes()`
- `projects/monolith/knowledge/models.py` — `Note`, `Chunk` SQLModel
- `projects/monolith/frontend/src/routes/private/+page.svelte` — homepage
- `projects/monolith/e2e/e2e_playwright_test.py` — e2e Playwright suite
