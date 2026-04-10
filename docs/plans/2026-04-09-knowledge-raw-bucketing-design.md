# Knowledge Raw Bucketing Design

## Goal

Restructure the knowledge pipeline around two explicit buckets:

- **Raw** — immutable ground-truth inputs, preserved forever
- **Processed** — disposable derived atoms/facts/active notes, regenerable from Raw

Replaces the current flow where raw inputs TTL-expire after 24 hours and no explicit provenance links derived atoms back to their source.

## Motivation

The current gardener design (`docs/plans/2026-04-08-knowledge-gardener-design.md`) treats raw inputs as transient — they land in the vault root, get decomposed into `_processed/` by the gardener, then get moved to `_deleted_with_ttl/` and purged after 24 hours. This optimises for vault cleanliness but has three weaknesses:

1. **No reprocessing.** When the gardener prompt or model version improves, you can't re-derive better atoms from the original inputs — the inputs are gone.
2. **No audit trail.** Given any atom, there's no way to trace back to the exact input it was derived from.
3. **No recovery.** 24 hours is a hard cliff. Anything you realise you wanted beyond that window is unrecoverable.

All three weaknesses resolve if Raw is treated as the immutable source of truth and Processed is treated as a regenerable cache.

## Bucket Model

Two buckets, not three:

- **Raw** — every input (vault drop, insert API, web share, Discord backfill) lands here and stays forever. Lives in `_raw/` on the filesystem and as a row in `knowledge.raw_inputs`. Indexed and searchable via a mirror row in `knowledge.notes` with `type='raw'`, but filtered from default search results.
- **Processed** — atoms, facts, and active notes produced by the gardener from Raw. Current state only: no soft deletes, no tombstones. Hard deletes are fine because Raw makes them recoverable.

The "Deleted" bucket collapses away. If an atom disappears, the answer to "why?" is "the current gardener, running against current Raw, didn't produce it." Deletion is implicit in the gardener's behaviour, not a separate state.

**Key constraint:** atoms/facts become **read-only derived data**. Manual edits are silently clobbered by any future reprocessing pass. To correct an atom, correct its Raw (or add a new Raw) and let the gardener regenerate.

## Storage Layout

### Filesystem (Obsidian vault)

```
vault/
├── _raw/                              # NEW — immutable raw inputs
│   ├── grandfathered/                 # one-shot: recovered from _deleted_with_ttl/
│   │   └── <hash-prefix>-<slug>.md
│   └── YYYY/MM/DD/                    # ongoing: organised by ingestion date
│       └── <hash-prefix>-<slug>.md
├── _processed/                        # EXISTING — atoms/facts/active
│   ├── atoms/
│   ├── facts/
│   └── active/
└── _deleted_with_ttl/                 # REMOVED after migration
```

Raw filenames use a content-hash prefix so collisions are impossible and identity is visible from the filename alone. New raws go under `_raw/YYYY/MM/DD/`; pre-migration raws recovered from `_deleted_with_ttl/` go under `_raw/grandfathered/` as a one-shot population that only shrinks over time.

### Database

#### `knowledge.raw_inputs` (new table)

| column          | type        | purpose                                                             |
| --------------- | ----------- | ------------------------------------------------------------------- |
| `id`            | serial PK   |                                                                     |
| `raw_id`        | text unique | stable identity — sha256 of body                                    |
| `path`          | text unique | vault-relative path under `_raw/`                                   |
| `source`        | text        | `vault-drop`, `insert-api`, `web-share`, `discord`, `grandfathered` |
| `original_path` | text        | where it came from before being moved to `_raw/` (if known)         |
| `content`       | text        | full markdown body (duplicated from disk; see rationale below)      |
| `content_hash`  | text        | sha256, matches `raw_id`                                            |
| `created_at`    | timestamptz | when ingested                                                       |
| `extra`         | jsonb       | source-specific metadata (discord ids, web urls, …)                 |

Rationale for duplicating `content` in the DB: enables DB-only search/provenance queries without a filesystem round-trip, and provides a safety net if the filesystem and DB diverge. At homelab scale the storage cost is negligible.

#### `knowledge.atom_raw_provenance` (new table)

| column             | type                               | purpose                       |
| ------------------ | ---------------------------------- | ----------------------------- |
| `atom_fk`          | integer NULL, FK → `notes.id`      | derived atom/fact/active note |
| `raw_fk`           | integer NULL, FK → `raw_inputs.id` | source raw input              |
| `gardener_version` | text NOT NULL                      | model ID + prompt hash        |
| `created_at`       | timestamptz NOT NULL               |                               |

Constraints and indexes:

- `CHECK (atom_fk IS NOT NULL OR raw_fk IS NOT NULL)` — at least one side populated
- `UNIQUE (atom_fk, raw_fk)` where both non-null — prevents duplicate real edges
- `UNIQUE (atom_fk) WHERE raw_fk IS NULL AND gardener_version = 'pre-migration'` — one grandfather row per atom
- `UNIQUE (raw_fk) WHERE atom_fk IS NULL AND gardener_version = 'pre-migration'` — one "already processed" sentinel per raw
- Index on `raw_fk` — "what did this raw produce?"
- Index on `gardener_version` — "what's stale?"

The `atom_fk IS NULL` sentinel form marks a raw as already-decomposed by a previous gardener version (used by the migration to prevent duplicate regeneration). The `raw_fk IS NULL` sentinel form marks an atom as grandfathered (no known source raw).

#### `knowledge.notes` (existing table, one change)

Add `'raw'` to the allowed `type` values alongside `'atom' | 'fact' | 'active'`. When a raw is ingested it gets a mirror row in `notes` with `note_id = raw_id`, so the existing reconciler embeds it without modification. The mirror approach (vs. teaching the reconciler to read from `raw_inputs`) was chosen because it touches almost no existing code.

## Ingestion Flow

Crash-safe via a three-phase loop — each phase is independently idempotent and safe to interrupt.

### Phase A — Move (the atomic commit point)

```
move_phase():
    for each .md file in vault root (not in _raw/, _processed/, _deleted_with_ttl/):
        compute content_hash
        target = _raw/YYYY/MM/DD/<hash-prefix>-<slug>.md
        if target already exists:
            delete source         # dedup — we already have this content
        else:
            os.rename(source, target)   # atomic within the same filesystem
```

After Phase A, every raw file is physically in `_raw/`. An interrupted `rename(2)` either completed or didn't — no partial states. A crash between moves just means the next cycle finishes the job.

### Phase B — DB reconcile (idempotent)

```
reconcile_raw_phase():
    for each .md file under _raw/:
        if raw_inputs row exists for this path → skip
        parse frontmatter and body
        insert raw_inputs row
        insert notes row (type='raw', note_id=raw_id)
```

Idempotent on path — re-running after a crash is a no-op for already-reconciled files.

### Phase C — Decompose (existing gardener logic, essentially unchanged)

```
for each raw_input where NOT EXISTS (
    SELECT 1 FROM atom_raw_provenance
    WHERE raw_fk = raw_input.id
      AND (gardener_version = :current_version OR gardener_version = 'pre-migration')
):
    run claude CLI subprocess with raw content
    claude writes atom/fact .md files to _processed/
    after subprocess exits, insert atom_raw_provenance(atom_fk, raw_fk, current_version, now())
```

The `NOT EXISTS` clause handles new raws naturally (no provenance rows yet) and also respects the `pre-migration` sentinel (grandfathered raws are skipped until an explicit manual reprocess). When `gardener_version` changes, a manual reprocess command can target specific raws to regenerate.

### Entry points

All ingestion paths become trivial — "write a markdown file to the vault root":

- **Vault drop** — Obsidian sync drops files as usual. Phase A catches them.
- **Insert API** — writes directly to the vault root. No DB knowledge needed.
- **Web share** — writes directly to the vault root.
- **Discord backfill** — writes directly to the vault root with source metadata in frontmatter.

### Removed

- `_deleted_with_ttl/` folder — no longer exists post-migration
- TTL cleanup phase — no TTL to clean up

## Reprocessing

**Automatic reprocessing** runs for new raws every gardener cycle via Phase C's `NOT EXISTS` query.

**Manual reprocessing** is an explicit operator action, not yet implemented, but the machinery is in place from day one:

```sql
-- Find raws that need manual reprocessing (stale or grandfathered):
SELECT DISTINCT r.id
FROM knowledge.raw_inputs r
LEFT JOIN knowledge.atom_raw_provenance p ON p.raw_fk = r.id
WHERE p.gardener_version != :current_version
   OR p.gardener_version = 'pre-migration'
   OR p.gardener_version IS NULL;
```

When a manual reprocess is triggered for a raw, the operator command (future work) deletes the atoms currently linked to it (plus their provenance rows) and re-runs Phase C, stamping the new `gardener_version`.

Stamping `gardener_version` on every provenance row from day one is cheap to add up front and painful to retrofit.

## Migration

Executed as a one-shot offline maintenance window:

1. Take the monolith offline (scale deployment to 0).
2. Apply schema migration: create `raw_inputs` and `atom_raw_provenance` tables, add `'raw'` to the `notes.type` check constraint.
3. Run a local migration script against the vault and DB:
   1. **Recover surviving raws from `_deleted_with_ttl/`:**
      - Walk `_deleted_with_ttl/` for `.md` files
      - Strip `ttl:` and `original_path:` frontmatter keys
      - Move each file to `_raw/grandfathered/<hash-prefix>-<slug>.md`
      - Insert `raw_inputs` row with `source='grandfathered'`, `original_path` from stripped frontmatter
      - Insert `notes` row with `type='raw'`
      - Insert sentinel provenance row `(atom_fk=NULL, raw_fk=<id>, gardener_version='pre-migration')`
   2. **Grandfather existing derived notes:**
      - For each row in `knowledge.notes` with `type IN ('atom','fact','active')`, insert sentinel provenance row `(atom_fk=<id>, raw_fk=NULL, gardener_version='pre-migration')`
   3. Delete empty `_deleted_with_ttl/` folder
4. Deploy new gardener code.
5. Bring the monolith back online.
6. First gardener cycle runs normally; Phase C sees grandfathered raws as "already processed" (via the sentinel) and skips them, so no duplicate atoms are produced.

The offline maintenance window eliminates races between ingestion and migration. The migration script is still written to be idempotent (using `ON CONFLICT DO NOTHING` on all inserts) so it's safe to re-run if interrupted.

Grandfathered atoms are effectively pinned — immune to automatic reprocessing because their sentinel row has `raw_fk IS NULL`. They can be explicitly nuked and regenerated later if desired, but by default they persist forever as "manually curated" pre-migration knowledge. The grandfathered population is bounded and shrinks naturally as atoms are replaced over time.

## New Files

- `projects/monolith/chart/migrations/<timestamp>_raw_bucketing_schema.sql` — schema migration
- `projects/monolith/knowledge/raw_ingest.py` — Phase A + Phase B implementation
- `projects/monolith/knowledge/raw_ingest_test.py`
- `projects/monolith/knowledge/migrations/migrate_raw_bucketing.py` — one-shot migration script
- `projects/monolith/knowledge/migrations/migrate_raw_bucketing_test.py`

## Modified Files

- `projects/monolith/knowledge/models.py` — add `RawInput` and `AtomRawProvenance` SQLModel classes; extend `type` docstring
- `projects/monolith/knowledge/gardener.py` — integrate Phase A and Phase B into the garden loop; remove TTL cleanup
- `projects/monolith/knowledge/service.py` — adjust garden job registration if needed
- `projects/monolith/knowledge/reconciler.py` — no changes expected (handles `type='raw'` via existing code paths)
- Insert API handler — write to vault root instead of its current destination (if different)

## Interaction With In-Flight Work

This design lands on the same codebase as the gardener-claude-cli plan (`docs/plans/2026-04-09-gardener-claude-cli.md`). The CLI migration changes **how** Phase C decomposes (Anthropic SDK → `claude` CLI subprocess); this design adds **Phase A and Phase B around it**. The two are mostly orthogonal but will need careful sequencing — merge the CLI work first, then rebase this on top.

## Deferred

- **Manual reprocessing command** — the DB machinery is in place, but the operator CLI/API surface to trigger reprocessing is out of scope for this design. Will be added when the first gardener version bump warrants it.
- **Search type filtering UI** — the default search will exclude `type='raw'`. Exposing a "include raw" toggle in the UI is a future UX concern.
- **Grandfathered atom cleanup** — a dedicated "regenerate all grandfathered atoms" operator command is out of scope; it can be done with ad-hoc SQL when needed.
- **Raw compaction / cold storage** — if raws grow unbounded and Postgres starts feeling it, future work can migrate old raws to object storage. Not a concern at current scale.

## Risks

- **Grandfathered atoms drift.** Over time, the grandfathered population becomes stale relative to newer atoms, and there's no easy way to know which ones "should" have been reprocessed. Mitigated by the fact that grandfathered atoms are bounded in count and will organically shrink.
- **Content duplication between filesystem and `raw_inputs.content`.** If the two diverge (e.g., an out-of-band filesystem edit), search results may not match the on-disk file. Mitigated by the "atoms are read-only" principle — raw files should not be edited in-place either, post-ingestion.
- **First gardener cycle after migration could be long** if many new (non-grandfathered) raws exist. Acceptable one-off cost.
