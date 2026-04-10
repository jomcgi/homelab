# ADR 003: Knowledge Search Overlay

**Author:** jomcgi
**Status:** Draft
**Created:** 2026-04-09

---

## Problem

The knowledge store (PostgreSQL + pgvector, populated by the monolith reconciler) has no user-facing interface. Notes are indexed, embedded, and linked — but the only way to access them is via MCP tools in an AI session. There is no way to directly navigate to a specific note while working.

The need is **navigation**: quickly finding and reading a specific note while in the middle of something else. This is different from discovery (exploring unknown connections) or synthesis (summarising across notes) — it is lookup.

---

## Proposal

Add a full-viewport search overlay to the existing homepage (`private/+page.svelte`). Triggered by `⌘K` from anywhere on the page. No new routes — this is an in-page mode switch driven by a `$state` boolean.

The backend provides two new FastAPI endpoints under `/api/knowledge/`:

- `GET /search?q=&type=&limit=` — semantic search returning ranked results with chunk snippets and section context
- `GET /notes/{note_id}` — full note content for the preview pane

The frontend renders results as a keyboard-navigable list. Selecting a result opens a note preview within the overlay, scrolled to the matching section heading.

| Aspect           | Today                        | Proposed                                              |
| ---------------- | ---------------------------- | ----------------------------------------------------- |
| Knowledge access | MCP tools only (AI sessions) | Direct browser UI on the homepage                     |
| Search method    | None (user-facing)           | pgvector semantic search via voyage-4-nano embeddings |
| Note viewing     | Read raw files on disk       | Inline preview with section-level scroll targeting    |
| Route            | N/A                          | In-page overlay — no new URL                          |

---

## Architecture

```mermaid
graph LR
    KB[⌘K keypress] --> OV[Search overlay mounts]
    OV --> INP[Search input]
    INP -->|debounce 300ms| API1[GET /api/knowledge/search]
    API1 --> EMB[EmbeddingClient.embed query]
    EMB --> PG[(PostgreSQL + pgvector)]
    PG -->|cosine search| API1
    PG -->|best chunk per note| API1
    API1 --> RES[Results list]
    RES -->|Enter / click| API2[GET /api/knowledge/notes/note_id]
    API2 --> VAULT[/vault filesystem]
    VAULT --> PRV[Note preview]
    PRV -->|§ section scroll| HEAD[Heading anchor]
```

### Backend: `knowledge/router.py`

New `APIRouter(prefix="/api/knowledge")`, registered in `app/main.py`.

**`GET /search`**

1. Embed `q` via `await EmbeddingClient().embed(q)` — 1024-dim voyage-4-nano vector
2. Query `KnowledgeStore.search_notes(vector, limit=limit)` with optional `type` filter on `notes.type`
3. Fetch best matching chunk per result in a single batched query:
   ```sql
   SELECT DISTINCT ON (note_fk)
     note_fk, section_header, chunk_text
   FROM knowledge.chunks
   WHERE note_fk = ANY(:note_fk_ids)
   ORDER BY note_fk, embedding <=> :query_vector
   ```
4. Return results with snippet and section fields

Response schema:

```json
{
  "results": [
    {
      "note_id": "abc123",
      "title": "Attention Is All You Need",
      "path": "_processed/papers/attention.md",
      "type": "paper",
      "tags": ["ml", "transformers"],
      "score": 0.91,
      "snippet": "The transformer architecture replaces recurrence entirely...",
      "section": "## Architecture"
    }
  ]
}
```

**`GET /notes/{note_id}`**

Look up the note row to get `path`, then read the raw file from `Path(VAULT_ROOT) / path`. Returns metadata plus full markdown content.

### Frontend: search overlay state machine

```
closed ──⌘K──► open (idle, no results)
open   ──type──► open (searching → results)
open   ──↑↓──► open (activeIndex changes)
open   ──Enter──► preview (selectedNote set)
preview ──Esc──► open (back to results)
open   ──Esc──► closed
```

### Markdown rendering — heading-only parse

The note preview renders with a minimal regex renderer rather than `<pre>` or a full markdown library. This is required for section-level scroll targeting.

Strategy: convert `^(#{1,3}) (.+)$` lines to `<h1–3 id="slug">` elements; convert blank-line-separated paragraphs to `<p>` elements; leave everything else as text. No syntax highlighting, no external dependency.

This gives:

- Scrollable headings via `document.getElementById(slug).scrollIntoView()`
- Readable body text without markdown syntax noise
- Zero npm dependencies added

---

## Implementation

### Phase 1: Backend

- [ ] Create `projects/monolith/knowledge/router.py` with `GET /search` and `GET /notes/{note_id}`
- [ ] Register router in `app/main.py` (`app.include_router(knowledge_router)`)
- [ ] Add `type` filter param to `KnowledgeStore.search_notes()` (optional `WHERE notes.type = :type`)
- [ ] Implement batched best-chunk query (`DISTINCT ON`) — avoid N+1 to Postgres
- [ ] Add `VAULT_ROOT` env var reading to router (already used in `knowledge/service.py`)
- [ ] Write tests: search with and without `type` filter, empty query, missing note_id

### Phase 2: Frontend overlay

- [ ] Add `searchOpen`, `searchQuery`, `searchResults`, `selectedNote`, `activeIndex`, `searching` state to `+page.svelte`
- [ ] Add `⌘K` global keydown handler; do NOT intercept `Tab` (breaks standard focus movement)
- [ ] Implement debounced fetch to `/api/knowledge/search` (300ms)
- [ ] Empty query idle state: show nothing — just the input and filter pills. No "recently indexed" list (recently indexed ≠ recently relevant)
- [ ] Implement result keyboard navigation (`↑`/`↓`/`Enter`/`Esc`)
- [ ] Implement overlay close on `Esc` (from results) and back-to-results on `Esc` (from preview)
- [ ] Add `⌘K` hint to capture textarea footer (same style as existing `⌘ enter` hint)

### Phase 3: Note preview

- [ ] Implement minimal heading-only markdown renderer (no npm dependency):
  - `^(#{1,3}) (.+)$` → `<h1–3 id="{slug}">`
  - Blank-line-separated blocks → `<p>`
  - Everything else: text nodes
- [ ] On preview mount, call `document.getElementById(sectionSlug)?.scrollIntoView({ block: 'start' })`
- [ ] `← back · esc` shown as fixed element at top of preview (not inline with scrolling content)
- [ ] Tags rendered as `tag1 · tag2 · tag3` (middle dot separator, `--fg-tertiary`)

---

## Design Decisions

### Search trigger: ⌘K only (not Tab)

`Tab` intercept was considered but rejected — it conflicts with standard browser focus movement and would surprise users tabbing to the right panel. `⌘K` is the established convention for command palettes (Linear, Raycast, Notion) and requires no user education.

### Overlay: mode shift, not modal

The overlay uses `position: fixed; inset: 0; background: var(--bg); z-index: 100` with no backdrop, shadow, or border-radius. This makes it feel like the page changed state rather than a popup appeared. Consistent with the app's personality — no chrome, no decoration.

### Idle state: empty, not "recent"

When the search query is empty, the overlay shows only the input and type filter pills — no pre-populated list. "Recently indexed" notes surface fleeting captures (lowest-value content), not the most relevant notes. Silence signals "waiting for your query" and avoids false affordances.

### Loading state: ghost results

While a search is in-flight (`searching === true`), previous results remain visible at reduced opacity (`opacity: 0.5`). This avoids a flash of empty content and gives the user a sense of continuity. The embedding + pgvector call typically takes 200–500ms — long enough to notice, short enough that a spinner would feel heavy.

### Markdown rendering: heading-only parse

Full markdown libraries (marked, micromark) add ~50KB to the bundle and render more than needed. A `<pre>` with `white-space: pre-wrap` is simple but cannot support heading-level scroll targeting — the core feature. A 15-line regex renderer produces `<h1–3>` and `<p>` elements, enables `scrollIntoView()`, and adds zero dependencies.

### Section scroll: slug from section_header

The API returns `section: "## Architecture"`. The frontend strips the `#` prefix and slugifies the title (`architecture`) to match the generated heading `id`. This avoids storing IDs server-side.

---

## Security

No new secrets or external network calls. The `/api/knowledge/` endpoints are internal — same auth surface as all other monolith API routes. `VAULT_ROOT` path is read from environment, not user input. Note content is read-only via this interface.

---

## Risks

| Risk                                       | Likelihood | Impact                       | Mitigation                                                                         |
| ------------------------------------------ | ---------- | ---------------------------- | ---------------------------------------------------------------------------------- |
| Embedding server unavailable               | Low        | Search broken                | Return `503` with clear error; overlay shows "search unavailable" in `--danger`    |
| Vault file deleted between index and fetch | Low        | `GET /notes/{id}` 404        | Return `404`; frontend shows "note not found" and clears preview                   |
| Large note content slow to render          | Low        | Preview lag                  | Render is synchronous DOM ops — no async needed; content capped by vault note size |
| Heading slug collision within a note       | Very low   | Scroll targets wrong section | Append `-2`, `-3` etc. to duplicate slugs (standard slugify behaviour)             |

---

## Open Questions

1. Should the overlay remember the last search query when reopened within the same session? (Probably yes — same UX as browser search history)
2. Should `type` filter state persist across overlay open/close cycles, or reset each time?
3. Future: "open in Obsidian" button using `obsidian://open?vault=jomcgi&file=<path>` deep link — worth adding as a minor enhancement in Phase 3.

---

## References

| Resource                                                     | Relevance                                                                   |
| ------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `projects/monolith/knowledge/store.py`                       | `KnowledgeStore.search_notes()` — the semantic search method this builds on |
| `projects/monolith/knowledge/models.py`                      | `Note`, `Chunk`, `NoteLink` SQLModel definitions                            |
| `projects/monolith/shared/embedding.py`                      | `EmbeddingClient.embed()` — async, voyage-4-nano, 1024-dim                  |
| `projects/monolith/frontend/src/routes/private/+page.svelte` | Existing homepage being modified                                            |
| `projects/monolith/frontend/src/routes/+layout.svelte`       | Design system CSS variables                                                 |
| `docs/decisions/services/001-discord-history-backfill.md`    | Prior services ADR for format reference                                     |
