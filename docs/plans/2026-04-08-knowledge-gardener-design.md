# Knowledge Gardener Design

## Goal

Build a scheduled gardener process that decomposes raw Obsidian vault notes into typed knowledge artifacts (atoms, facts, active items) using Claude Sonnet, then moves originals to a soft-delete folder with a 24-hour TTL.

## Context

The knowledge reconciler (`knowledge.reconcile`) already indexes files in `_processed/` — parsing frontmatter, chunking, embedding, and upserting to Postgres. Nothing currently populates `_processed/` with properly typed notes. Raw notes arrive in the vault root via Obsidian sync (web shares, the insert endpoint, manual entry) as unstructured markdown.

The gardener sits between raw input and the reconciler:

```
Raw vault files
     │
     ▼
 ┌──────────┐    Sonnet API     ┌────────────┐
 │  INGEST   │ ───────────────▶ │ _processed/ │
 │           │   decompose      │  atoms/     │
 │  raw .md  │   into typed     │  facts/     │
 │  files    │   notes          │  active/    │
 └──────────┘                   └────────────┘
     │
     ▼
 _deleted_with_ttl/
 (soft delete, 24h TTL)

     ... then on next cycle ...

 ┌────────────┐
 │ RECONCILER  │ ──▶ embed + upsert to Postgres
 │ (existing)  │
 └────────────┘
```

## Architecture

### Scheduled Job

Register `knowledge.garden` as a scheduler job alongside `knowledge.reconcile`, same 5-minute cadence. The garden job runs first (registered with lower priority / earlier in the cycle) so its output is available when the reconciler runs.

### Ingest Phase

The gardener walks the vault root for `.md` files that are NOT in `_processed/` or `_deleted_with_ttl/`. For each raw file:

1. Read the file and parse any existing frontmatter.
2. Call Claude Sonnet via the Anthropic SDK using a tool-use message loop.
3. Sonnet has access to tools that let it query the knowledge store and write output:
   - `search_notes(query)` — semantic search against the embedding index to find related existing notes
   - `get_note(note_id)` — read full content of a specific indexed note
   - `create_note(type, title, tags, edges, body)` — write a new `.md` file to `_processed/` with full frontmatter schema
   - `patch_edges(note_id, edges)` — add edges to an existing note's frontmatter (for linking new notes back to existing ones)
4. Tool calls execute eagerly during the loop (side effects on disk). Partial state from crashes is fine — the reconciler is idempotent.
5. After Sonnet finishes, move the raw input to `_deleted_with_ttl/` with `ttl: <ISO timestamp +24h>` in frontmatter.

### Note Types

| Type     | Purpose                        | Example                                          |
| -------- | ------------------------------ | ------------------------------------------------ |
| `atom`   | Distilled concept or principle | "Kubernetes uses CNI plugins for pod networking" |
| `fact`   | Specific verifiable claim      | "Calico supports 500 nodes per cluster"          |
| `active` | Temporal / actionable item     | Journal entry, TODO, reminder                    |

Sonnet determines the type based on content. A single raw input may produce multiple notes of mixed types.

### LLM Configuration

- **Model:** Claude Sonnet (via Anthropic SDK, `anthropic` Python package)
- **API key:** `ANTHROPIC_API_KEY` env var, injected from a 1Password secret
- **Tool use:** Structured tool definitions for `search_notes`, `get_note`, `create_note`, `patch_edges`
- **Prompt:** Context-aware — includes the raw note content and instructions for decomposition into the type taxonomy

### TTL Cleanup Phase

Runs at the end of each garden cycle, no LLM needed:

1. Walk `_deleted_with_ttl/` for `.md` files.
2. Parse `ttl:` from frontmatter.
3. Delete files where `ttl` has passed.

### Soft Delete

Raw inputs are moved (not copied) to `_deleted_with_ttl/<original-relative-path>`. The frontmatter is augmented with:

```yaml
---
ttl: "2026-04-09T12:00:00Z"
original_path: "inbox/my-note.md"
---
```

This provides a 24-hour recovery window. The TTL cleanup phase purges expired files.

## New Files

- `knowledge/gardener.py` — core gardener logic, Anthropic SDK tool loop, TTL cleanup
- `knowledge/gardener_test.py` — tests with mocked Sonnet responses

## Modified Files

- `knowledge/service.py` — register `knowledge.garden` job
- `chart/templates/deployment.yaml` — add `ANTHROPIC_API_KEY` env var
- `deploy/values.yaml` or 1Password secret — API key storage

## New Dependencies

- `anthropic` Python SDK

## Deferred

- **Refine phase** — embedding cluster analysis to flag missing links and consolidation opportunities. Will be added once the knowledge base has enough content for clustering to be useful.

## Edge Types

Reuses the existing edge taxonomy from `frontmatter.py`:

- `refines`, `generalizes`, `related`, `contradicts`, `derives_from`, `supersedes`

The `derives_from` edge is particularly relevant — decomposed notes naturally derive from their source raw note.
