# Gardener Dead Letter Queue & Grandfather Removal

## Problem

The gardener's `_grandfather_untracked_raws()` method marks **all** raws without
provenance as `pre-migration`, including freshly ingested items that simply
haven't been gardened yet. This permanently suppresses reprocessing. As of
2026-04-11, 153 raws are stuck — 2 YouTube videos and 151 vault-drops.

Additionally, when the gardener fails to process a raw (e.g., Claude subprocess
timeout), no sentinel is recorded. The raw sits in limbo until the grandfather
sweep marks it as `pre-migration`.

## Changes

### 1. Remove grandfather logic

Delete `_grandfather_untracked_raws()` from `Gardener` and its call in `run()`.
The migration is complete — all pre-existing raws already have `pre-migration`
sentinels. No new sentinels need to be created.

### 2. Dead letter tracking via provenance

When the gardener fails to process a raw, record a `failed` provenance row
instead of silently logging:

```python
AtomRawProvenance(
    raw_fk=raw.id,
    derived_note_id="failed",
    gardener_version=GARDENER_VERSION,
    error=str(exc)[:500],     # new column
    retry_count=prev_count+1  # new column
)
```

**New columns on `atom_raw_provenance`:**

- `error: text | null` — truncated error message from the failed attempt
- `retry_count: int default 0` — number of gardening attempts

**Processing priority in `_raws_needing_decomposition()`:**

1. Fresh raws (no provenance) — highest priority
2. Retriable raws (`derived_note_id = 'failed'` AND `retry_count < 3`) — fill
   remaining slots after fresh raws
3. Exhausted raws (`retry_count >= 3`) — dead-lettered, only reprocessable via
   replay endpoint

### 3. Increase Claude subprocess timeout

Raise `_CLAUDE_TIMEOUT_SECS` from 300 (5 minutes) to 900 (15 minutes). YouTube
transcripts can be long and require more processing time.

### 4. API endpoints

Two new routes on the existing `/api/knowledge` router:

**`GET /api/knowledge/dead-letter`** — list dead-lettered raws

Returns provenance rows where `derived_note_id = 'failed'` AND
`retry_count >= 3`. Response:

```json
{
  "items": [
    {
      "id": 48782,
      "path": "_raw/2026/04/11/51548791-youtube-jiwgkrgdgpi.md",
      "source": "youtube",
      "error": "RuntimeError: claude timed out after 300s",
      "retry_count": 3,
      "last_failed_at": "2026-04-11T05:52:16Z"
    }
  ]
}
```

**`POST /api/knowledge/dead-letter/{raw_id}/replay`** — replay a dead-lettered
raw

- `raw_id` is `raw_inputs.id` (integer PK)
- Deletes the `failed` provenance row so the gardener picks it up next cycle
- Returns `{"replayed": true}` or 404

### 5. Claude Code skill: `knowledge-dead-letter`

A skill for investigating and replaying failed gardener items:

1. Calls `GET /api/knowledge/dead-letter` via port-forward
2. Presents failed items with errors
3. Replays selected item via `POST /api/knowledge/dead-letter/{id}/replay`
4. Monitors SigNoz logs to confirm processing

### 6. Unblock YouTube videos (immediate)

Delete `pre-migration` provenance for `raw_inputs` ids 48782 and 48783 via SQL
migration. Remaining 151 vault-drops retain `pre-migration` sentinels — revisit
after confirming YouTube processing works.

## Approach chosen

DB-only (Approach A). Dead letter state lives entirely in `atom_raw_provenance`
— no file moves to `_raw/dead_letter/` on disk. The API provides visibility.
File-based dead letter was rejected due to Obsidian sync race conditions and
unnecessary complexity.
