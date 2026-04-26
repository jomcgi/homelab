# Notes Page (`private.jomcgi.dev/notes`) — Design

**Author:** Joe McGinley
**Created:** 2026-04-26
**Branch:** `feat/notes-page`
**Prototype:** `~/repos/temp/notes-prototype.html` (D3 force graph, sample data)

---

## Goal

Add an interactive knowledge-graph view of the personal vault at
`private.jomcgi.dev/notes`. Backed by the existing `monolith/knowledge`
FastAPI surface. Heavily CDN-cached at the graph-structure layer; individual
note bodies fetched on click.

Same visit, the public homepage and the new private notes page should feel
like the same product — **shared design tokens, shared nav, one visual
language across the two stacks** (Astro public, SvelteKit private).

Out of scope:

- Re-skinning the existing `/private` home page (capture/schedule/todos)
  to the unified rack aesthetic — separate follow-up PR.
- Auth changes for `private.jomcgi.dev` — addressed separately.
- Computed graph clustering / community detection — not needed; we cluster
  by `Note.type`.

---

## Approach summary

1. **Backend:** add `GET /api/knowledge/graph` to the existing
   `monolith/knowledge/router.py`. Returns the whole graph in one payload
   (~80 KB gzipped at current vault size). CDN-cached via `Cache-Control`.
2. **Shared web kit:** promote `projects/websites/shared/` to be the
   canonical token + nav source for both stacks. Drop dark mode entirely.
   Public site’s rack/manifest aesthetic is the gold standard.
3. **Frontend:** new SvelteKit route `monolith/frontend/src/routes/private/notes/`
   with SSR-fetched graph payload, client-side d3 force sim, side panel that
   fetches individual notes on click.
4. **Nav:** white bar with black underline, `home ↔ notes`, rendered both
   as `Nav.astro` (public) and `Nav.svelte` (private), shared CSS in
   `projects/websites/shared/nav/nav.css`.

---

## Architecture

### Shared web kit at `projects/websites/shared/`

```
projects/websites/shared/
├── tokens.css            # canonical CSS custom properties
├── reset.css             # baseline reset (already exists)
├── components.css        # shared atomic styles
├── nav/
│   ├── Nav.astro         # public renderer
│   ├── Nav.svelte        # private renderer
│   ├── nav.css           # shared styling
│   └── routes.js         # single nav link list
└── BUILD                 # extend exports for cross-stack consumption
```

Both stacks import via `@import "../../../websites/shared/tokens.css";`
relative path. Vite resolves it natively. Bazel needs the file in the
sandbox at build time — handled by adding the shared target to `data` deps
on the consuming `BUILD` files.

**Fallback if cross-package CSS import is fiddly under
`rules_js`/Bazel:** duplicate the markup files (`Nav.astro`,
`Nav.svelte`) into each stack and share only the CSS. Same one source of
truth for styling, two copies of ~30 lines of HTML — graceful degradation.

### Token reconciliation

Public site is the gold standard. Private adopts public's values; both
drop dark-mode mechanisms.

| Token                  | Public today                   | Private today                       | Unified                                         |
| ---------------------- | ------------------------------ | ----------------------------------- | ----------------------------------------------- |
| `--bg`                 | `#fff`                         | `#fff`                              | `#fff`                                          |
| `--fg`                 | `#000`                         | `#111`                              | `#000`                                          |
| `--border`             | `#000`                         | `#d4d4d4`                           | `#000` (heavy 2px)                              |
| `--font-mono`          | `ui-monospace, "SF Mono", ...` | `"Space Mono"`                      | `ui-monospace, "SF Mono", ...` (public's stack) |
| `--accent`             | `#0066ff`                      | (none)                              | `#0066ff`                                       |
| `--st-ok / warn / err` | present                        | (only `--danger`)                   | full triad on both sides                        |
| Dark mode              | `body.dark` + localStorage     | `prefers-color-scheme` + `.theme-*` | **dropped entirely**                            |

New tokens (added to shared `tokens.css`):

```css
--yellow: #f5d90a;
--coral: #ff6b5b;
--green: #5dd879;
--cream: #f1ebdc;
--grey: #8a857a;
/* cluster aliases — only the notes graph references these */
--cluster-atom: var(--yellow);
--cluster-raw: var(--grey);
--cluster-gap: var(--coral);
--cluster-active: var(--accent);
--cluster-paper: var(--green);
--cluster-other: var(--cream);
```

Private-only intermediate greys (`--fg-secondary`, `--fg-tertiary`,
`--surface`, `--danger`) are aliased once in
`monolith/frontend/src/lib/global.css` to shared-token equivalents
(`var(--muted)`, `#999`, `#f5f5f5`, `var(--st-err)`). They exist because
the existing `/private` UI already references them; aliasing is cheaper
than a renaming pass.

### What changes per stack

**Public Astro (`projects/websites/jomcgi.dev/`):**

- `tokens.css` keeps existing values; `body.dark` block is deleted from
  `tokens.css`.
- `index.astro` removes the INVERT button, the `<script is:inline>`
  localStorage dark-mode logic, and the `.dark-pending` class machinery
  (~25 lines).
- All pages get `<Nav />` above the content container.

**Private Svelte (`projects/monolith/frontend/`):**

- `src/lib/global.css` deletes its entire `:root` token block AND the
  `prefers-color-scheme` / `.theme-dark` / `.theme-light` blocks; adds
  `@import "../../../websites/shared/tokens.css";` and the four
  intermediate-grey aliases.
- `src/routes/+layout.svelte` adds `<Nav />` above the slot.

---

## Backend

### `GET /api/knowledge/graph`

```json
{
  "nodes": [{ "id": "abc-123", "title": "adr-15-mtls", "type": "atom" }],
  "edges": [
    {
      "source": "abc-123",
      "target": "def-456",
      "kind": "edge",
      "edge_type": "refines"
    }
  ],
  "indexed_at": "2026-04-26T14:23:11Z"
}
```

- `id` = `Note.note_id` (stable graph identity).
- `type` is the existing `Note.type` column. Unknown types fall through
  to the `--cluster-other` cream bucket on the client; the legend lists
  every type that appears in the current payload.
- **Edges with unresolved targets are dropped server-side.** A
  `NoteLink.target_id` can point to a string that doesn’t match any
  `note_id` (raw wikilink that hasn’t been gap-promoted). Gap-promoted
  wikilinks survive as edges into `type=gap` nodes, so the graph
  naturally surfaces "missing knowledge" as coral nodes.
- **No `degree` field** — client iterates edges once on load. Saves
  ~30 bytes/node and keeps the endpoint pure.
- `indexed_at = max(notes.indexed_at)` so the status bar can render
  "LAST INDEX 5M AGO" with no extra round-trip.

### Implementation

New `KnowledgeStore.get_graph()` method in
`monolith/knowledge/store.py` — two `SELECT`s, joined client-side in
Python:

```python
def get_graph(self) -> dict:
    notes = self.session.exec(
        select(Note.note_id, Note.title, Note.type, Note.indexed_at)
    ).all()
    note_ids = {row.note_id for row in notes}
    links = self.session.exec(
        select(
            Note.note_id.label("source"),
            NoteLink.target_id.label("target"),
            NoteLink.kind, NoteLink.edge_type,
        ).join(Note, NoteLink.src_note_fk == Note.id)
    ).all()
    edges = [
        {"source": l.source, "target": l.target,
         "kind": l.kind, "edge_type": l.edge_type}
        for l in links if l.target in note_ids
    ]
    return {
        "nodes": [{"id": n.note_id, "title": n.title, "type": n.type} for n in notes],
        "edges": edges,
        "indexed_at": max((n.indexed_at for n in notes), default=None),
    }
```

Router exposes it with the cache header from `cache-headers.js` mirrored
into FastAPI:

```python
@router.get("/graph")
def get_graph(
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = (
        "public, s-maxage=60, "
        "stale-while-revalidate=86400, "
        "stale-if-error=31536000"
    )
    return KnowledgeStore(session).get_graph()
```

### Caching strategy

Two layers, same TTL semantics:

1. **Page route** (`/notes` SvelteKit SSR): `+page.server.js` calls
   `setHeaders({ "cache-control": PAGE_CACHE_CONTROL })` (already exported
   from `$lib/cache-headers.js`). HTML+graph payload caches together at
   the edge.
2. **Graph endpoint** (`/api/knowledge/graph`): same `Cache-Control`
   header from FastAPI. Useful if the page route is bypassed.

`s-maxage=60, stale-while-revalidate=24h, stale-if-error=1y`. The
gardener mutates the graph slowly (scheduled runs); 60s freshness is
generous and SWR/SIE keep the page resilient when the cluster is sleepy.

The `/api/knowledge/notes/{id}` endpoint stays uncached. Notes are
small, only fetched on click, and cache-busting per-note on edits is
harder than for the whole graph.

---

## Frontend

### Route structure

```
monolith/frontend/src/routes/private/notes/
├── +page.server.js     # SSR fetch; sets cache-control
├── +page.svelte        # composes the components
```

```js
// +page.server.js
import { PAGE_CACHE_CONTROL } from "$lib/cache-headers.js";
const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch, setHeaders }) {
  setHeaders({ "cache-control": PAGE_CACHE_CONTROL });
  const res = await fetch(`${API_BASE}/api/knowledge/graph`, {
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    throw error(503, "graph unavailable");
  }
  return { graph: await res.json() };
}
```

### Components

```
monolith/frontend/src/lib/components/notes/
├── KnowledgeGraph.svelte    # canvas, force sim, hit-test, render loop
├── NotePanel.svelte         # right-side, on-click fetch + markdown render
├── GraphLegend.svelte       # bottom-left, type filter
├── GraphSearch.svelte       # top-left, debounced filter
├── StatusBar.svelte         # top stat strip (white, dashed dividers)
├── markdown.js              # minimal renderer (lifted from prototype)
└── clusters.js              # type → cluster colour map
```

All components use Svelte 5 runes (`$state`, `$derived`, `$effect`) —
matches the existing private home idiom.

### Data flow on selection

```
canvas click → KnowledgeGraph fires {nodeClick, id}
  → +page.svelte sets selectedNoteId = id
  → NotePanel $effect: fetch /api/knowledge/notes/{id}
  → renders markdown via markdown.js
    → [[wikilinks]] resolved against title→id map (built once from graph nodes)
    → click on wikilink → selectedNoteId = target.id (loops back)
    → focusNode(target) re-centers the canvas
```

**Backlinks computed client-side** from the full graph payload —
`graph.edges.filter(e => e.target === id)`. No new backend method needed.

### Cluster colour assignment

```js
// clusters.js
export const CLUSTER_COLORS = {
  atom: "var(--cluster-atom)",
  fact: "var(--cluster-atom)", // legacy alias
  raw: "var(--cluster-raw)",
  gap: "var(--cluster-gap)",
  active: "var(--cluster-active)",
  paper: "var(--cluster-paper)",
};
const FALLBACK = "var(--cluster-other)";
export const colorFor = (type) => CLUSTER_COLORS[type] ?? FALLBACK;
```

Unknown types auto-bucket into the cream `--cluster-other` group. The
legend lists every type that appears in the current payload. Adding a
dedicated colour for a new type is a one-line addition.

### Filtering

Search and legend filtering are **purely client-side**, no server hits
on keystroke. CDN-cached graph payload is the win — every interaction is
a free local recompute.

### Nav

```js
// projects/websites/shared/nav/routes.js
export const NAV_LINKS = [
  { label: "home", href: "https://public.jomcgi.dev/" },
  { label: "notes", href: "https://private.jomcgi.dev/notes" },
];
```

```css
/* projects/websites/shared/nav/nav.css */
.nav {
  background: var(--bg); /* white */
  color: var(--fg); /* black ink */
  border-bottom: var(--border-heavy);
  padding: var(--space-xs) var(--space-md);
  display: flex;
  gap: var(--space-lg);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}
.nav a {
  padding: 4px 0;
  opacity: 0.55;
}
.nav a:hover {
  opacity: 1;
}
.nav a.active {
  opacity: 1;
  text-decoration: underline;
  text-underline-offset: 4px;
}
```

Active state: `Nav.svelte` uses `$page.url.pathname`; `Nav.astro` uses
`Astro.url.pathname`. Cross-domain links can never be "active" on the
other domain, so each side computes only its own active link.

---

## Visual treatment of the graph

Public site is the gold standard. The notes graph adopts:

- Pure `#fff` stage; no cream paper.
- 2px black heavy borders on side panel, search box, legend, status bar.
- No soft shadows. Hard `4px 4px 0 #000` blocks where lift is needed
  (the prototype's brutalist convention — already rack-aligned).
- Uppercase letterspaced section labels at 9–11px,
  `letter-spacing: 0.08–0.16em`, `font-weight: 700`.
- `--accent: #0066ff` blue replaces the prototype's coral for hover /
  selection emphasis on the chrome.
- **Cluster node fills keep their bright colours.** Yellow / coral /
  blue / green / cream / grey nodes on a stark white canvas. Chrome is
  monochrome; nodes are the only colourful elements.
- System monospace stack — no JetBrains Mono.

---

## Error handling & loading

| Surface         | Loading                                                                          | Failure                                                                                                                                    |
| --------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Page route SSR  | SvelteKit hydration delay covers; graph ships in payload                         | `error(503)` → minimal black-bordered "graph unavailable" card. `stale-if-error=1y` means CDN serves last good payload across most outages |
| Note panel      | Title + eyebrow render immediately from local node; body shows italic "loading…" | Title + `--st-err` red note "couldn't load note body". Click outside / esc dismisses                                                       |
| Search / legend | Purely local — no async surface                                                  | n/a                                                                                                                                        |

Per CLAUDE.md (no error handling for impossible scenarios): no
client-side validation of graph payload shape — backend response is
trusted. Duplicate titles in `title→id` map: last write wins, no
disambiguation in MVP.

---

## Tests

Inner loop is "push to test" — no local Bazel runs.

| Layer    | What                                                        | Where                                                                          |
| -------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Backend  | `GET /api/knowledge/graph` shape & filtering                | New cases in `monolith/knowledge/router_test.py`                               |
| Backend  | `KnowledgeStore.get_graph()` SQL                            | New cases in `monolith/knowledge/store_test.py`                                |
| Frontend | Markdown renderer (wikilinks, tags, blockquote, dead links) | `markdown.test.js` (pure function)                                             |
| Frontend | Backlink derivation                                         | `KnowledgeGraph.test.js` (small unit)                                          |
| Frontend | Page route load shape                                       | `notes/+page.server.test.js`                                                   |
| Frontend | Force sim, canvas hit-testing                               | **Not unit tested** — d3 is upstream-tested; canvas hit-testing needs real DOM |
| E2E      | Click node → panel opens → click wikilink → panel updates   | If `monolith/frontend/e2e/` has an existing harness, add one test              |

---

## Bazel build wiring

1. `projects/websites/shared/BUILD` — extend `filegroup` (or add a new
   `js_library`) covering `tokens.css`, `reset.css`, `components.css`,
   `nav/*`. Visibility opens to
   `//projects/monolith/frontend/...` and existing public consumers.
2. `projects/monolith/frontend/BUILD` — add the shared target to
   `data` deps of the existing Svelte build target so Vite finds it
   in the sandbox.
3. `projects/websites/jomcgi.dev/BUILD` — already references the shared
   target; extend to include `nav/`.

Fallback (if cross-package CSS imports collide with `rules_js`'s sandbox
expectations): duplicate the two ~30-line nav files into each stack.
Same single CSS source of truth, two copies of HTML markup.

---

## Migration of existing dark mode

**Public site (`jomcgi.dev/src/pages/index.astro`):**

- Delete the inline `<script is:inline>` blocks that read/write
  `localStorage.darkMode` and toggle `body.dark` / `.dark-pending`.
- Delete the INVERT button.
- Delete the `body.dark` block from `shared/tokens.css`.

**Private site (`monolith/frontend/src/lib/global.css`):**

- Delete the `@media (prefers-color-scheme: dark)` block.
- Delete the `:root.theme-dark` and `:root.theme-light` blocks.

No user-facing migration needed — the toggle was opt-in on public; on
private it followed the OS preference. Both flatten to light mode.

---

## What ships

- `feat/notes-page` branch with one PR containing:
  - New backend endpoint + tests
  - Promoted shared web kit (tokens reconciled, nav added)
  - New `/notes` route + components
  - Public Astro site dark-mode removal
- Manual QA on push (CI tests cover unit-testable surfaces; force-sim,
  canvas, and end-to-end clicking are eyes-on).

## What doesn’t

- `/private` home (capture/schedule/todos) re-skin to the rack aesthetic
  — separate follow-up PR.
- Auth on `private.jomcgi.dev` — separate ongoing work.
- Server-side filtering / pagination of the graph — only justified if
  the vault grows past the point where ~80 KB gzipped is too big.
