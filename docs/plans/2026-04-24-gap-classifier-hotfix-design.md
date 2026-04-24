# Gap Classifier Hotfix — Design

## Context

PR #2194 shipped the Claude-backed classifier + stub-notes pattern at chart
`0.53.8`, deployed to production at 22:26:15Z on 2026-04-24. The rollout
worked — Claude is classifying stubs (`accelerate.md` got
`gap_class: external`, `classifier_version: opus-4-7@v1`) — but **two
real bugs surfaced against production data that the test suite missed**.

## Bugs

### 1. Slug collisions crash the reconciler's DB projection

`_project_gap_frontmatter` queries by `Gap.note_id` and calls
`scalar_one_or_none()`. The migration enforced `UNIQUE(term)`, but two
distinct `term` values can slug to the same `note_id` (e.g.
`"Outside-In TDD"` vs `"Outside In TDD"` → `outside-in-tdd`). Both pass
the term-uniqueness check, the reconciler hits `MultipleResultsFound`,
and **31 stubs/cycle lose their classifications**.

```
sqlalchemy.exc.MultipleResultsFound: Multiple rows were found when one
or none was required
  File ".../knowledge/reconciler.py", line 412, in _project_gap_frontmatter
    ).scalar_one_or_none()
```

**Why tests missed it:** the integration test seeds one term per slug, so
slug uniqueness was trivially preserved. Real-world wikilink variation
exposed it within the first reconcile cycle.

### 2. Claude appends duplicate frontmatter keys instead of replacing

The classifier prompt asks Claude to "set `gap_class`, `status: classified`,
…", and Claude uses `Edit` to add new lines at the end of the frontmatter
block without removing the existing `status: discovered` line. Result:

```yaml
status: discovered      # original line from discover_gaps
gap_class: external     # appended by Claude
classified_at: …
classifier_version: …
status: classified      # appended by Claude — duplicates line above
```

YAML last-wins so `meta.status` parses as `classified`, but the file is
ugly, the duplicate compounds on each reclassify, and Obsidian users
will see redundant keys.

### 3. Legacy gardener path emits misleading warnings

The gardener still calls `gaps.classify_gaps(self.session, classifier=None)`
each cycle as a no-op, which logs:

```
WARNING knowledge.gaps: gaps.classify_gaps: 815 gaps awaiting
classification but no classifier is wired
```

The new scheduled job (`knowledge.classify-gaps`) replaced this path.
The warning is now noise that suggests the rollout is broken when it
isn't.

## Outcome

Reconciler projects every stub successfully — zero `MultipleResultsFound`
in steady state. Claude's edits produce clean frontmatter with no
duplicate keys. The misleading legacy-path warning stops firing.

## Architecture decisions

### Slug-collision merge policy: **one row per `note_id`**

When two `term`s slug to the same `note_id`:

- **Keep** the Gap row with the lowest `id` (earliest discovered).
- **Drop** the other row(s).
- **Union** `referenced_by` into the surviving stub's frontmatter (the
  set of source notes pointing at this term — both spellings — collapses
  to one set).
- The surviving `term` value is whichever the lowest-`id` row had. We
  lose the alternate spelling, which is fine: `note_id` is now the
  user-facing identifier (it's the filename slug in `_researching/`),
  and `term` is a historical hint.

### Schema: add `UNIQUE(note_id)`

The `note_id` column was added in the previous migration but only
indexed (not unique). This hotfix:

1. Dedups existing rows by `note_id`.
2. Adds `ALTER TABLE knowledge.gaps ADD CONSTRAINT gaps_note_id_unique
UNIQUE (note_id)`.
3. Drops the now-redundant non-unique index `gaps_note_id` (the
   constraint creates its own).

`UNIQUE(term)` stays — `term` is still our discovery dedup key from
`note_links` rows — but `UNIQUE(note_id)` is now the projection-layer
guarantee.

### `discover_gaps` collision handling

When `_slugify(term)` collides with an existing row's `note_id`:

- If the term **matches** the existing row's term: standard idempotent
  upsert (current behavior).
- If the term **differs** but slugs to the same `note_id`: append the
  new `referenced_by` source to the surviving row's stub frontmatter.
  Do **not** insert a second row.

The `UNIQUE(note_id)` constraint catches any path that misses this
logic, so the constraint is the safety net.

### Classifier prompt: explicit replace semantics

Update `_CLASSIFIER_PROMPT` to spell out:

> When updating the stub's frontmatter, you must replace existing values
> rather than appending. The stub already contains
> `status: discovered` — use Edit to change that line to
> `status: classified`. Do **not** add a new `status:` line; YAML
> requires unique top-level keys.

Backfill the ~600 already-classified stubs in production by running a
one-time vault sweep that collapses duplicate keys (last-wins). This is
file-system-only, no DB writes; the reconciler's next cycle picks up
the cleaned frontmatter.

### Drop the gardener's legacy classify_gaps call

Remove the call from `gardener.py`. Keep the `gaps.classify_gaps`
function defined (still useful as a unit-test seam and for tests
already importing it), just stop invoking it on the cycle.

## Components

### 1. Migration `20260425010000_knowledge_gaps_note_id_unique.sql`

```sql
-- Dedupe by note_id, keeping the earliest row per slug.
WITH winners AS (
  SELECT MIN(id) AS id FROM knowledge.gaps
  WHERE note_id IS NOT NULL
  GROUP BY note_id
)
DELETE FROM knowledge.gaps
WHERE note_id IS NOT NULL AND id NOT IN (SELECT id FROM winners);

-- Drop the non-unique index in favor of the constraint.
DROP INDEX IF EXISTS knowledge.gaps_note_id;

-- The new invariant.
ALTER TABLE knowledge.gaps
  ADD CONSTRAINT gaps_note_id_unique UNIQUE (note_id);
```

### 2. `discover_gaps` slug-collision handling

When iterating unresolved wikilinks:

- Compute `note_id = _slugify(term)`.
- Query for existing row by `note_id` (not just `term`).
- If found and `term` matches: existing idempotent path.
- If found and `term` differs: skip insert, accumulate the new
  `referenced_by` entry into the stub instead.
- If not found: insert + write stub as today.

### 3. Stub backfill helper (one-shot)

A `dedupe_stub_frontmatter` function called once at gardener startup (or
as a manual admin endpoint — TBD in plan):

- Walk `_researching/*.md`.
- For each stub: re-parse frontmatter, collapsing duplicate keys
  (last-wins). Write back if any duplicates were collapsed.
- Idempotent: subsequent runs are no-ops.

### 4. Classifier prompt update

`_CLASSIFIER_PROMPT` in `gap_classifier.py` gains an explicit "replace,
do not append" rule + an example of what good Edit usage looks like.

### 5. Gardener cleanup

Remove `gaps.classify_gaps(self.session)` call from gardener cycle. The
gardener log line `gaps_classified=N` is no longer meaningful (the
scheduled job owns this metric); remove it from the log dict too.

## Migration ordering

The hotfix migration is `20260425010000_*` — strictly after the
`20260425000000_*` migration that shipped in PR #2194. Atlas applies in
filename order, so this is automatic.

## Testing

Unit tests added:

- `discover_gaps` two terms slugging to same `note_id` → one row, two
  entries in `referenced_by`.
- `_project_gap_frontmatter` against a single-row-per-note_id world is
  the existing test path; the new test asserts no `MultipleResultsFound`
  is possible (post-constraint).
- `dedupe_stub_frontmatter` collapses duplicate `status:` keys.
- Classifier prompt test: regression that the prompt string contains
  the explicit replace-don't-append clause (cheap drift detector).

Integration test extended:

- Seed two source notes that wikilink to slug-colliding terms
  (`[[Outside-In TDD]]` and `[[Outside In TDD]]`) → run
  `discover_gaps` → assert one Gap row, one stub, both source notes in
  `referenced_by`.

## Out of scope

- Refactoring `term` away entirely (still useful as an audit hint).
- Changing the classifier prompt's classification rubric (the
  4-class system is fine; only the edit-discipline language changes).
- Removing `source_note_fk` (still deferred from PR #2194's design).
- Adding observability for slug collisions (would be nice for future
  monitoring; defer until we see whether the fix sticks).

## Rollout plan

1. Merge hotfix PR.
2. Watch for the new chart version to deploy (image-updater pattern as
   PR #2194).
3. Verify the migration runs cleanly (no `MultipleResultsFound` in the
   first reconcile cycle post-deploy).
4. Confirm `dedupe_stub_frontmatter` cleaned up the ~600 existing
   stubs (their next reconcile cycle should report `failed=0`).
5. Confirm SigNoz `knowledge.classify-gaps complete` events show
   non-zero `stubs_processed` and zero `invalid_output_count`.
