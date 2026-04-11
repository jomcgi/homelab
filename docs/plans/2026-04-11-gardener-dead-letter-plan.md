# Gardener Dead Letter Queue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the grandfather sweep, add dead letter tracking for failed gardener runs, expose dead letter API endpoints, increase the Claude subprocess timeout, and unblock the 2 stuck YouTube videos.

**Architecture:** Failed gardener attempts are tracked as `failed` provenance rows with `error` and `retry_count` columns. Fresh raws have priority over retries. After 3 failures, raws are dead-lettered and only replayable via API. The grandfather sweep is deleted — migration is complete.

**Tech Stack:** Python (FastAPI, SQLModel), PostgreSQL (Atlas migrations), Bazel (bb remote test)

---

### Task 1: SQL migration — add error and retry_count columns

**Files:**

- Create: `projects/monolith/chart/migrations/20260411000000_dead_letter_columns.sql`

**Step 1: Write the migration**

```sql
-- Add dead letter tracking columns to atom_raw_provenance.
ALTER TABLE knowledge.atom_raw_provenance
    ADD COLUMN error TEXT,
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
```

**Step 2: Commit**

```
git add projects/monolith/chart/migrations/20260411000000_dead_letter_columns.sql
git commit -m "feat(knowledge): add error and retry_count columns to atom_raw_provenance"
```

---

### Task 2: Update the SQLModel — add new fields to AtomRawProvenance

**Files:**

- Modify: `projects/monolith/knowledge/models.py:125-145`

**Step 1: Write the failing test**

In `projects/monolith/knowledge/gardener_test.py`, add a test class that verifies the model accepts the new fields and that retry_count defaults to 0.

**Step 2: Run test to verify it fails**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

Expected: FAIL — `AtomRawProvenance` doesn't accept `error` or `retry_count`.

**Step 3: Add fields to the model**

In `projects/monolith/knowledge/models.py`, add to `AtomRawProvenance`:

```python
    error: str | None = None
    retry_count: int = Field(default=0)
```

**Step 4: Run test to verify it passes**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

Expected: PASS

**Step 5: Commit**

```
git add projects/monolith/knowledge/models.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): add error and retry_count fields to AtomRawProvenance"
```

---

### Task 3: Remove grandfather logic

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py` — delete `_grandfather_untracked_raws()` and its call in `run()`
- Modify: `projects/monolith/knowledge/gardener_test.py` — delete `TestGrandfatherUntrackedRaws` class
- Modify: `projects/monolith/knowledge/gardener_coverage_test.py` — remove `_grandfather_untracked_raws` references in outdated-provenance test setup comments

**Step 1: Delete `_grandfather_untracked_raws()` method** (lines 162-198 of gardener.py)

**Step 2: Remove its call from `run()`** — delete the grandfather comment block and method call

**Step 3: Delete the `TestGrandfatherUntrackedRaws` class** (lines 570-634 of gardener_test.py)

**Step 4: Update coverage test comments** that reference `_grandfather_untracked_raws`

**Step 5: Run tests**

```
bb remote test //projects/monolith:knowledge_gardener_test //projects/monolith:knowledge_gardener_coverage_test --config=ci
```

Expected: PASS

**Step 6: Commit**

```
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py projects/monolith/knowledge/gardener_coverage_test.py
git commit -m "refactor(knowledge): remove grandfather sweep — migration complete"
```

---

### Task 4: Record failed provenance on gardener errors

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py` — `_ingest_one()` exception handler

**Step 1: Write the failing test — failed provenance recorded on exception**

Add `TestIngestOneRecordsFailedProvenance` to `gardener_test.py` with:

- `test_records_failed_provenance_on_exception` — subprocess raises, provenance row created with `derived_note_id="failed"`, `retry_count=1`, `error` populated
- `test_increments_retry_count_on_repeated_failure` — pre-existing failed provenance with `retry_count=1`, after another failure it becomes `retry_count=2`

**Step 2: Run test to verify it fails**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

**Step 3: Implement `_record_failed_provenance()` helper**

New method on `Gardener`:

- Queries for existing `failed` provenance row for this raw
- If exists: update `error`, increment `retry_count`, update `gardener_version`
- If not: insert new row with `retry_count=1`
- Commit

Modify `_ingest_one()`: wrap `_run_claude_subprocess()` in try/except, call `_record_failed_provenance()` on failure, then re-raise.

**Step 4: Run test to verify it passes**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

**Step 5: Commit**

```
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): record failed provenance with error and retry_count"
```

---

### Task 5: Prioritized decomposition — fresh first, retries second

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py` — `_raws_needing_decomposition()`

**Step 1: Write failing tests**

Add `TestRawsNeedingDecompositionPriority` to `gardener_test.py`:

- `test_fresh_raws_before_retriable_failed` — fresh raw and failed raw with `retry_count=1`; fresh appears first
- `test_exhausted_raws_excluded` — raw with `retry_count=3` not returned

**Step 2: Rewrite `_raws_needing_decomposition()`**

Add `_MAX_RETRIES = 3` class constant. Two-tier query:

1. Fresh: raws with no current-version or pre-migration provenance
2. Retriable: raws with `derived_note_id="failed"` AND `retry_count < _MAX_RETRIES`

Return `fresh + retriable`, capped by `max_files_per_run`.

**Step 3: Run tests, commit**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
git commit -m "feat(knowledge): prioritize fresh raws over retriable failures in gardener"
```

---

### Task 6: Increase Claude subprocess timeout to 15 minutes

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py`

**Step 1: Change `_CLAUDE_TIMEOUT_SECS` from 300 to 900**

**Step 2: Run tests, commit**

```
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
git commit -m "fix(knowledge): increase gardener Claude timeout to 15 minutes"
```

---

### Task 7: Dead letter API endpoints

**Files:**

- Modify: `projects/monolith/knowledge/router.py`
- Create: `projects/monolith/knowledge/dead_letter_test.py`
- Modify: `projects/monolith/BUILD` — add test target

**Step 1: Write failing tests**

Create `dead_letter_test.py` with session/client fixtures (follow pattern from `ingest_queue_router_test.py`):

- `TestListDeadLetters`: returns exhausted raws (`retry_count >= 3`), excludes retriable, empty when none
- `TestReplayDeadLetter`: replays by deleting provenance row, 404 for unknown, 404 for non-dead-lettered

**Step 2: Add Bazel test target** in `projects/monolith/BUILD`

**Step 3: Implement endpoints in `router.py`**

`GET /dead-letter`:

- Join `RawInput` with `AtomRawProvenance` where `derived_note_id="failed"` and `retry_count >= Gardener._MAX_RETRIES`
- Return `{items: [{id, path, source, error, retry_count, last_failed_at}]}`

`POST /dead-letter/{raw_id}/replay`:

- Find dead-lettered provenance row, delete it, return `{replayed: true}`
- 404 if raw not found or not in dead letter state

**Step 4: Run tests, commit**

```
bb remote test //projects/monolith:knowledge_dead_letter_test --config=ci
git commit -m "feat(knowledge): add dead letter list and replay API endpoints"
```

---

### Task 8: SQL migration — unblock YouTube videos

**Files:**

- Modify: `projects/monolith/chart/migrations/20260411000000_dead_letter_columns.sql`

**Step 1: Append to the migration file**

```sql
-- Unblock YouTube videos wrongly grandfathered on 2026-04-11.
DELETE FROM knowledge.atom_raw_provenance
WHERE raw_fk IN (
    SELECT id FROM knowledge.raw_inputs
    WHERE source = 'youtube'
      AND path LIKE '_raw/2026/04/11/%'
)
AND gardener_version = 'pre-migration';
```

**Step 2: Commit**

```
git commit -m "fix(knowledge): unblock wrongly-grandfathered YouTube videos"
```

---

### Task 9: Bump chart version

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` — bump patch version
- Modify: `projects/monolith/deploy/application.yaml` — update `targetRevision`

**Step 1: Bump both files** (read current version, increment patch)

**Step 2: Run format**

**Step 3: Commit**

```
git commit -m "chore(monolith): bump chart version"
```

---

### Task 10: Run all tests, create PR

**Step 1: Run all monolith tests**

```
bb remote test //projects/monolith/... --config=ci
```

**Step 2: Push and create PR**

Title: `feat(knowledge): gardener dead letter queue + remove grandfather`

Summary:

- Remove `_grandfather_untracked_raws()` — migration complete, sweep was wrongly suppressing fresh ingests
- Record `failed` provenance with error message and retry count
- Prioritize fresh raws over retries in `_raws_needing_decomposition()`
- Add `GET /api/knowledge/dead-letter` and `POST /api/knowledge/dead-letter/{id}/replay`
- Increase Claude subprocess timeout from 5min to 15min
- Unblock 2 YouTube videos stuck since 2026-04-11

Test plan:

- [ ] `bb remote test //projects/monolith/... --config=ci` passes
- [ ] After deploy, SigNoz logs show no `gardener: grandfathered` messages
- [ ] YouTube videos picked up by gardener on next cycle
- [ ] `GET /api/knowledge/dead-letter` returns empty initially
- [ ] Simulated failure appears in dead letter after 3 retries

**Step 3: Enable auto-merge with `--auto --rebase`**
