# Gap Classifier + Stub Notes — Design

## Context

PR #2193 shipped the gap data model: a `knowledge.gaps` table, discovery logic,
and a Claude-free no-op classifier that leaves gaps at `state='discovered'`.
The gardener's first cycle produced **1793 discovered gaps** awaiting
classification.

This design wires in the real Claude-backed classifier, and in doing so
corrects an architectural mismatch: the Gap table is currently a parallel
state store to the vault. Every other knowledge artifact (notes, links,
atoms, tasks) lives in the vault first, DB second — the reconciler keeps
them in sync. Gaps should be homogeneous.

## Outcome

Unresolved wikilinks materialise as barebones stub notes under
`_researching/<slug>.md`. Claude classifies gaps by editing the stub's
frontmatter. The reconciler projects frontmatter changes into the
`knowledge.gaps` table, which stays authoritative for reads (review queue,
MCP tools) but derived from the vault for writes.

Source-of-truth inverts: **vault → DB (derived index)**, not the current
**DB → vault (parallel store)**.

## Architecture shift

| Layer                 | Before (PR #2193)              | After                                                              |
| --------------------- | ------------------------------ | ------------------------------------------------------------------ |
| Write source of truth | `knowledge.gaps` table         | `_researching/<slug>.md` frontmatter                               |
| Reads                 | Direct DB query                | DB (index projected from frontmatter)                              |
| Classification        | Python writes `gaps.gap_class` | Claude edits stub's `gap_class:` frontmatter → reconciler projects |
| User override         | HTTP PATCH / raw SQL           | Edit stub frontmatter in Obsidian                                  |
| Discovery             | `discover_gaps` inserts DB row | `discover_gaps` inserts DB row **and** writes stub file            |

## Components

### 1. Stub note format

`_researching/<slug>.md`:

```markdown
---
id: linkerd-mtls
title: "Linkerd mTLS"
type: gap
status: discovered # discovered → classified → in_review → committed/rejected
gap_class: null # set by classifier: external | internal | hybrid | parked
referenced_by:
  - note-a
  - note-b
discovered_at: "2026-04-25T08:00:00Z"
classified_at: null
classifier_version: null
---
```

Both path (`_researching/`) and frontmatter (`type: gap`) signal the stub's
role — matching the `_processed/` + `type: atom` convention used elsewhere.
Body stays empty until the gap is answered.

### 2. Discovery (`discover_gaps`, extended)

For each unresolved wikilink target:

- If no Gap row exists → insert one (`state='discovered'`)
- If no stub file exists at `_researching/<slug>.md` → write one
- Both sides idempotent; either heals the other on re-run

### 3. Reconciler (extended)

When the reconciler processes a note with `type: gap`:

- Skip chunking / embedding (gaps aren't retrieval targets; they're
  pipeline state)
- Match the stub to its Gap row via `note_id`
- Project frontmatter into the Gap row:
  `gap_class`, `status` (→ `state`), `classifier_version` (→ `pipeline_version`),
  `classified_at`, `resolved_at`

The reconciler remains the only writer to `knowledge.gaps` after this
design lands (aside from `discover_gaps` creating new rows).

### 4. Classifier job (`knowledge.classify-gaps`)

New scheduled job, 1-minute tick. Each tick:

1. Glob `_researching/*.md` for stubs with `gap_class: null` (or missing)
2. Take up to N stubs (initial N = 10)
3. Spawn one `claude --print` subprocess with the batch; allowed tools:
   `Read, Edit` (no Write, no Bash — the classifier cannot create or
   execute new code paths)
4. Prompt gives Claude a classification rubric and asks it to `Edit` each
   stub's frontmatter to set `gap_class`, `status: classified`,
   `classifier_version`, `classified_at`
5. On subprocess exit, job returns; reconciler picks up the frontmatter
   changes on its next tick and updates DB rows

1793-gap backlog at N=10 per minute drains in ~3 hours. Steady-state
(new discoveries per gardener cycle) keeps pace without a tight loop.

Privacy-conservative default still applies: if Claude returns an invalid
value or cannot decide, stubs stay `gap_class: null` and get retried next
tick. We do not auto-route to `internal` just because the classifier
hiccuped — the design doc's uncertainty rule is about real classifier
output, not absence.

### 5. Migration

```sql
-- 20260425xxxxxx_knowledge_gaps_stub_notes.sql

-- Add the file ↔ gap connection (string-identity pattern matching
-- AtomRawProvenance.derived_note_id).
ALTER TABLE knowledge.gaps
  ADD COLUMN note_id TEXT;
CREATE INDEX gaps_note_id ON knowledge.gaps (note_id);

-- Collapse (term, source) duplicates to (term). 1793 rows likely collapses
-- to a much smaller set of distinct terms. Keep the oldest row per term
-- (earliest discovery timestamp).
WITH winners AS (
  SELECT MIN(id) AS id FROM knowledge.gaps GROUP BY term
)
DELETE FROM knowledge.gaps WHERE id NOT IN (SELECT id FROM winners);

-- Swap uniqueness: one gap per term globally.
ALTER TABLE knowledge.gaps DROP CONSTRAINT gaps_term_source_note_fk_key;
ALTER TABLE knowledge.gaps ADD CONSTRAINT gaps_term_unique UNIQUE (term);

-- source_note_fk loses its authoritative role — stub's referenced_by +
-- note_links graph replace it. Nullable here; dropped in a follow-up
-- migration once the stub pattern is stable.
ALTER TABLE knowledge.gaps ALTER COLUMN source_note_fk DROP NOT NULL;
```

Python-side backfill (first run after deploy):

- For each Gap row with `note_id IS NULL`: compute slug from term,
  set `note_id`
- For each Gap row without a corresponding stub at `_researching/<slug>.md`:
  write the stub (`discover_gaps` handles this idempotently on next cycle —
  no separate backfill code needed)

## Data flow

```
vault/*.md                       (source notes with [[wikilinks]])
    ↓ (reconciler parses)
note_links table                 (kind='link' rows for each wikilink)
    ↓ (discover_gaps)
gaps table + _researching/*.md   (paired entities per unresolved target)
    ↓ (classifier job)
_researching/<slug>.md edited    (Claude sets gap_class via Edit tool)
    ↓ (reconciler projects frontmatter → DB)
gaps.gap_class populated, gaps.state='classified'
    ↓ (reconciler + future answer flow)
review queue (MCP tool) + DB queries

```

## Observability

One new SigNoz alert (log pattern-based):

- **`knowledge.classify-gaps: classifier returned invalid class`** — if
  Claude produces an unexpected value and we retry; spike = prompt drift

Metrics (log extra dict from the scheduled job):

- `knowledge.classify-gaps complete` with
  `{stubs_processed, gaps_classified, invalid_output_count, duration_ms}`

Existing gardener log line already carries `gaps_discovered` /
`gaps_classified`. `gaps_classified` keeps its meaning (count of state
transitions this cycle).

## Testing

- Unit tests (SQLite + tmp_path):
  - `discover_gaps` creates both a DB row and a stub file
  - `discover_gaps` is idempotent across both sides (re-running on existing
    term + missing stub heals the stub; re-running on existing stub +
    missing row heals the row)
  - Reconciler projects `gap_class` from frontmatter into DB row
  - Reconciler ignores `type: gap` notes for chunking/embedding
- Integration test (gardener cycle against tmp vault):
  - Seed source note + unresolved wikilink → run cycle → verify stub +
    Gap row
  - Fake classifier overwrites frontmatter → run cycle → verify DB state
    projection
- Classifier job test with mocked `claude` subprocess (stub subprocess
  that edits stub files deterministically, no real model call)

## Out of scope for this PR

- Answer flow via vault writes (still goes through the existing HTTP /
  MCP → `knowledge.gaps.answer_gap` path for now; migrating that to
  stub-write-body-and-move is a follow-up)
- External research pipeline (Qwen bulk extraction, verification,
  consolidation) — a later PR once we see the classification distribution
- Dropping `source_note_fk` column — happens in a follow-up once the
  stub pattern is stable
- Cluster-scoped briefing (design doc feature; not needed for per-stub
  classification)
- Domain-reputation substrate — design doc calls it out; only relevant
  once external research exists
- Agentic sub-agent parallelism — plain sequential classification within
  one subprocess is fast enough for the backlog; revisit only if steady-state
  wall-clock becomes a problem

The follow-up implementation plan will take this as its contract.
