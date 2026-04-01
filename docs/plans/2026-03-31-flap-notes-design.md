# FLAP Notes Capture — Design

## Problem

The monolith dashboard has a capture textarea (left pane) that is currently a no-op. We want to wire it up so that brain-dumped text is saved as a `#fleeting` note in the Obsidian vault, ready for daily review via the Spaced Repetition plugin.

## Design

### Note Format

Every captured note is saved as a markdown file with YAML frontmatter:

```markdown
---
up:
tags: fleeting
source: web-ui
---

Raw text from the capture box
```

- **`up:`** — Empty initially; filled during review when the note is promoted to `#atomic` and slotted into a hierarchy
- **`tags: fleeting`** — Picked up by the Obsidian Spaced Repetition plugin for daily triage
- **`source: web-ui`** — Provenance tracking (other sources: `mcp`, `api`)

### Filename

Timestamp-based: `Fleeting/<YYYY-MM-DD> <HHMM>.md`

Descriptive filenames are a FLAP principle for `#atomic` notes, not `#fleeting` — at capture time, speed matters more than naming.

### Architecture

```
Browser (SvelteKit +page.svelte)
  │
  │  POST /api/notes  { content: "..." }
  │
  ▼
Monolith FastAPI (notes/router.py → notes/service.py)
  │
  │  POST /api/notes  { content: "...", source: "web-ui" }
  │
  ▼
Vault-MCP (Starlette /api/notes endpoint)
  │
  │  Generates filename, wraps frontmatter, calls write_note()
  │  Git commit via existing lock/sidecar coordination
  │
  ▼
Obsidian Vault (git-backed PVC)
  └── Fleeting/2026-03-31 1423.md
```

### Component Changes

#### 1. Vault-MCP: `POST /api/notes` endpoint

Add a REST endpoint to `projects/obsidian_vault/vault_mcp/app/main.py`:

- **Input:** `{ content: string, source?: string }` (source defaults to `"api"`)
- **Behaviour:**
  1. Generate filename: `Fleeting/<YYYY-MM-DD> <HHMM>.md` (UTC)
  2. Build frontmatter + content body
  3. Call existing `write_note(path, full_content, reason="fleeting note from <source>")`
  4. Return `201 { path: "Fleeting/..." }`
- **Errors:** Empty content → 400; write failure → 500

#### 2. Monolith: `notes/` module

New module following the existing router/service pattern:

- **`notes/router.py`** — `APIRouter(prefix="/api/notes")`, single `POST /` endpoint
- **`notes/service.py`** — Calls vault-mcp `POST /api/notes` over HTTP
- **`main.py`** — `app.include_router(notes_router)`

The monolith acts as a thin proxy — it doesn't generate filenames or frontmatter. That logic lives in vault-mcp so all note sources (web-ui, MCP, future API clients) get consistent formatting.

#### 3. Frontend: `+page.svelte`

Wire `submitCapture()` to:

```js
const res = await fetch("/api/notes", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ content: note }),
});
```

On success: existing "sent" animation plays, textarea clears.
On failure: hint text shows "failed" briefly, auto-clears for retry.

#### 4. Infrastructure

- **Monolith values.yaml:** Add `VAULT_API_URL` env var pointing to `http://obsidian-vault.obsidian.svc.cluster.local:8000`
- **Monolith chart version bump** + `application.yaml` targetRevision update
- **Vault-MCP chart version bump** + `application.yaml` targetRevision update

No new secrets, PVCs, services, or ingress rules needed.

## Scope

**In scope:**

- `POST /api/notes` on vault-mcp (REST endpoint)
- `POST /api/notes` on monolith (proxy to vault-mcp)
- Wire `submitCapture()` in `+page.svelte`
- Chart version bumps + infra wiring

**Out of scope:**

- Review UI (done in Obsidian via SR plugin)
- Listing/searching notes from the dashboard
- Note editing from the dashboard
- The `projects/notes/` React prototype (superseded by monolith SvelteKit)
