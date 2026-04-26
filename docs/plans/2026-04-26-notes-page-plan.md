# Notes Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `private.jomcgi.dev/notes` — a force-directed knowledge-graph view backed by the existing `monolith/knowledge` FastAPI surface, with a shared design language across the public Astro and private SvelteKit stacks.

**Architecture:** New `GET /api/knowledge/graph` endpoint returns the whole graph in one CDN-cached payload. SvelteKit route SSR-fetches it, mounts a d3 force sim on a canvas, opens individual notes via direct (uncached) backend fetches on click. Tokens + nav consolidated under `projects/websites/shared/`; dark mode dropped from both stacks; public Astro home is the visual gold standard.

**Tech Stack:** FastAPI / SQLModel (backend), SvelteKit 5 + Vite + Vitest (private frontend), Astro (public frontend), d3-force / d3-zoom / d3-quadtree, pgvector + Postgres (existing), Bazel + `aspect_rules_js` (build).

**Design doc:** `docs/plans/2026-04-26-notes-page-design.md` (committed in the same worktree).

**Worktree:** `/tmp/claude-worktrees/notes-page` on branch `feat/notes-page`.

**Important constraints (from `.claude/CLAUDE.md`):**

- **No local test runs.** All `pytest` / `vitest` / `bazel test` defer to BuildBuddy CI on the pushed branch. Each task writes the test AND the implementation, then commits both. Verification happens at end-of-plan via `gh pr checks <number> --watch` and the `mcp__buildbuddy__*` tools.
- **Conventional Commits** are enforced by a `commit-msg` hook. Format: `<type>(<scope>): <description>`.
- **Co-author footer** required on every commit:
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- **One commit per task** unless a task explicitly batches.

---

## Phase 1 — Backend (graph endpoint)

### Task 1: `KnowledgeStore.get_graph()` with tests

**Files:**

- Modify: `projects/monolith/knowledge/store.py` (add new method on the existing `KnowledgeStore` class)
- Modify: `projects/monolith/knowledge/store_test.py` (new test cases)

**Step 1: Write the failing test**

Append to `projects/monolith/knowledge/store_test.py`:

```python
def test_get_graph_returns_nodes_and_edges(session):
    store = KnowledgeStore(session)

    # Seed two notes with a link between them.
    store.upsert_note(
        path="a.md",
        content_hash="h-a",
        metadata=_meta(note_id="id-a", title="A", type="atom"),
    )
    store.upsert_note(
        path="b.md",
        content_hash="h-b",
        metadata=_meta(note_id="id-b", title="B", type="atom"),
    )
    store.replace_note_links("id-a", [{"target_id": "id-b", "kind": "link"}])

    result = store.get_graph()

    assert {n["id"] for n in result["nodes"]} == {"id-a", "id-b"}
    assert any(
        e["source"] == "id-a" and e["target"] == "id-b" for e in result["edges"]
    )
    assert result["indexed_at"] is not None


def test_get_graph_drops_edges_with_unresolved_targets(session):
    store = KnowledgeStore(session)
    store.upsert_note(
        path="a.md",
        content_hash="h-a",
        metadata=_meta(note_id="id-a", title="A", type="atom"),
    )
    # Edge points at a target that does not exist in the notes table.
    store.replace_note_links("id-a", [{"target_id": "nonexistent", "kind": "link"}])

    result = store.get_graph()

    assert any(n["id"] == "id-a" for n in result["nodes"])
    assert result["edges"] == []
```

> Check the existing `_meta(...)` helper / `replace_note_links` signature in `store_test.py` — adjust the calls to match the local conventions if they differ. The test names and asserts are what matter.

**Step 2: Add the implementation**

In `projects/monolith/knowledge/store.py`, add (near other read methods):

```python
def get_graph(self) -> dict:
    """Return the full knowledge graph: nodes (notes) and edges (links).

    Edges with unresolved targets (target_id pointing to a string that doesn't
    match any note's note_id) are dropped — gap-promoted wikilinks survive as
    edges into type='gap' nodes.
    """
    note_rows = self.session.exec(
        select(Note.note_id, Note.title, Note.type, Note.indexed_at)
    ).all()
    note_ids = {row.note_id for row in note_rows}

    link_rows = self.session.exec(
        select(
            Note.note_id.label("source"),
            NoteLink.target_id.label("target"),
            NoteLink.kind,
            NoteLink.edge_type,
        ).join(Note, NoteLink.src_note_fk == Note.id)
    ).all()

    edges = [
        {
            "source": row.source,
            "target": row.target,
            "kind": row.kind,
            "edge_type": row.edge_type,
        }
        for row in link_rows
        if row.target in note_ids
    ]

    return {
        "nodes": [
            {"id": row.note_id, "title": row.title, "type": row.type}
            for row in note_rows
        ],
        "edges": edges,
        "indexed_at": (
            max((row.indexed_at for row in note_rows), default=None)
            or None
        ),
    }
```

The `indexed_at` value is serialised by FastAPI to ISO 8601 automatically; no manual `.isoformat()` call needed at this layer.

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py
git commit -m "$(cat <<'EOF'
feat(knowledge): add get_graph store method

New KnowledgeStore.get_graph() returns the full knowledge graph as
nodes and edges in one payload. Edges with unresolved targets are
dropped server-side so gap-promoted wikilinks survive as edges into
type='gap' nodes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `GET /api/knowledge/graph` route + tests

**Files:**

- Modify: `projects/monolith/knowledge/router.py`
- Modify: `projects/monolith/knowledge/router_test.py`

**Step 1: Write the failing test**

Append to `router_test.py` (mirror the existing pattern of using a TestClient against the FastAPI app):

```python
def test_graph_endpoint_returns_nodes_edges_and_cache_header(client, session):
    # Seed a tiny graph (two atoms linked).
    store = KnowledgeStore(session)
    store.upsert_note(
        path="a.md",
        content_hash="h-a",
        metadata=_meta(note_id="id-a", title="A", type="atom"),
    )
    store.upsert_note(
        path="b.md",
        content_hash="h-b",
        metadata=_meta(note_id="id-b", title="B", type="atom"),
    )
    store.replace_note_links("id-a", [{"target_id": "id-b", "kind": "link"}])

    response = client.get("/api/knowledge/graph")

    assert response.status_code == 200
    body = response.json()
    assert {n["id"] for n in body["nodes"]} == {"id-a", "id-b"}
    assert body["edges"][0]["source"] == "id-a"
    assert body["edges"][0]["target"] == "id-b"

    cache_control = response.headers["cache-control"]
    assert "public" in cache_control
    assert "s-maxage=" in cache_control
    assert "stale-while-revalidate=" in cache_control
```

> Use the existing `client` and `session` fixtures from `router_test.py`. If the local convention is `TestClient(app)` constructed inline, mirror that.

**Step 2: Add the route**

In `projects/monolith/knowledge/router.py`, add near the existing `search_knowledge` route:

```python
_GRAPH_CACHE_CONTROL = (
    "public, s-maxage=60, "
    "stale-while-revalidate=86400, "
    "stale-if-error=31536000"
)


@router.get("/graph")
def get_graph(
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Return the full knowledge graph for the /notes visualisation.

    Heavily CDN-cached: the gardener mutates the graph on a schedule, so
    60s freshness with 24h SWR is generous and saves repeated DB hits.
    """
    response.headers["Cache-Control"] = _GRAPH_CACHE_CONTROL
    return KnowledgeStore(session).get_graph()
```

Add the `Response` import at the top of the file (`from fastapi import APIRouter, Depends, HTTPException, Query, Response`).

**Step 3: Commit**

```bash
git add projects/monolith/knowledge/router.py projects/monolith/knowledge/router_test.py
git commit -m "$(cat <<'EOF'
feat(knowledge): expose GET /api/knowledge/graph

CDN-cached endpoint returning the full knowledge graph in one payload
(~80 KB gzipped at current vault size). Backs the /notes visualisation
on private.jomcgi.dev. Cache-Control: 60s fresh, 24h SWR, 1y SIE.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Shared web kit (tokens + dark-mode removal)

### Task 3: Add new tokens, drop dark mode from `shared/tokens.css`

**Files:**

- Modify: `projects/websites/shared/tokens.css`

**Step 1: Edit the tokens file**

Replace the contents of `projects/websites/shared/tokens.css` with:

```css
:root {
  --bg: #fff;
  --fg: #000;
  --border: #000;
  --accent: #0066ff;
  --muted: #666;

  --st-ok: #00b300;
  --st-warn: #ff9900;
  --st-err: #cc0000;

  /* Bright accents — used by graph node fills, tag highlights. */
  --yellow: #f5d90a;
  --coral: #ff6b5b;
  --green: #5dd879;
  --cream: #f1ebdc;
  --grey: #8a857a;

  /* Cluster colour aliases — only the notes graph references these. */
  --cluster-atom: var(--yellow);
  --cluster-raw: var(--grey);
  --cluster-gap: var(--coral);
  --cluster-active: var(--accent);
  --cluster-paper: var(--green);
  --cluster-other: var(--cream);

  --font-mono:
    ui-monospace, "SF Mono", "Cascadia Mono", "Courier New", monospace;
  --line-height: 1.6;

  --text-xs: 10px;
  --text-sm: 12px;
  --text-base: 16px;
  --text-lg: 20px;
  --text-xl: 28px;
  --text-2xl: 36px;

  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 40px;
  --space-2xl: 60px;

  --border-heavy: 2px solid var(--fg);
  --border-thin: 1px solid var(--fg);
}
```

The `body.dark` block is **deleted** entirely.

**Step 2: Commit**

```bash
git add projects/websites/shared/tokens.css
git commit -m "$(cat <<'EOF'
feat(shared-tokens): add cluster colours, drop dark mode

Promotes shared/tokens.css to be the canonical token source for both
Astro public and SvelteKit private stacks. Adds bright accents
(--yellow/--coral/--green/--cream/--grey) and cluster-colour aliases
(--cluster-atom etc.) for the new /notes graph. Removes the body.dark
block — dark mode is dropped from both sites.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Strip dark mode from public Astro `index.astro`

**Files:**

- Modify: `projects/websites/jomcgi.dev/src/pages/index.astro`

**Step 1: Apply edits**

In `index.astro`:

1. Delete the entire first `<script is:inline>` block in `<head>` that sets `darkMode` from `localStorage` / `prefers-color-scheme` (around lines 386–398). Replace with nothing.

2. In `<body>`, delete the second `<script is:inline>` block (around lines 401–412) that toggles `body.dark` and defines `window.toggleDarkMode`.

3. Inside `.identity-header`, delete the INVERT button:
   ```html
   <button class="toggle-btn" onclick="toggleDarkMode()">INVERT</button>
   ```

After the edits, the page renders identically in light mode but has no dark-mode machinery.

**Step 2: Commit**

```bash
git add projects/websites/jomcgi.dev/src/pages/index.astro
git commit -m "$(cat <<'EOF'
chore(jomcgi.dev): drop dark-mode toggle and machinery

Removes the INVERT button, the localStorage-backed dark-mode script,
and the .dark-pending machinery from the public homepage. Aligns with
the unified light-mode-only design language being introduced for the
new /notes page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Strip dark mode from private Svelte `global.css`; import shared tokens

**Files:**

- Modify: `projects/monolith/frontend/src/lib/global.css`

**Step 1: Replace the file**

Replace contents with:

```css
/* ── Reset ──────────────────────────────────── */
*,
*::before,
*::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  font-size: clamp(16px, max(1.6vw, 2.6vh), 48px);
}

body {
  margin: 0;
  overflow: hidden;
}

ul {
  list-style: none;
}

a {
  color: inherit;
  text-decoration: none;
}

/* ── Shared design tokens (canonical source) ── */
@import "../../../websites/shared/tokens.css";

/* ── Private-only intermediate aliases ──────── */
/*
 * The existing /private UI references --fg-secondary, --fg-tertiary,
 * --surface, --danger. Alias them to shared-token equivalents instead
 * of doing a renaming sweep across components.
 */
:root {
  --font: var(--font-mono);
  --fg-secondary: var(--muted);
  --fg-tertiary: #999;
  --surface: #f5f5f5;
  --danger: var(--st-err);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
  }
}
```

The `--font` alias keeps the existing private home compiling — its components reference `var(--font)` directly.

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/lib/global.css
git commit -m "$(cat <<'EOF'
refactor(frontend): consume shared tokens; drop dark mode

Replaces the private frontend's local :root token block with an @import
of projects/websites/shared/tokens.css. Removes prefers-color-scheme and
.theme-dark/.theme-light blocks (dark mode is dropped). Keeps four
private-only intermediate aliases (--fg-secondary, --fg-tertiary,
--surface, --danger) so existing components keep compiling without a
renaming sweep.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Shared Nav

### Task 6: Create `shared/nav/` — routes, CSS, and the two renderers

**Files:**

- Create: `projects/websites/shared/nav/routes.js`
- Create: `projects/websites/shared/nav/nav.css`
- Create: `projects/websites/shared/nav/Nav.astro`
- Create: `projects/websites/shared/nav/Nav.svelte`

**Step 1: Create `routes.js`**

```js
// Single source of truth for the cross-domain nav.
//
// When `notes` becomes public, change the second link's href to a
// relative `/notes` path and serve from the public origin.
export const NAV_LINKS = [
  { label: "home", href: "https://public.jomcgi.dev/" },
  { label: "notes", href: "https://private.jomcgi.dev/notes" },
];
```

**Step 2: Create `nav.css`**

```css
.nav {
  background: var(--bg);
  color: var(--fg);
  border-bottom: var(--border-heavy);
  padding: var(--space-xs) var(--space-md);
  display: flex;
  gap: var(--space-lg);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  align-items: center;
}

.nav a {
  padding: 4px 0;
  opacity: 0.55;
  color: inherit;
  text-decoration: none;
  transition: opacity 0.15s ease;
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

**Step 3: Create `Nav.astro`**

```astro
---
import { NAV_LINKS } from "./routes.js";
import "./nav.css";

const currentHref = Astro.url.href;
function isActive(linkHref) {
  // Cross-domain nav — only matches when origin AND path align.
  try {
    const a = new URL(linkHref);
    const b = new URL(currentHref);
    return a.origin === b.origin && a.pathname === b.pathname;
  } catch {
    return false;
  }
}
---

<nav class="nav">
  {
    NAV_LINKS.map((link) => (
      <a href={link.href} class={isActive(link.href) ? "active" : ""}>
        {link.label}
      </a>
    ))
  }
</nav>
```

**Step 4: Create `Nav.svelte`**

```svelte
<script>
  import { page } from "$app/stores";
  import { NAV_LINKS } from "./routes.js";
  import "./nav.css";

  function isActive(linkHref, currentUrl) {
    try {
      const a = new URL(linkHref);
      return a.origin === currentUrl.origin && a.pathname === currentUrl.pathname;
    } catch {
      return false;
    }
  }
</script>

<nav class="nav">
  {#each NAV_LINKS as link}
    <a href={link.href} class={isActive(link.href, $page.url) ? "active" : ""}>
      {link.label}
    </a>
  {/each}
</nav>
```

**Step 5: Commit**

```bash
git add projects/websites/shared/nav/
git commit -m "$(cat <<'EOF'
feat(shared-nav): add cross-stack Nav component

Two-link nav (home / notes) shared by Astro public and SvelteKit
private stacks. Single CSS source in shared/nav/nav.css; Nav.astro and
Nav.svelte render identical markup. Cross-domain links match the
active state by origin+pathname.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Wire Nav into the public Astro site

**Files:**

- Modify: `projects/websites/jomcgi.dev/src/pages/index.astro`

**Step 1: Add the import and render the nav**

Near the top of the frontmatter (the `---` block at the top), add:

```astro
import Nav from "../../../shared/nav/Nav.astro";
```

In `<body>`, **above** `<div class="container">`, add:

```astro
<Nav />
```

**Step 2: Commit**

```bash
git add projects/websites/jomcgi.dev/src/pages/index.astro
git commit -m "$(cat <<'EOF'
feat(jomcgi.dev): mount shared Nav at top of homepage

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

> If `cv.astro`, `engineering.astro`, etc. should also have the nav, repeat the import + `<Nav />` insertion in each — but only if you want them in the cross-page wiring now. Out-of-scope for this PR if uncertain.

---

### Task 8: Wire Nav into the private Svelte layout

**Files:**

- Modify: `projects/monolith/frontend/src/routes/+layout.svelte`

**Step 1: Replace the layout**

```svelte
<script>
  import "$lib/global.css";
  import Nav from "../../../websites/shared/nav/Nav.svelte";
  let { children } = $props();
</script>

<Nav />

{@render children()}
```

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/routes/+layout.svelte
git commit -m "$(cat <<'EOF'
feat(frontend): mount shared Nav in private layout

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Bazel BUILD wiring for the shared web kit

**Files:**

- Modify: `projects/websites/shared/BUILD`
- Modify: `projects/websites/jomcgi.dev/BUILD` (only if the shared target's visibility is the blocker)
- Modify: `projects/monolith/frontend/BUILD` (add `data` dep on the shared target)

**Step 1: Open visibility on the shared target**

Edit `projects/websites/shared/BUILD`:

```python
load("@aspect_rules_js//js:defs.bzl", "js_library")

js_library(
    name = "css",
    srcs = glob(["*.css"]),
    visibility = [
        "//projects/monolith/frontend:__subpackages__",
        "//projects/websites:__subpackages__",
    ],
)

js_library(
    name = "nav",
    srcs = glob(["nav/**"]),
    visibility = [
        "//projects/monolith/frontend:__subpackages__",
        "//projects/websites:__subpackages__",
    ],
)
```

**Step 2: Add the deps on the consumers**

In `projects/monolith/frontend/BUILD`, find the existing target that compiles the SvelteKit app (likely a `js_run_devserver` or `vite_build` rule — it'll be the one with `srcs = glob(["src/**"])` or similar). Add to its `data`:

```python
data = [
    # …existing deps…
    "//projects/websites/shared:css",
    "//projects/websites/shared:nav",
],
```

In `projects/websites/jomcgi.dev/BUILD`, find the equivalent Astro build target and add the same two `data` deps if they aren't already covered by the existing `:css` reference. The `:css` target will have changed shape (now includes `nav/*.css` only via the second target), so confirm via:

```bash
bazel query 'kind("source file", deps(//projects/websites/shared:nav))'
```

> If `bazel query` reveals a path issue (e.g., `nav/Nav.svelte` not picked up because rules_js filters non-JS srcs from `js_library`), fall back to `filegroup` for the markup files:
>
> ```python
> filegroup(
>     name = "nav_files",
>     srcs = glob(["nav/**"]),
>     visibility = [...],
> )
> ```
>
> and depend on `//projects/websites/shared:nav_files` instead.

**Step 3: Commit**

```bash
git add projects/websites/shared/BUILD projects/monolith/frontend/BUILD projects/websites/jomcgi.dev/BUILD
git commit -m "$(cat <<'EOF'
build: expose shared web kit to private frontend

Adds visibility for //projects/monolith/frontend on the shared :css
target, introduces a :nav target covering shared/nav/, and threads
both as data deps into the private frontend and public Astro builds.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Frontend leaf utilities

### Task 10: Cluster colour map (`clusters.js`) + tests

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/clusters.js`
- Create: `projects/monolith/frontend/src/lib/components/notes/clusters.test.js`

**Step 1: Write the failing tests**

```js
// clusters.test.js
import { describe, it, expect } from "vitest";
import { colorFor, CLUSTER_COLORS } from "./clusters.js";

describe("colorFor", () => {
  it("returns the mapped colour for known types", () => {
    expect(colorFor("atom")).toBe("var(--cluster-atom)");
    expect(colorFor("gap")).toBe("var(--cluster-gap)");
    expect(colorFor("paper")).toBe("var(--cluster-paper)");
  });

  it("aliases legacy 'fact' type to atom colour", () => {
    expect(colorFor("fact")).toBe(CLUSTER_COLORS.atom);
  });

  it("falls back to --cluster-other for unknown types", () => {
    expect(colorFor("recipe")).toBe("var(--cluster-other)");
    expect(colorFor(undefined)).toBe("var(--cluster-other)");
    expect(colorFor(null)).toBe("var(--cluster-other)");
  });
});
```

**Step 2: Write `clusters.js`**

```js
export const CLUSTER_COLORS = {
  atom: "var(--cluster-atom)",
  fact: "var(--cluster-atom)", // legacy alias
  raw: "var(--cluster-raw)",
  gap: "var(--cluster-gap)",
  active: "var(--cluster-active)",
  paper: "var(--cluster-paper)",
};

const FALLBACK = "var(--cluster-other)";

export function colorFor(type) {
  return CLUSTER_COLORS[type] ?? FALLBACK;
}
```

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/clusters.js \
        projects/monolith/frontend/src/lib/components/notes/clusters.test.js
git commit -m "$(cat <<'EOF'
feat(notes): cluster colour map for graph node fills

Maps Note.type values to CSS custom-property references defined in
the shared tokens. Unknown types fall through to --cluster-other so
new types appear in the legend without a code change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Markdown renderer with wikilinks (`markdown.js`) + tests

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/markdown.js`
- Create: `projects/monolith/frontend/src/lib/components/notes/markdown.test.js`

**Step 1: Write the failing tests**

```js
// markdown.test.js
import { describe, it, expect } from "vitest";
import { renderMarkdown } from "./markdown.js";

describe("renderMarkdown", () => {
  const titleMap = new Map([["Existing Note", { id: "id-existing" }]]);

  it("renders headings", () => {
    const html = renderMarkdown("## hello", titleMap);
    expect(html).toContain("<h2>hello</h2>");
  });

  it("renders ordered list items as <ul>", () => {
    const html = renderMarkdown("- one\n- two", titleMap);
    expect(html).toMatch(/<ul>\s*<li>one<\/li>\s*<li>two<\/li>\s*<\/ul>/);
  });

  it("renders bold and italic", () => {
    const html = renderMarkdown("**bold** and *italic*", titleMap);
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
  });

  it("renders inline code", () => {
    const html = renderMarkdown("use `foo`", titleMap);
    expect(html).toContain("<code>foo</code>");
  });

  it("renders blockquotes", () => {
    const html = renderMarkdown("> a quote", titleMap);
    expect(html).toContain("<blockquote>");
  });

  it("resolves wikilinks to live anchors", () => {
    const html = renderMarkdown("see [[Existing Note]]", titleMap);
    expect(html).toContain('class="wl"');
    expect(html).toContain('data-id="id-existing"');
  });

  it("renders unresolved wikilinks as dead links", () => {
    const html = renderMarkdown("see [[Missing]]", titleMap);
    expect(html).toContain('class="wl dead"');
    expect(html).not.toContain("data-id=");
  });

  it("escapes HTML in source", () => {
    const html = renderMarkdown("<script>", titleMap);
    expect(html).toContain("&lt;script&gt;");
  });
});
```

**Step 2: Port the renderer from the prototype**

Create `markdown.js` lifting `esc`, `inline`, and `renderMarkdown` from `~/repos/temp/notes-prototype.html` lines 752–796, with one signature change: take `titleMap: Map<string, {id: string}>` instead of `Map<string, Node>`.

```js
const esc = (s) =>
  s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

function inline(s, titleMap) {
  // Protect tag spans before escaping (they came in as raw HTML).
  s = s.replace(/<span class="tag">(.*?)<\/span>/g, (_, t) => ` TAG${t}`);
  s = esc(s);
  s = s.replace(/ TAG(.*?)/g, (_, t) => `<span class="tag">${t}</span>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\[\[([^\]]+)\]\]/g, (_, t) => {
    const node = titleMap.get(t);
    const cls = node ? "wl" : "wl dead";
    const data = node ? ` data-id="${node.id}"` : "";
    return `<a class="${cls}"${data}>${esc(t)}</a>`;
  });
  return s;
}

export function renderMarkdown(md, titleMap) {
  const lines = md.split("\n");
  const out = [];
  let inUl = false;
  let inBq = false;
  const flushUl = () => {
    if (inUl) {
      out.push("</ul>");
      inUl = false;
    }
  };
  const flushBq = () => {
    if (inBq) {
      out.push("</blockquote>");
      inBq = false;
    }
  };

  for (const line of lines) {
    if (/^### (.+)$/.test(line)) {
      flushUl();
      flushBq();
      out.push(`<h3>${inline(line.replace(/^### /, ""), titleMap)}</h3>`);
    } else if (/^## (.+)$/.test(line)) {
      flushUl();
      flushBq();
      out.push(`<h2>${inline(line.replace(/^## /, ""), titleMap)}</h2>`);
    } else if (/^# (.+)$/.test(line)) {
      flushUl();
      flushBq();
    } else if (/^- (.+)$/.test(line)) {
      flushBq();
      if (!inUl) {
        out.push("<ul>");
        inUl = true;
      }
      out.push(`<li>${inline(line.replace(/^- /, ""), titleMap)}</li>`);
    } else if (/^> (.+)$/.test(line)) {
      flushUl();
      if (!inBq) {
        out.push("<blockquote>");
        inBq = true;
      }
      out.push(inline(line.replace(/^> /, ""), titleMap));
    } else if (line.trim() === "") {
      flushUl();
      flushBq();
    } else {
      flushUl();
      flushBq();
      out.push(`<p>${inline(line, titleMap)}</p>`);
    }
  }
  flushUl();
  flushBq();
  return out.join("\n");
}
```

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/markdown.js \
        projects/monolith/frontend/src/lib/components/notes/markdown.test.js
git commit -m "$(cat <<'EOF'
feat(notes): minimal markdown renderer with wikilinks

Ports the prototype's tiny markdown renderer; resolves [[wikilinks]]
against a title->id map, falls back to dotted dead-link rendering for
unresolved targets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Frontend components

### Task 12: Add d3 dependencies

**Files:**

- Modify: `projects/monolith/frontend/package.json`
- Modify: `projects/monolith/frontend/pnpm-lock.yaml` (regenerated)

**Step 1: Add the deps**

In `package.json`, add to `"dependencies"`:

```json
"d3-force": "^3.0.0",
"d3-quadtree": "^3.0.1",
"d3-selection": "^3.0.0",
"d3-zoom": "^3.0.0",
```

> Avoid the umbrella `"d3": "^7"` — we only need four sub-packages and the umbrella pulls in ~30 KB of unused code.

**Step 2: Run `pnpm install` (locally, in the worktree)**

```bash
cd projects/monolith/frontend && pnpm install
```

This regenerates `pnpm-lock.yaml`.

**Step 3: Commit**

```bash
git add projects/monolith/frontend/package.json projects/monolith/frontend/pnpm-lock.yaml
git commit -m "$(cat <<'EOF'
build(frontend): add d3-force/zoom/quadtree/selection deps

Pulls in the four d3 sub-packages needed for the /notes graph view.
Avoids the umbrella d3 package since only force-sim, zoom, quadtree,
and selection are used.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: `KnowledgeGraph.svelte`

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.svelte`

This is the largest component. It owns: canvas sizing, force sim, zoom/pan, quadtree hit-test, render loop, label drawing, click/hover dispatch.

**Step 1: Create the component**

Port from the prototype's `~/repos/temp/notes-prototype.html` structure, restructured as a Svelte 5 component with these props/events:

```svelte
<script>
  import { onMount, onDestroy, createEventDispatcher } from "svelte";
  import {
    forceSimulation,
    forceLink,
    forceManyBody,
    forceCollide,
    forceX,
    forceY,
  } from "d3-force";
  import { select } from "d3-selection";
  import { zoom as d3Zoom, zoomIdentity } from "d3-zoom";
  import { quadtree } from "d3-quadtree";
  import { colorFor } from "./clusters.js";

  const dispatch = createEventDispatcher();

  let {
    nodes,           // [{id, title, type, degree}]
    edges,           // [{source, target}]
    selectedId = null,
    searchTerm = "",
    activeClusters,  // Set<string>
  } = $props();

  let stageEl;
  let canvasEl;
  let hoverId = $state(null);
  let transform = $state(zoomIdentity);

  // … lift force-sim setup, render loop, hit-test, drawLabels(),
  //   focusNode() helpers from prototype lines 798–1192 …

  // Differences from prototype:
  // - colours come from getComputedStyle().getPropertyValue() to resolve
  //   `var(--cluster-atom)` etc. at runtime
  // - clicks dispatch `nodeClick` and `nodeHover` events instead of
  //   mutating module-level state
  // - dpr/resize obtained via ResizeObserver on stageEl
</script>

<div bind:this={stageEl} class="stage">
  <canvas bind:this={canvasEl}></canvas>
</div>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
  }
  .stage::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image: radial-gradient(rgba(0, 0, 0, 0.07) 1px, transparent 1px);
    background-size: 24px 24px;
    pointer-events: none;
  }
  canvas {
    display: block;
    cursor: grab;
  }
  canvas.panning {
    cursor: grabbing;
  }
  canvas.over-node {
    cursor: pointer;
  }
</style>
```

**Reference checkpoints from the prototype** (paste these helpers directly with minor adaptation):

| Prototype lines | What to lift                                           |
| --------------- | ------------------------------------------------------ |
| 798–809         | `resize()` — convert to ResizeObserver-driven          |
| 822–841         | force-sim construction; pre-tick 220 frames            |
| 843–853         | quadtree + `findNode(mx, my)`                          |
| 856–875         | `d3.zoom().filter().on('zoom', ...)`                   |
| 877–930         | mousedown/mousemove/mouseup → click vs. drag detection |
| 932–1018        | `render()` — full canvas draw, labels                  |
| 1020–1091       | `drawLabels()` — greedy collision detection            |
| 1146–1192       | `focusNode()` — viewport-aware zoom                    |

**Colour resolution at runtime:** because the canvas needs concrete colours (not `var(--cluster-atom)`), inside `onMount` cache the resolved colours once:

```js
const styles = getComputedStyle(document.documentElement);
const resolved = Object.fromEntries(
  ["atom", "raw", "gap", "active", "paper", "other"].map((k) => [
    k,
    styles.getPropertyValue(`--cluster-${k}`).trim() || "#ccc",
  ]),
);
function fillFor(node) {
  const key = node.type === "fact" ? "atom" : (node.type ?? "other");
  return resolved[key] ?? resolved.other;
}
```

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.svelte
git commit -m "$(cat <<'EOF'
feat(notes): KnowledgeGraph canvas component

Force-directed graph view ported from the prototype: d3 force sim on
canvas, quadtree hit-testing, zoom/pan, viewport-aware zoom-to-node,
greedy-collision label drawing. Cluster colours resolved at mount
time via getComputedStyle so CSS custom properties drive the palette.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: `NotePanel.svelte`

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/NotePanel.svelte`

**Step 1: Create the component**

```svelte
<script>
  import { renderMarkdown } from "./markdown.js";
  import { colorFor } from "./clusters.js";
  const API_BASE = ""; // same-origin from the SvelteKit page

  let {
    selectedId,
    nodes,
    edges,
    onSelect,
    onClose,
  } = $props();

  // Derived: lookups by id and title.
  let byId = $derived(new Map(nodes.map((n) => [n.id, n])));
  let titleMap = $derived(new Map(nodes.map((n) => [n.title, { id: n.id }])));
  let selectedNode = $derived(byId.get(selectedId));

  // Backlinks/outgoing computed from the graph payload — no extra fetch.
  let backlinks = $derived(
    edges
      .filter((e) => e.target === selectedId)
      .map((e) => byId.get(e.source))
      .filter(Boolean),
  );
  let outgoing = $derived(
    edges
      .filter((e) => e.source === selectedId)
      .map((e) => byId.get(e.target))
      .filter(Boolean),
  );

  // Note body fetch — direct, uncached.
  let body = $state("");
  let loading = $state(false);
  let error = $state("");
  let panelEl;

  $effect(() => {
    if (!selectedId) return;
    let cancelled = false;
    loading = true;
    error = "";
    body = "";
    fetch(`/api/knowledge/notes/${encodeURIComponent(selectedId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((data) => {
        if (!cancelled) body = data.content ?? "";
      })
      .catch(() => {
        if (!cancelled) error = "couldn't load note body";
      })
      .finally(() => {
        if (!cancelled) loading = false;
      });
    return () => {
      cancelled = true;
    };
  });

  function handleBodyClick(e) {
    const a = e.target.closest("a.wl[data-id]");
    if (!a) return;
    e.preventDefault();
    onSelect(a.dataset.id);
  }
</script>

{#if selectedNode}
  <aside class="panel" bind:this={panelEl}>
    <div class="panel-head">
      <span class="panel-dot" style:background={colorFor(selectedNode.type)}></span>
      <div class="panel-titlewrap">
        <div class="panel-eyebrow">{(selectedNode.type ?? "other").toUpperCase()}</div>
        <div class="panel-title">{selectedNode.title}</div>
      </div>
      <button class="panel-close" onclick={onClose} aria-label="close">×</button>
    </div>

    <div class="panel-body" onclick={handleBodyClick}>
      {#if loading}
        <p class="panel-loading">loading…</p>
      {:else if error}
        <p class="panel-error">{error}</p>
      {:else}
        {@html renderMarkdown(body, titleMap)}
      {/if}
    </div>

    <div class="panel-foot">
      <div>
        <h5>BACKLINKS</h5>
        <ul class="link-list">
          {#each backlinks.slice(0, 10) as nb}
            <li onclick={() => onSelect(nb.id)}>
              <span class="swatch" style:background={colorFor(nb.type)}></span>
              <span>{nb.title}</span>
            </li>
          {/each}
          {#if backlinks.length === 0}
            <li class="empty">— none</li>
          {/if}
        </ul>
      </div>
      <div>
        <h5>OUTGOING</h5>
        <ul class="link-list">
          {#each outgoing.slice(0, 10) as nb}
            <li onclick={() => onSelect(nb.id)}>
              <span class="swatch" style:background={colorFor(nb.type)}></span>
              <span>{nb.title}</span>
            </li>
          {/each}
          {#if outgoing.length === 0}
            <li class="empty">— none</li>
          {/if}
        </ul>
      </div>
    </div>
  </aside>
{/if}

<style>
  /* Lift styling from prototype lines 121–212 with these substitutions:
     --paper → var(--bg)
     --ink   → var(--fg)
     --bg    → var(--surface) (private alias) for panel-close hover background
     --coral → var(--accent) for hover emphasis
     keep dashed dividers, hard 4px shadow, uppercase letterspaced labels */
  .panel {
    position: absolute;
    top: 20px;
    right: 20px;
    width: 440px;
    max-height: calc(100% - 40px);
    background: var(--bg);
    border: var(--border-heavy);
    box-shadow: 4px 4px 0 var(--fg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 6;
  }
  .panel-head {
    padding: 14px 16px;
    border-bottom: 1.5px dashed var(--fg);
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .panel-dot {
    width: 12px;
    height: 12px;
    border: 1.5px solid var(--fg);
    margin-top: 4px;
    flex-shrink: 0;
  }
  .panel-titlewrap { flex: 1; min-width: 0; }
  .panel-eyebrow {
    font-size: 9px;
    letter-spacing: 0.14em;
    color: var(--muted);
    margin-bottom: 3px;
  }
  .panel-title { font-size: 14px; font-weight: 500; word-break: break-word; }
  .panel-close {
    background: var(--surface);
    border: 1.5px solid var(--fg);
    width: 22px; height: 22px;
    cursor: pointer; padding: 0;
    font-family: var(--font-mono); font-size: 12px; line-height: 1;
  }
  .panel-close:hover { background: var(--fg); color: var(--bg); }
  .panel-body {
    padding: 14px 18px 18px;
    overflow-y: auto;
    font-size: 12.5px;
    line-height: 1.55;
    font-family: var(--font-mono);
  }
  .panel-body :global(h2) {
    font-size: 11px; letter-spacing: 0.16em; font-weight: 700;
    margin: 16px 0 8px; text-transform: uppercase;
    border-top: 1px dashed var(--fg); padding-top: 10px;
  }
  .panel-body :global(h2:first-child) { border-top: none; padding-top: 0; margin-top: 0; }
  .panel-body :global(h3) {
    font-size: 11px; letter-spacing: 0.1em; font-weight: 700;
    margin: 12px 0 6px; color: var(--muted);
  }
  .panel-body :global(p) { margin: 0 0 10px; }
  .panel-body :global(ul) { margin: 0 0 10px; padding-left: 18px; }
  .panel-body :global(li) { margin-bottom: 3px; }
  .panel-body :global(code) {
    background: var(--surface);
    padding: 1px 5px;
    font-family: var(--font-mono);
    font-size: 11.5px;
    border: 1px solid rgba(0, 0, 0, 0.15);
  }
  .panel-body :global(strong) { font-weight: 700; }
  .panel-body :global(blockquote) {
    margin: 10px 0; padding: 8px 12px;
    border-left: 3px solid var(--fg);
    background: var(--surface);
  }
  .panel-body :global(a.wl) {
    color: var(--fg);
    text-decoration: underline;
    text-decoration-color: var(--accent);
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .panel-body :global(a.wl:hover) { background: var(--yellow); }
  .panel-body :global(a.wl.dead) {
    color: var(--muted);
    text-decoration-style: dotted;
    text-decoration-color: var(--muted);
    cursor: default;
  }
  .panel-body :global(.tag) {
    display: inline-block;
    font-size: 10px;
    padding: 1px 6px;
    border: 1px solid var(--fg);
    background: var(--bg);
    margin-right: 4px;
  }
  .panel-loading, .panel-error {
    color: var(--muted);
    font-style: italic;
  }
  .panel-error { color: var(--st-err); }
  .panel-foot {
    border-top: 1.5px dashed var(--fg);
    padding: 12px 16px;
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
    font-size: 11px;
  }
  .panel-foot h5 {
    margin: 0 0 6px;
    font-size: 9px; letter-spacing: 0.14em; color: var(--muted); font-weight: 700;
  }
  .link-list { list-style: none; padding: 0; margin: 0; }
  .link-list li {
    padding: 3px 0; cursor: pointer;
    display: flex; align-items: center; gap: 7px;
    font-size: 11px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .link-list li:hover { color: var(--accent); }
  .link-list .swatch { width: 8px; height: 8px; border: 1.2px solid var(--fg); flex-shrink: 0; }
  .link-list .empty { color: var(--muted); font-size: 10px; cursor: default; }
</style>
```

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/NotePanel.svelte
git commit -m "$(cat <<'EOF'
feat(notes): NotePanel side component

Right-hand panel that fetches /api/knowledge/notes/{id} on selection,
renders markdown with resolved wikilinks, and shows backlinks +
outgoing computed locally from the graph payload.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: `GraphLegend.svelte`

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/GraphLegend.svelte`

```svelte
<script>
  import { colorFor } from "./clusters.js";

  let { nodes, activeClusters, onToggle } = $props();

  // Derive type → count from current node set.
  let counts = $derived(
    nodes.reduce((acc, n) => {
      const k = n.type ?? "other";
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    }, {}),
  );
  let entries = $derived(
    Object.entries(counts).sort((a, b) => b[1] - a[1]),
  );
</script>

<div class="legend">
  <h4>VAULT</h4>
  {#each entries as [type, count]}
    <div
      class="legend-row"
      class:off={!activeClusters.has(type)}
      onclick={() => onToggle(type)}
      role="button"
      tabindex="0"
    >
      <span class="left">
        <span class="swatch" style:background={colorFor(type)}></span>
        <span class="name">{type}</span>
      </span>
      <span class="count">{count}</span>
    </div>
  {/each}
</div>

<style>
  .legend {
    position: absolute;
    left: 20px; bottom: 20px;
    background: var(--bg);
    border: var(--border-heavy);
    box-shadow: 4px 4px 0 var(--fg);
    padding: 12px 14px;
    min-width: 200px;
    z-index: 5;
    font-family: var(--font-mono);
  }
  h4 {
    margin: 0 0 8px;
    font-size: 9px; letter-spacing: 0.14em; font-weight: 700;
  }
  .legend-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 14px; font-size: 11px; padding: 3px 0;
    cursor: pointer; user-select: none;
  }
  .legend-row:hover { color: var(--accent); }
  .legend-row.off { opacity: 0.35; text-decoration: line-through; }
  .legend-row .swatch { width: 12px; height: 12px; border: 1.5px solid var(--fg); flex-shrink: 0; }
  .legend-row .name { flex: 1; }
  .legend-row .count { font-size: 10px; color: var(--muted); }
  .legend-row .left { display: flex; align-items: center; gap: 8px; }
</style>
```

Commit:

```bash
git add projects/monolith/frontend/src/lib/components/notes/GraphLegend.svelte
git commit -m "$(cat <<'EOF'
feat(notes): GraphLegend cluster filter

Bottom-left card listing every Note.type in the current payload with
its node count. Click toggles whether that cluster's nodes/edges are
visible on the canvas.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: `GraphSearch.svelte`

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/GraphSearch.svelte`

```svelte
<script>
  import { onMount, onDestroy } from "svelte";

  let { value = "", onChange } = $props();
  let inputRef;

  onMount(() => {
    function onKey(e) {
      if (e.key === "/" && document.activeElement !== inputRef) {
        e.preventDefault();
        inputRef?.focus();
        inputRef?.select();
      } else if (e.key === "Escape" && document.activeElement === inputRef) {
        inputRef.blur();
        onChange("");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
</script>

<div class="search">
  <label for="graph-search-input">SEARCH NOTES</label>
  <input
    id="graph-search-input"
    type="text"
    bind:this={inputRef}
    {value}
    oninput={(e) => onChange(e.target.value)}
    placeholder="filename or substring…"
    autocomplete="off"
    spellcheck="false"
  />
  <div class="search-hint">
    <kbd>/</kbd> focus &nbsp; <kbd>esc</kbd> clear
  </div>
</div>

<style>
  .search {
    position: absolute; top: 20px; left: 20px;
    background: var(--bg);
    border: var(--border-heavy);
    box-shadow: 4px 4px 0 var(--fg);
    padding: 10px 12px; width: 280px; z-index: 5;
    font-family: var(--font-mono);
  }
  label {
    display: block; font-size: 9px; letter-spacing: 0.12em;
    margin-bottom: 6px; color: var(--muted);
  }
  input {
    width: 100%; border: none; outline: none; background: transparent;
    font-family: inherit; font-size: 14px; color: var(--fg);
    padding: 0; caret-color: var(--accent);
  }
  input::placeholder { color: rgba(0, 0, 0, 0.32); }
  .search-hint {
    margin-top: 6px; font-size: 9px; letter-spacing: 0.1em; color: var(--muted);
  }
  kbd {
    font-family: inherit; font-size: 9px;
    border: 1px solid var(--fg); padding: 1px 5px; background: var(--surface);
  }
</style>
```

Commit:

```bash
git add projects/monolith/frontend/src/lib/components/notes/GraphSearch.svelte
git commit -m "$(cat <<'EOF'
feat(notes): GraphSearch filter input

Top-left card with a substring search input. `/` focuses, `esc` clears.
Filtering is purely local — the cached graph payload stays one URL so
keystrokes don't re-hit the server.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: `StatusBar.svelte`

**Files:**

- Create: `projects/monolith/frontend/src/lib/components/notes/StatusBar.svelte`

```svelte
<script>
  let {
    nodeCount,
    edgeCount,
    clusterCount,
    zoom = 1,
    hoverTitle = "—",
    indexedAt = null,
  } = $props();

  function formatAgo(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    const m = Math.floor(ms / 60_000);
    if (m < 1) return "JUST NOW";
    if (m < 60) return `${m}M AGO`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}H AGO`;
    return `${Math.floor(h / 24)}D AGO`;
  }
</script>

<div class="statusbar">
  <div class="statusbar-track">
    <span class="stat">~/KG</span>
    <span class="stat"><strong>{nodeCount}</strong> NOTES</span>
    <span class="stat"><strong>{edgeCount}</strong> LINKS</span>
    <span class="stat"><strong>{clusterCount}</strong> CLUSTERS</span>
    <span class="stat">ZOOM <strong>{zoom.toFixed(2)}</strong>×</span>
    <span class="stat">HOVER <strong>{hoverTitle}</strong></span>
    <span class="stat">LAST INDEX <strong>{formatAgo(indexedAt)}</strong></span>
  </div>
</div>

<style>
  .statusbar {
    position: relative;
    height: 32px;
    background: var(--bg);
    border-bottom: var(--border-heavy);
    overflow: hidden;
    z-index: 4;
    font-family: var(--font-mono);
  }
  .statusbar-track {
    display: flex; align-items: center; height: 100%;
    white-space: nowrap; padding: 0 var(--space-md); gap: 32px;
    font-size: 11px; letter-spacing: 0.06em;
  }
  .stat { display: inline-flex; align-items: center; gap: 10px; }
  .stat::before {
    content: ""; width: 5px; height: 5px;
    background: var(--fg); border-radius: 50%;
    display: inline-block; margin-right: 4px;
  }
  strong { font-weight: 700; }
</style>
```

Commit:

```bash
git add projects/monolith/frontend/src/lib/components/notes/StatusBar.svelte
git commit -m "$(cat <<'EOF'
feat(notes): StatusBar component

Top stat strip showing node/link/cluster counts, zoom level, hovered
note title, and "LAST INDEX Nm AGO" derived from the indexed_at field
in the graph payload. White bar with black underline — matches the
unified design language.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Page composition

### Task 18: `+page.server.js` for `/notes`

**Files:**

- Create: `projects/monolith/frontend/src/routes/private/notes/+page.server.js`
- Create: `projects/monolith/frontend/src/routes/private/notes/+page.server.test.js`

**Step 1: Write the failing test**

```js
// +page.server.test.js
import { describe, it, expect, vi } from "vitest";
import { load } from "./+page.server.js";

describe("/notes load", () => {
  it("fetches the graph and sets the cache-control header", async () => {
    const setHeaders = vi.fn();
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [], indexed_at: null }),
    });

    const result = await load({ fetch, setHeaders });

    expect(setHeaders).toHaveBeenCalledWith(
      expect.objectContaining({
        "cache-control": expect.stringContaining("s-maxage="),
      }),
    );
    expect(result.graph).toEqual({ nodes: [], edges: [], indexed_at: null });
  });

  it("throws a 503 when the backend fetch fails", async () => {
    const setHeaders = vi.fn();
    const fetch = vi.fn().mockResolvedValue({ ok: false, status: 502 });

    await expect(load({ fetch, setHeaders })).rejects.toThrow();
  });
});
```

**Step 2: Write the loader**

```js
// +page.server.js
import { error } from "@sveltejs/kit";
import { PAGE_CACHE_CONTROL } from "$lib/cache-headers.js";

const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch, setHeaders }) {
  setHeaders({ "cache-control": PAGE_CACHE_CONTROL });
  const res = await fetch(`${API_BASE}/api/knowledge/graph`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw error(503, "graph unavailable");
  }
  return { graph: await res.json() };
}
```

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/routes/private/notes/+page.server.js \
        projects/monolith/frontend/src/routes/private/notes/+page.server.test.js
git commit -m "$(cat <<'EOF'
feat(notes): SSR loader for /notes route

Fetches GET /api/knowledge/graph server-side and sets the shared CDN
cache-control header (s-maxage=60, SWR=24h, SIE=1y). 503s through to
SvelteKit's error page when the backend is unreachable; CDN's
stale-if-error covers most outages anyway.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: `+page.svelte` composing the notes view

**Files:**

- Create: `projects/monolith/frontend/src/routes/private/notes/+page.svelte`

```svelte
<script>
  import KnowledgeGraph from "$lib/components/notes/KnowledgeGraph.svelte";
  import NotePanel from "$lib/components/notes/NotePanel.svelte";
  import GraphLegend from "$lib/components/notes/GraphLegend.svelte";
  import GraphSearch from "$lib/components/notes/GraphSearch.svelte";
  import StatusBar from "$lib/components/notes/StatusBar.svelte";

  let { data } = $props();
  let { nodes, edges, indexed_at } = $derived(data.graph);

  // Compute degree once per graph payload.
  let nodesWithDegree = $derived.by(() => {
    const deg = new Map(nodes.map((n) => [n.id, 0]));
    for (const e of edges) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    return nodes.map((n) => ({ ...n, degree: deg.get(n.id) ?? 0 }));
  });

  let activeClusters = $state(
    new Set(nodes.map((n) => n.type ?? "other")),
  );
  let searchTerm = $state("");
  let selectedId = $state(null);
  let zoom = $state(1);
  let hoverTitle = $state("—");

  let clusterCount = $derived(activeClusters.size);

  function toggleCluster(type) {
    const next = new Set(activeClusters);
    next.has(type) ? next.delete(type) : next.add(type);
    activeClusters = next;
  }

  function selectNode(id) {
    selectedId = id;
  }
</script>

<div class="notes-root">
  <StatusBar
    nodeCount={nodes.length}
    edgeCount={edges.length}
    {clusterCount}
    {zoom}
    {hoverTitle}
    indexedAt={indexed_at}
  />

  <div class="notes-stage">
    <KnowledgeGraph
      nodes={nodesWithDegree}
      {edges}
      {selectedId}
      {searchTerm}
      {activeClusters}
      on:nodeClick={(e) => selectNode(e.detail.id)}
      on:nodeHover={(e) => (hoverTitle = e.detail.title ?? "—")}
      on:zoom={(e) => (zoom = e.detail)}
    />

    <GraphSearch value={searchTerm} onChange={(v) => (searchTerm = v)} />
    <GraphLegend
      nodes={nodesWithDegree}
      {activeClusters}
      onToggle={toggleCluster}
    />
    <NotePanel
      {selectedId}
      nodes={nodesWithDegree}
      {edges}
      onSelect={selectNode}
      onClose={() => (selectedId = null)}
    />
  </div>
</div>

<style>
  .notes-root {
    height: calc(100vh - 48px); /* minus shared Nav height */
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--fg);
  }
  .notes-stage {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
```

> The `48px` reserved for the nav assumes the Nav component has a deterministic height. If you bumped the nav's vertical padding, adjust this number to match.

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/routes/private/notes/+page.svelte
git commit -m "$(cat <<'EOF'
feat(notes): compose /notes page

Wires KnowledgeGraph, NotePanel, GraphLegend, GraphSearch, and
StatusBar into the SvelteKit /notes route. Degree is computed once
per graph payload; cluster filter and search are local-only state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 7 — Push, watch CI, iterate

### Task 20: Open PR and watch CI

**Step 1: Push the branch**

```bash
cd /tmp/claude-worktrees/notes-page
git push -u origin feat/notes-page
```

**Step 2: Open the PR**

```bash
gh pr create \
  --title "feat: notes page at private.jomcgi.dev/notes" \
  --body "$(cat <<'EOF'
## Summary

- Adds `GET /api/knowledge/graph` endpoint to `monolith/knowledge` returning the full KG in one CDN-cached payload.
- Adds `/notes` route to the private SvelteKit frontend: force-directed graph view backed by the new endpoint, click-to-open side panel that fetches individual notes directly.
- Promotes `projects/websites/shared/` to the canonical token + nav source for both Astro public and SvelteKit private stacks.
- Drops dark mode entirely from both stacks; public homepage's rack aesthetic is the unified gold standard.

## Test plan

- [ ] CI passes `monolith/knowledge` Python tests (new `get_graph` + endpoint cases).
- [ ] CI passes frontend `vitest` tests (clusters, markdown renderer, page loader).
- [ ] Visit `https://private.jomcgi.dev/notes` after deploy: graph renders, click opens panel, wikilinks resolve.
- [ ] Visit `https://public.jomcgi.dev/`: nav appears, INVERT button gone, no dark-mode flash.
- [ ] `curl -I https://private.jomcgi.dev/api/knowledge/graph | grep cache-control` shows `s-maxage=60, stale-while-revalidate=86400, stale-if-error=31536000`.

Design doc: `docs/plans/2026-04-26-notes-page-design.md`
Implementation plan: `docs/plans/2026-04-26-notes-page-plan.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Watch the CI run**

```bash
gh pr checks "$(gh pr view --json number -q .number)" --watch
```

**Step 4: If CI fails, diagnose with the BuildBuddy MCP tools (per CLAUDE.md)**

Use `mcp__buildbuddy__get_invocation` (selector `commitSha`) → `get_target` → `get_log`. **Quote the actual error before hypothesising** — never invoke "flaky CI" until you've ruled out a real failure.

For each fix:

1. Cherry-pick the failure to a new task at the bottom of this plan.
2. Implement.
3. Commit (`fix(...): …` per Conventional Commits).
4. Push.
5. Re-watch.

Common gotchas to watch for:

- **Bazel sandbox can't find `projects/websites/shared/tokens.css`** — `:css` target visibility didn't open to `//projects/monolith/frontend`. Re-check Task 9.
- **`d3-force` not in `pnpm-lock.yaml`** — `pnpm install` didn't run before the commit, or `pnpm-lock.yaml` wasn't staged.
- **Conventional Commits hook rejects the PR title** — the _PR title_ is checked at merge by the rebase merge step; pick a `feat:`-prefixed title (this plan's example does).

---

## What this plan does NOT cover

- Re-skinning the existing `/private` capture/schedule/todos page in the rack aesthetic. Out of scope; separate follow-up.
- Adding the nav to public-side pages other than `index.astro` (`cv.astro`, `engineering.astro`, etc.). Add per page if/when desired.
- Auth on `private.jomcgi.dev`. Tracked separately.
- Server-side filtering or pagination on the graph endpoint. Only revisit if vault size pushes the gzipped payload above ~250 KB.
- E2E tests for click-through interactions. The existing `monolith/frontend/e2e/` harness can grow a "click a node, verify panel opens" test once the manual QA in the PR shakes out any issues.
