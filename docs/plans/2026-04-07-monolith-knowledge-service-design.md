# Monolith Knowledge Service — Design

**Status:** approved, ready for implementation plan
**Date:** 2026-04-07
**Owner:** jomcgi

## Goal

Ingest the Obsidian vault's `_processed/` folder into a new pgvector-backed
schema in the monolith Postgres cluster, with frontmatter promoted to filterable
columns so we can do hybrid filter-plus-vector searches over notes.

This is the second consumer of the existing voyage-4-nano embedding pipeline
(the first being the Discord chat memory in `chat/`). The PR also lifts the
embedding client and the markdown chunker into shared modules so a third
consumer (e.g. grimoire) can reuse them without copy-paste.

## Non-goals

- Migrating `vault_mcp/`'s Qdrant + fastembed reconciler to the new store. That
  is a follow-up; once it lands, vault_mcp's `search_semantic` MCP tool will
  query `knowledge.chunks` and we'll retire its qdrant + fastembed code paths.
- Building a "lint" reconciler that audits frontmatter quality, dangling
  wikilinks, etc. Frontmatter parse failures are logged as warnings; a future
  audit job will surface them.
- Alerting on reconciler staleness. The scheduler row's `last_run_at` gives us
  the data; the SigNoz alert is a follow-up.
- Extracting `shared/chunker.py` and `shared/embedding.py` to a cross-project
  Python lib (e.g. under `bazel/python/lib/`). Their APIs are designed to be
  generic so the move is one line when a second project needs them.

## Topology

The knowledge service is **not a new pod**. It's a logical module inside the
existing monolith backend FastAPI process, scheduled by the existing
`scheduler.scheduled_jobs` table.

```
┌─────────────────────────────────────────────────────────┐
│ monolith pod                                            │
│                                                         │
│  ┌────────────────┐  reads /vault   ┌────────────────┐  │
│  │ obsidian       │ ───────────────▶│ backend        │  │
│  │ (sidecar,      │  emptyDir       │ (FastAPI)      │  │
│  │ ob sync)       │                 │                │  │
│  └────────────────┘                 │ - notes/       │  │
│                                     │ - chat/        │  │
│                                     │ - knowledge/ ◀─┼──┤
│                                     │   reconciler   │  │
│                                     └───────┬────────┘  │
│                                             │           │
│                                             ▼           │
│                                     ┌────────────────┐  │
│                                     │ CNPG postgres  │  │
│                                     │ + pgvector     │  │
│                                     └────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

Why no new container:

- The vault is already mounted read-only at `/vault` in the backend
  (`projects/monolith/chart/templates/deployment.yaml:91-95`). Adding a new pod
  would mean re-mounting the vault, more cron, more failure surface.
- The existing scheduler infra (`scheduler.scheduled_jobs`, migration
  `20260407000000_scheduled_jobs.sql`) already gives us distributed locking
  via `SELECT … FOR UPDATE SKIP LOCKED`, `last_run_at` heartbeats, and
  `last_status` observability — for free.

The reconciler walks `/vault/_processed/**/*.md`. Anything outside `_processed`
is invisible to it. The folder doesn't exist yet — that's fine, the reconciler
treats an empty directory as a no-op cycle.

## Schema

New migration: `projects/monolith/chart/migrations/<ts>_knowledge_schema.sql`.

```sql
-- Vector dim 1024 = voyage-4-nano (matches chat.messages.embedding).
-- pgvector extension is already created cluster-wide via cnpg-cluster.yaml.

CREATE SCHEMA IF NOT EXISTS knowledge;

-- One row per .md file under /vault/_processed.
CREATE TABLE knowledge.notes (
    id            BIGSERIAL PRIMARY KEY,
    note_id       TEXT NOT NULL UNIQUE,        -- stable graph identity from frontmatter `id:` (auto-backfilled if missing)
    path          TEXT NOT NULL UNIQUE,        -- current file location, relative to /vault
    title         TEXT NOT NULL,               -- frontmatter.title or filename stem
    content_hash  TEXT NOT NULL,               -- sha256 of full file bytes (drives reconciliation)

    -- Promoted frontmatter columns.
    type          TEXT,                        -- e.g. note | daily | project | paper | fleeting
    status        TEXT,                        -- e.g. draft | active | archived | published
    source        TEXT,                        -- e.g. web-ui | discord | manual | clipper
    tags          TEXT[]      NOT NULL DEFAULT '{}',
    aliases       TEXT[]      NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ,                 -- frontmatter.created or NULL
    updated_at    TIMESTAMPTZ,                 -- frontmatter.updated or NULL
    extra         JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- everything else from frontmatter

    -- Bookkeeping.
    indexed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX notes_note_id     ON knowledge.notes (note_id);
CREATE INDEX notes_tags_gin    ON knowledge.notes USING gin (tags);
CREATE INDEX notes_aliases_gin ON knowledge.notes USING gin (aliases);
CREATE INDEX notes_extra_gin   ON knowledge.notes USING gin (extra);
CREATE INDEX notes_type        ON knowledge.notes (type);
CREATE INDEX notes_status      ON knowledge.notes (status);
CREATE INDEX notes_source      ON knowledge.notes (source);
CREATE INDEX notes_updated_at  ON knowledge.notes (updated_at DESC);

-- One row per chunk. Re-chunked + re-embedded whenever the parent's content_hash changes.
CREATE TABLE knowledge.chunks (
    id              BIGSERIAL PRIMARY KEY,
    note_id         BIGINT      NOT NULL REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    chunk_index     INTEGER     NOT NULL,
    section_header  TEXT        NOT NULL DEFAULT '',
    chunk_text      TEXT        NOT NULL,
    embedding       vector(1024) NOT NULL,
    UNIQUE (note_id, chunk_index)
);

CREATE INDEX chunks_embedding_hnsw ON knowledge.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_note_id        ON knowledge.chunks (note_id);

-- Edge table for graph queries. Targets are stable note ids (strings), not FKs,
-- because edges may dangle (point at non-existent or not-yet-ingested notes).
--
-- Two-level taxonomy:
--   kind='edge' → declared semantic relationship from frontmatter `edges:` block;
--                 edge_type names the relationship.
--   kind='link' → untyped body wikilink ([[Foo]]); edge_type is NULL.
--
-- Adding a new edge_type is a code change, not a schema migration.
CREATE TABLE knowledge.note_links (
    id            BIGSERIAL PRIMARY KEY,
    src_note_id   BIGINT NOT NULL REFERENCES knowledge.notes(id) ON DELETE CASCADE,
    target_id     TEXT   NOT NULL,             -- target note_id or raw wikilink target
    target_title  TEXT,                        -- display text from [[Foo|display]] when present
    kind          TEXT   NOT NULL CHECK (kind IN ('edge', 'link')),
    edge_type     TEXT   CHECK (
                    (kind = 'edge' AND edge_type IN (
                      'refines', 'generalizes', 'related',
                      'contradicts', 'derives_from', 'supersedes'
                    )) OR
                    (kind = 'link' AND edge_type IS NULL)
                  ),
    UNIQUE (src_note_id, target_id, kind, edge_type)
);

CREATE INDEX note_links_target    ON knowledge.note_links (target_id);
CREATE INDEX note_links_kind      ON knowledge.note_links (kind);
CREATE INDEX note_links_edge_type ON knowledge.note_links (edge_type) WHERE edge_type IS NOT NULL;

-- Register the reconcile job in the existing scheduler.
INSERT INTO scheduler.scheduled_jobs (name, interval_secs, next_run_at, ttl_secs)
VALUES ('knowledge.reconcile', 300, NOW(), 600)
ON CONFLICT (name) DO NOTHING;
```

### Schema rationale

- **`note_id` is the stable graph identity, `path` is mutable display.** Edges
  reference `note_id`, so file moves and renames don't break the graph. The
  frontmatter `id:` field is the authoritative source; if a file arrives
  without one, the reconciler auto-backfills (see "ID assignment" below).
- `BIGSERIAL id` gives `chunks` and `note_links` cheap stable joins on the
  hot path; user-facing identity is `note_id`.
- `content_hash` is the only thing the reconciler diffs against. No mtime, no
  length, no "smart" check. Hash matches → skip; hash differs → delete cascade
  - re-insert.
- `extra JSONB` with a GIN index lets `WHERE extra @> '{"author": "Karpathy"}'`
  filter on un-promoted fields with no schema migration.
- Vector dim 1024 matches `chat.messages.embedding` so we use the same model
  and the same `<=>` cosine operator everywhere. Switching models is a future
  migration that touches both schemas symmetrically.
- `note_links.target_id` is a string, not an FK, because edges dangle
  routinely (target not yet ingested, or pointing at an external concept).
  A future audit reconciler can flag dangling targets.
- **Two-level link taxonomy** (`kind` × `edge_type`) means: `kind='edge'`
  filters to declared semantic relationships, `kind='link'` filters to body
  wikilinks. Adding a new edge type (`refutes`, `cites`, etc.) is a one-line
  CHECK constraint widening, not a table redesign.
- `note_links_edge_type` is a partial index (`WHERE edge_type IS NOT NULL`),
  so it only stores rows where the column is meaningful — saves space and
  speeds up the most common edge-traversal queries.
- All in one migration file: the schema is one logical unit and Atlas applies
  it transactionally.

### ID assignment policy

The frontmatter `id:` field is the canonical stable identity for a note.
Reconciler behavior:

1. **`id:` present** → use it verbatim. Never regenerate. Once set, it's
   permanent.
2. **`id:` missing** → auto-backfill. Generate `slugify(title or filename
stem)`, append a short content-hash suffix on collision. Write the new
   `id:` back to the markdown file's frontmatter, then ingest.
3. **Concurrency**: backfills are gated by a Postgres advisory lock keyed on
   `hashtext(path)` so two replicas can't race on the same file. The
   scheduler's `SELECT … FOR UPDATE SKIP LOCKED` already prevents two
   replicas from running the same job, but advisory locks are belt-and-braces
   against producer/consumer races (gardener writing the file at the same
   moment the reconciler reads it).
4. **Vault mount**: the `/vault` mount must be `readWrite` for backfill to
   work. (As of design time the mount is `readOnly`; the flip is in flight on
   a separate PR.) On `PermissionError` (read-only filesystem), the
   reconciler logs a warning and **skips that file's ingestion this cycle**
   — same lenient policy as broken YAML, never blocks other files.

### Edges contract

The frontmatter `edges:` block is a mapping of edge type → list of target
ids:

```yaml
edges:
  refines: [embedding-model-memory-requirements]
  generalizes: []
  related: [gemma4-vram-footprint, node4-gpu-allocation]
  contradicts: []
  derives_from: [voyage-ai-model-card]
  supersedes: []
```

Each non-empty list produces N rows in `note_links` with `kind='edge'` and
`edge_type=<key>`. Empty lists are skipped silently. Unknown keys (typos,
made-up edge types not in the CHECK constraint) are logged as warnings and
**dropped** — the audit reconciler will surface them later.

The legacy `up:` field is removed in favor of `refines:`. The semantics are:
`up: [[Parent]]` means "parent is broader than me" = "I refine parent" =
`refines: [parent]`. A one-shot vault migration script (out of scope for
this PR) rewrites existing `up:` keys before the reconciler runs against
them in production.

### Example filtered query

```sql
SELECT n.path, c.section_header, c.chunk_text, c.embedding <=> :q AS distance
FROM knowledge.chunks c
JOIN knowledge.notes n ON n.id = c.note_id
WHERE n.tags && ARRAY['ml','attention']
  AND n.type = 'paper'
  AND n.status != 'archived'
ORDER BY c.embedding <=> :q
LIMIT 10;
```

## Component layout

```
projects/monolith/
├── shared/
│   ├── __init__.py
│   ├── chunker.py        ← lifted verbatim from projects/obsidian_vault/vault_mcp/app/chunker.py
│   └── embedding.py      ← lifted verbatim from projects/monolith/chat/embedding.py (with `model` arg parameterized)
├── chat/
│   └── (all callers updated to import from projects.monolith.shared.embedding)
└── knowledge/
    ├── __init__.py
    ├── frontmatter.py    ← parse + strip YAML frontmatter, return (ParsedFrontmatter, body)
    ├── links.py          ← extract [[wikilinks]] from body, dedupe
    ├── models.py         ← SQLModel definitions for notes / chunks / note_links
    ├── store.py          ← pgvector DAL: get_indexed, upsert_note, delete_note, search
    ├── reconciler.py     ← walk /vault/_processed → diff → backfill ids → embed → write
    ├── service.py        ← scheduler hookup; registers handler at lifespan startup
    └── *_test.py
```

### Generic-shared discipline

`shared/chunker.py` and `shared/embedding.py` must remain free of monolith- or
Obsidian-specific assumptions so a third consumer (e.g. grimoire) can reuse
them. Concretely:

- `chunker.py` API is narrowed to `chunk_markdown(content, *, max_tokens,
min_tokens) -> list[Chunk]` where `Chunk = TypedDict({"index": int,
"section_header": str, "text": str})`. Storage concerns (`content_hash`,
  `source_url`, `title`) are dropped — callers attach them.
- `embedding.py` constructor takes `base_url` (already env-driven) and `model`
  (currently hardcoded to `voyage-4-nano` in `chat/embedding.py:59` —
  parameterize with the same default). After this, any caller with an
  OpenAI-compatible `/v1/embeddings` endpoint can use it.

No backwards-compat shims in `chat/embedding.py`. All chat call sites are
updated to the new import path in the same PR (per CLAUDE.md "no
backwards-compatibility hacks").

### Module responsibilities

**`knowledge/frontmatter.py`** — `parse(raw: str) -> tuple[ParsedFrontmatter,
str]`. Detects `---\n…\n---\n` at the very top of the file (Obsidian
convention). Uses `yaml.safe_load`; YAML errors return empty metadata + a
warning, body is the **full original content** so the file still ingests with
no filters. Accepts both YAML lists and comma/space-separated strings for
`tags` / `aliases`. ISO date parsing for `created` / `updated`; failures →
`None` + warning. Promoted keys are popped before assigning the rest to
`extra`, so `extra` never duplicates a column.

**`knowledge/links.py`** — `extract(body: str) -> list[Link]`. Strips fenced
code blocks before regex matching so ` ```[[not_a_link]]``` ` is excluded.
Doesn't try to "resolve" wikilink targets — stores them verbatim.

**`knowledge/store.py`** — SQLModel-backed DAL.

```python
class KnowledgeStore:
    def __init__(self, session: Session): ...
    def get_indexed(self) -> dict[str, str]: ...      # {path: content_hash}
    def upsert_note(self, *, note_id, path, content_hash, title, metadata, chunks, vectors, links, edges) -> None: ...
    def delete_note(self, path: str) -> None: ...
    def search(self, *, query_vector, limit, tags=None, type_=None, status_not=None) -> list[SearchHit]: ...
```

`upsert_note` strategy: DELETE existing row by path (cascade drops chunks +
note_links), INSERT fresh row, INSERT chunks, INSERT note_links — single
transaction. `links` are body wikilinks (`kind='link'`); `edges` is the
typed edge map (`kind='edge'`). This avoids partial-update weirdness when
chunk count changes.

**`knowledge/reconciler.py`** — orchestrates one cycle. See data flow below.

**`knowledge/job.py`** — thin wrapper registered with the scheduler poller.

> **Open question, to be confirmed during plan-writing:** does a generic
> scheduler poller already exist for `scheduler.scheduled_jobs`? The migration
> creating the table is `20260407000000_scheduled_jobs.sql`. If yes, `job.py`
> is a 10-line registration. If no, the implementation plan adds a small
> generic poller (`SELECT … FOR UPDATE SKIP LOCKED`, claim, run, update
> `last_run_at`/`last_status`, release) as part of this work and calls it out
> as a discrete plan step.

## Data flow

### Happy path (one reconcile cycle)

```
scheduler poller picks knowledge.reconcile job (every ~300s)
        │
        ▼
walk /vault/_processed/**/*.md → {path: sha256}
        │
        ▼
SELECT path, content_hash FROM knowledge.notes → {path: sha256}
        │
        ▼
diff → (to_upsert, to_delete)
        │
        ├──▶ for each to_delete: DELETE FROM knowledge.notes WHERE path = $1
        │    (cascades chunks + note_links)
        │
        └──▶ for each to_upsert:
              read file → frontmatter.parse → chunk_markdown → links.extract
                                    │
                                    ▼
              embedder.embed_batch([chunk["text"] for chunk in chunks])
                                    │
                                    ▼
              BEGIN; DELETE old row by path; INSERT note;
                     INSERT chunks (with vectors); INSERT links; COMMIT
        │
        ▼
UPDATE scheduler.scheduled_jobs SET last_run_at=NOW(), last_status='ok',
       next_run_at=NOW()+interval, locked_by=NULL
```

### Transactional invariants

1. **All-or-nothing per note.** Each note's upsert is a single transaction; one
   bad file doesn't roll back the cycle's other progress. Partial cycles are
   always coherent intermediate states.
2. **Delete-before-insert in the same txn,** keyed on `path`. Handles "chunk
   count changed from 12 → 7" with no orphans and no `ON CONFLICT` gymnastics.

### Why all-or-nothing per note (and not per cycle)

Per-note matches how the user thinks about the data ("did _that_ note get
indexed?"). It also makes retries trivial: the next cycle's hash diff naturally
re-attempts whatever didn't make it in. No retry queue, no dead-letter table.

## Frontmatter contract

| Key               | Column / table                   | Index          | Notes                                                                                                                          |
| ----------------- | -------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `id`              | `notes.note_id` (TEXT)           | unique + btree | Stable graph identity; auto-backfilled by reconciler if missing (see "ID assignment")                                          |
| `title`           | `notes.title` (TEXT NOT NULL)    | —              | Defaults to filename stem if missing                                                                                           |
| `created`         | `notes.created_at` (TIMESTAMPTZ) | btree          | ISO date or datetime                                                                                                           |
| `updated`         | `notes.updated_at` (TIMESTAMPTZ) | btree          | ISO date or datetime                                                                                                           |
| `tags`            | `notes.tags` (TEXT[])            | GIN            | Accepts YAML list or comma/space string                                                                                        |
| `aliases`         | `notes.aliases` (TEXT[])         | GIN            | Same                                                                                                                           |
| `type`            | `notes.type` (TEXT)              | btree          | e.g. `note`, `daily`, `project`, `paper`, `fleeting`                                                                           |
| `status`          | `notes.status` (TEXT)            | btree          | e.g. `draft`, `active`, `archived`, `published`                                                                                |
| `source`          | `notes.source` (TEXT)            | btree          | e.g. `web-ui`, `discord`, `manual`, `clipper`                                                                                  |
| `edges`           | `note_links` rows                | btree          | Mapping `{edge_type: [target_id, …]}`; each target → row with `kind='edge'`, `edge_type=<key>`. Unknown keys logged + dropped. |
| (everything else) | `notes.extra` (JSONB)            | GIN            | Filter via `WHERE extra @> '{…}'`                                                                                              |

The legacy `up:` key is gone; see "Edges contract" above for the migration.

### Lenient parse policy

- YAML syntax error → empty metadata, body unchanged, warning logged
- Missing `title` → default to filename stem, warning logged
- Invalid date → `NULL`, warning logged
- Missing required field → no required fields; everything except `path` and
  `title` may be null

A future audit reconciler will scan and report on these warnings.

## Failure modes

| What can break                                 | What we do                                                                                                                                    | Why                                    |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| YAML frontmatter syntax error                  | Log warning, ingest with empty metadata                                                                                                       | Never block ingest on content errors   |
| Missing `title`                                | Default to filename stem, log warning                                                                                                         | Same                                   |
| Invalid date in `created`/`updated`            | `NULL`, log warning                                                                                                                           | Same                                   |
| Embedding endpoint 5xx / timeout               | Existing retry in `embedding.py` (12 retries, 5min budget)                                                                                    | Battle-tested for chat                 |
| Embedding endpoint hard-down past retry budget | Reconciler raises → cycle marked `last_status='error'`; **no partial data persisted** for the failing note; next cycle retries the same notes | Embedding failure is infra not data    |
| File disappears between walk and read          | Caught as `FileNotFoundError`, treated as "delete next cycle"                                                                                 | Race window is microseconds            |
| File read returns invalid UTF-8                | Log warning, skip the file                                                                                                                    | Don't poison the table                 |
| Postgres unavailable                           | Job stays locked until `ttl_secs=600` expires, then re-claimable                                                                              | Same path as every other DB-backed job |
| Two replicas race the same job                 | `SELECT … FOR UPDATE SKIP LOCKED` in scheduler poller                                                                                         | Distributed locking is the whole point |
| `_processed/` doesn't exist                    | Reconciler walks empty set, no-op cycle, `last_status='ok'`                                                                                   | Bootstrap-friendly                     |

## Observability

- One info-level summary per cycle:
  `"reconciled vault: upserted=N deleted=M unchanged=K duration=Xs"`
- Warnings for every per-file content issue, with `path` in the structured log
  for SigNoz grepping
- `scheduler.scheduled_jobs.last_run_at` / `last_status` is the cheap heartbeat
- **Follow-up:** SigNoz alert on `now() - last_run_at > 15min` for
  `name='knowledge.reconcile'`

## Testing

### Pure-function tests

- `shared/chunker_test.py` — port of `vault_mcp/tests/chunker_test.py` +
  additional cases (frontmatter pass-through, empty input, oversized paragraph
  word-split, code blocks containing wikilinks/headings)
- `shared/embedding_test.py` — port of `chat/embedding_*_test.py` (~9 files) +
  one new test asserting the `model` constructor arg is sent in the request
  body
- `knowledge/frontmatter_test.py` — full grid: no FM, well-formed, list+string
  tags, invalid YAML, invalid date, unknown key → `extra`, promoted+`extra`
  collision (column wins), delimiter not at top of file
- `knowledge/links_test.py` — `[[Foo]]`, `[[Foo|Bar]]`, dedupe, order, fenced
  code block exclusion, malformed `[[unterminated`, empty body

### DB-backed tests

Reuse whatever Postgres fixture `chat/store_test.py` and `notes/router_test.py`
already use. To be confirmed during plan-writing — if no fixture exists, the
plan adds a session-scoped one in `conftest.py`.

- `knowledge/store_test.py` — `get_indexed` empty, upsert N chunks then
  re-upsert with M ≠ N chunks (cascade), delete cascade, search with `tags`
  filter ordering
- `knowledge/reconciler_test.py` — uses tmpdir vault + fake `EmbeddingClient`
  returning deterministic vectors. Cases:
  - Empty vault → `(0, 0, 0)`
  - Add one file → `(1, 0, 0)`
  - Re-run no changes → `(0, 0, 1)`, embedder called **zero** times (proves
    hash-diff)
  - Edit body → `(1, 0, 0)`, chunks may differ
  - Edit frontmatter only → `(1, 0, 0)`, columns updated, content_hash updated
  - Delete file → `(0, 1, 0)`, cascade
  - Broken frontmatter → ingested with empty metadata + warning
  - Embedder raises on file 2 of 3 → files 1 and 3 persisted, file 2 not in
    table, exception bubbles to scheduler
  - File appears mid-cycle then disappears before read → no crash

### Out of test scope

- HNSW index quality (pgvector's job)
- voyage-4-nano semantics (model's job)
- Atlas migration application (Atlas's harness)
- Concurrent reconciler races between replicas (scheduler's tests)
- End-to-end with real `EMBEDDING_URL` and real CNPG cluster (out of scope)

## Open questions to resolve during plan-writing

1. **Does a generic poller for `scheduler.scheduled_jobs` already exist?** If
   no, the plan adds one. Either way it's called out as a discrete step.
2. **Which Postgres test fixture does the existing test suite use?** The plan
   reuses it. If none exists, the plan adds a session-scoped one.

## Out of scope (future work)

- Migrate `vault_mcp/`'s reconciler from Qdrant + fastembed to the new
  pgvector store; retire its qdrant + fastembed code paths
- Audit reconciler that reports frontmatter warnings, dangling wikilinks, and
  notes missing `title` / `created`
- SigNoz alert on stale `last_run_at` for `knowledge.reconcile`
- Lift `shared/chunker.py` and `shared/embedding.py` to a cross-project Python
  lib once a non-monolith consumer materialises
