# Gap Classifier Hotfix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan task-by-task.

**Goal:** Fix the two production bugs blocking PR #2194's classifier rollout — slug-collision crashes in the reconciler, and Claude appending duplicate frontmatter keys instead of replacing — and remove the misleading legacy gardener log line.

**Architecture:** Add `UNIQUE(note_id)` to `knowledge.gaps`, refactor `discover_gaps` to iterate by slug (not term) so two terms slugging to the same `note_id` collapse into one row, extend `write_stub` to update `referenced_by` on existing stubs, add a one-shot stub-frontmatter dedup helper called at gardener startup, tighten the classifier prompt to spell out replace-don't-append semantics, and drop the gardener's legacy `classify_gaps(classifier=None)` call now that the scheduled job owns this metric.

**Tech Stack:** Python 3.13, SQLModel/SQLAlchemy, Atlas migrations, PyYAML, pytest, Bazel/BuildBuddy, Helm/ArgoCD.

**Worktree:** `/tmp/claude-worktrees/gap-classifier-hotfix` on `feat/gap-classifier-hotfix` off `main` (`969bddcea`).

**Design doc:** `docs/plans/2026-04-24-gap-classifier-hotfix-design.md` — read this for the why behind each decision.

---

## Repo conventions every implementer must respect

- **Commit messages:** Conventional Commits (`fix:`, `feat:`, `chore:`, `test:`, `refactor:`). A `commit-msg` hook enforces this.
- **Do NOT run tests locally.** No `pytest`, no `bb remote test`, no `bazel test`. The BuildBuddy `workflows` pool has no darwin runners and the linux fallback is too unreliable for an inner loop. **Implement, format, commit. The CI run on push verifies.** TDD discipline still applies (write failing test first, then implementation), but verification of red→green happens at end-of-plan when CI runs on the pushed branch. If you're tempted to "just check one thing locally," resist — the cost is a flaky multi-minute roundtrip with opaque exit codes.
- **Format before commit:** run `format` (vendored shell alias) once after Python changes — it runs ruff + gazelle and may touch BUILD files. If `format` is not on PATH, fall back to `bazel/tools/format/fast-format.sh` from the repo root. Stash unrelated noise (`git stash push -u`) before committing your task — only commit files relevant to the task.
- **Atlas checksum:** the `Update Atlas migration checksums` pre-commit hook updates `chart/migrations/atlas.sum` automatically when you stage a new SQL migration. Don't compute the hash by hand.
- **Worktree boundary:** every change must land in `/tmp/claude-worktrees/gap-classifier-hotfix`. Never commit to `~/repos/homelab` directly.
- **PR #2194 context:** chart `0.53.8` is the deployed version. This hotfix bumps to `0.53.9`.

## Verification model

Each task ships with TDD-shaped instructions (write test first, then implementation), but the **only place tests actually execute is BuildBuddy CI** after the branch is pushed. Implementer subagents:

1. Write the failing test as specified.
2. Write the implementation as specified.
3. Format + commit.
4. **Do not** invoke `bb remote test` / `bazel test` / `pytest`. The "Step N: Run test to verify it fails/passes" lines below are _intent_ statements — verification is deferred to CI.

Spec and code-quality reviewers review the diff against the spec; they do not run tests either. After all 7 tasks land, a final task pushes the branch, opens the PR, and monitors the CI run for the actual red/green signal.

---

## Task 1: Migration — dedup duplicate `note_id` rows and add `UNIQUE(note_id)`

**Files:**

- Create: `projects/monolith/chart/migrations/20260425010000_knowledge_gaps_note_id_unique.sql`
- Modify: `projects/monolith/knowledge/models.py:181-184` (Gap.**table_args** — add UniqueConstraint)
- Modify: `projects/monolith/chart/migrations/atlas.sum` (auto-updated by pre-commit hook)
- Test: `projects/monolith/knowledge/models_test.py` (add a constraint-presence test)

**Step 1: Write the failing test.**

Add this to `projects/monolith/knowledge/models_test.py`:

```python
def test_gap_has_note_id_unique_constraint():
    """note_id is the projection-layer identity — must be UNIQUE in the schema."""
    from sqlalchemy import UniqueConstraint
    from knowledge.models import Gap

    constraints = [
        c for c in Gap.__table_args__ if isinstance(c, UniqueConstraint)
    ]
    column_sets = [tuple(c.columns.keys()) for c in constraints]
    assert ("note_id",) in column_sets, (
        f"Gap must have UniqueConstraint on note_id; got {column_sets}"
    )
```

**Step 2: Run the test to verify it fails.**

```bash
cd /tmp/claude-worktrees/gap-classifier-hotfix
bb remote test //projects/monolith:knowledge_models_test --config=ci
```

Expected: FAIL with `("note_id",) not in column_sets`.

**Step 3: Write the migration.**

Create `projects/monolith/chart/migrations/20260425010000_knowledge_gaps_note_id_unique.sql`:

```sql
-- knowledge.gaps: enforce UNIQUE(note_id).
--
-- PR #2194's migration enforced UNIQUE(term), but two terms can slugify to
-- the same note_id (e.g. "Outside-In TDD" and "Outside In TDD" both →
-- outside-in-tdd). The reconciler queries Gap rows by note_id and crashes
-- on MultipleResultsFound when collisions exist.
--
-- Dedup keeping the earliest row per note_id, then add the constraint as
-- the projection-layer guarantee. See
-- docs/plans/2026-04-24-gap-classifier-hotfix-design.md.

-- 1. Dedup by note_id, keeping the earliest row per slug.
WITH winners AS (
  SELECT MIN(id) AS id
  FROM knowledge.gaps
  WHERE note_id IS NOT NULL
  GROUP BY note_id
)
DELETE FROM knowledge.gaps
WHERE note_id IS NOT NULL
  AND id NOT IN (SELECT id FROM winners);

-- 2. Drop the non-unique index in favor of the constraint's auto-index.
DROP INDEX IF EXISTS knowledge.gaps_note_id;

-- 3. The new invariant.
ALTER TABLE knowledge.gaps
  ADD CONSTRAINT gaps_note_id_unique UNIQUE (note_id);
```

**Step 4: Update the model's `__table_args__`.**

In `projects/monolith/knowledge/models.py:181-184`, replace:

```python
    __table_args__ = (
        UniqueConstraint("term"),
        {"schema": "knowledge", "extend_existing": True},
    )
```

with:

```python
    __table_args__ = (
        UniqueConstraint("term"),
        UniqueConstraint("note_id"),
        {"schema": "knowledge", "extend_existing": True},
    )
```

**Step 5: Run the test to verify it passes.**

```bash
bb remote test //projects/monolith:knowledge_models_test --config=ci
```

Expected: PASS.

**Step 6: Run the full migration smoke (model_test covers the schema-wiring leg; the SQL itself is verified at deploy time).**

```bash
bb remote test //projects/monolith:knowledge_models_test //projects/monolith:knowledge_gap_stubs_test //projects/monolith:knowledge_reconciler_test --config=ci
```

Expected: all PASS.

**Step 7: Format and commit.**

```bash
cd /tmp/claude-worktrees/gap-classifier-hotfix
format  # or bazel/tools/format/fast-format.sh if format isn't on PATH
git stash push -u -m "format-noise" -- $(git status -s | awk '$1=="M"||$1=="??" {print $2}' | grep -v -E 'migrations/|models\.py|models_test\.py')  # only if other files were touched
git add projects/monolith/chart/migrations/20260425010000_knowledge_gaps_note_id_unique.sql \
        projects/monolith/chart/migrations/atlas.sum \
        projects/monolith/knowledge/models.py \
        projects/monolith/knowledge/models_test.py
git commit -m "fix(knowledge): enforce UNIQUE(note_id) on gaps to prevent reconciler crashes"
git stash drop  # only if you stashed in step above
```

---

## Task 2: `discover_gaps` — iterate by slug, not term

**Why:** the current loop iterates `for term, refs in referenced_by.items()`. Two distinct terms slugging to the same `note_id` produce two iterations, both call `write_stub(note_id=slug)` (second is a no-op), and both attempt INSERT. `UNIQUE(note_id)` (Task 1) now blocks the second INSERT, but the SAVEPOINT swallows the IntegrityError and the second term's `referenced_by` is silently lost. Refactor to fold by slug _before_ iterating so referenced_by accumulates correctly.

**Files:**

- Modify: `projects/monolith/knowledge/gaps.py:74-200` (`discover_gaps`)
- Test: `projects/monolith/knowledge/gaps_test.py` (or wherever `discover_gaps` tests live — search first)

**Step 1: Find the existing test file.**

```bash
grep -rln 'def test.*discover_gaps' /tmp/claude-worktrees/gap-classifier-hotfix/projects/monolith/knowledge/
```

Expected: one or more `*_test.py` files. Add the new test to the file with the most existing `discover_gaps` tests.

**Step 2: Write the failing test.**

Add to that test file:

```python
def test_discover_gaps_collapses_slug_collisions(tmp_path, session):
    """Two terms slugging to the same note_id collapse into one Gap row."""
    from knowledge.models import Gap, Note, NoteLink
    from knowledge.gaps import discover_gaps

    # Two source notes that both reference slug-colliding terms.
    src_a = Note(note_id="src-a", title="Source A", path="src-a.md", body_hash="a")
    src_b = Note(note_id="src-b", title="Source B", path="src-b.md", body_hash="b")
    session.add_all([src_a, src_b])
    session.commit()

    session.add_all([
        NoteLink(src_note_fk=src_a.id, target_id="outside-in-tdd",
                 kind="link", target_label="Outside-In TDD"),
        NoteLink(src_note_fk=src_b.id, target_id="outside-in-tdd",
                 kind="link", target_label="Outside In TDD"),
    ])
    session.commit()

    # Even though the two NoteLinks have different target_labels,
    # _slugify("Outside-In TDD") == _slugify("Outside In TDD") == "outside-in-tdd",
    # so discover_gaps should produce ONE Gap row.
    discover_gaps(session, vault_root=tmp_path)

    rows = session.execute(select(Gap).where(Gap.note_id == "outside-in-tdd")).scalars().all()
    assert len(rows) == 1, f"Expected one Gap per note_id, got {len(rows)}: {[r.term for r in rows]}"

    # The stub's referenced_by should reflect both source notes.
    import yaml
    stub_path = tmp_path / "_researching" / "outside-in-tdd.md"
    text = stub_path.read_text()
    fm = yaml.safe_load(text.split("---\n", 2)[1])
    assert sorted(fm["referenced_by"]) == ["src-a", "src-b"], (
        f"Expected union of both source notes; got {fm['referenced_by']}"
    )
```

The test imports `select` and uses a `session` fixture — match the conventions of the existing `discover_gaps` tests in the same file (look at imports / fixtures of an existing test).

**Step 3: Run the test to verify it fails.**

```bash
bb remote test //projects/monolith:<gaps_test_target> --config=ci
```

(target name is whichever owns the file you found in Step 1 — search the BUILD file for it.)

Expected: FAIL — either two rows in DB, or stub's `referenced_by` missing one source.

**Step 4: Refactor `discover_gaps` to iterate by slug.**

In `projects/monolith/knowledge/gaps.py`, replace the loop body around lines 113-190 with slug-keyed accumulation. The shape:

```python
    # Accumulate referenced_by per term first (existing).
    referenced_by: dict[str, set[str]] = {}
    contexts: dict[str, str] = {}
    source_fks: dict[str, int] = {}
    for row in link_rows:
        target_id = row.target_id
        if target_id in existing_note_ids:
            continue
        referenced_by.setdefault(target_id, set()).add(row.note_id)
        contexts.setdefault(target_id, row.title or "")
        source_fks.setdefault(target_id, row.src_note_fk)

    # Fold by slug — collapse slug-colliding terms before insert.
    # Iterate terms in deterministic (sorted) order so the canonical
    # term-per-slug is reproducible across runs.
    slug_refs: dict[str, set[str]] = {}
    slug_canonical_term: dict[str, str] = {}
    slug_context: dict[str, str] = {}
    slug_source_fk: dict[str, int] = {}
    for term in sorted(referenced_by.keys()):
        slug = _slugify(term)
        slug_refs.setdefault(slug, set()).update(referenced_by[term])
        if slug not in slug_canonical_term:
            slug_canonical_term[slug] = term
            slug_context[slug] = contexts.get(term, "")
            slug_source_fk[slug] = source_fks[term]

    # Pre-load existing rows by note_id (the projection-layer identity)
    # AND by term (for backfill of legacy rows where note_id is null).
    all_gaps = session.execute(select(Gap)).scalars().all()
    existing_by_note_id: dict[str, Gap] = {g.note_id: g for g in all_gaps if g.note_id}
    existing_by_term: dict[str, Gap] = {g.term: g for g in all_gaps}

    stub_dir = vault_root / RESEARCHING_DIR
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserted = 0
    stubs_written = 0
    backfilled = 0
    new_items = 0

    for slug, refs in slug_refs.items():
        canonical_term = slug_canonical_term[slug]
        refs_sorted = sorted(refs)
        row_inserted = False

        existing = existing_by_note_id.get(slug)
        if existing is None:
            # Maybe a legacy row exists keyed only by term — backfill its note_id.
            legacy = existing_by_term.get(canonical_term)
            if legacy is not None and legacy.note_id is None:
                legacy.note_id = slug
                backfilled += 1
            else:
                with session.begin_nested():
                    session.add(
                        Gap(
                            term=canonical_term,
                            context=slug_context[slug],
                            note_id=slug,
                            source_note_fk=slug_source_fk[slug],
                            pipeline_version=GAPS_PIPELINE_VERSION,
                            state="discovered",
                        )
                    )
                inserted += 1
                row_inserted = True

        # Stub write — write_stub is idempotent on file existence; refs
        # union per slug ensures we always pass the canonical set.
        stub_path = stub_dir / f"{slug}.md"
        stub_existed = stub_path.exists()
        write_stub(
            vault_root=vault_root,
            note_id=slug,
            title=slug,
            referenced_by=refs_sorted,
            discovered_at=now_iso,
        )
        stub_newly_written = not stub_existed
        if stub_newly_written:
            stubs_written += 1

        if row_inserted or stub_newly_written:
            new_items += 1

    if inserted or backfilled:
        session.commit()
```

Keep the existing log line / return shape unchanged.

**Step 5: Run the test to verify it passes.**

```bash
bb remote test //projects/monolith:<gaps_test_target> --config=ci
```

Expected: PASS.

**Step 6: Run all gap-related tests to confirm no regression.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test //projects/monolith:knowledge_models_test //projects/monolith:knowledge_reconciler_test //projects/monolith:knowledge_gap_classifier_test //projects/monolith:<gaps_test_target> --config=ci
```

Expected: all PASS.

**Step 7: Format and commit.**

```bash
cd /tmp/claude-worktrees/gap-classifier-hotfix
format
git add projects/monolith/knowledge/gaps.py projects/monolith/knowledge/<gaps_test_file>
git commit -m "fix(knowledge): fold slug-colliding terms in discover_gaps"
```

---

## Task 3: `write_stub` — update `referenced_by` on existing stubs

**Why:** Task 2 unions referenced_by per slug, but `write_stub` is currently non-destructive — once a stub exists, it never updates. So a stub written on the first cycle from one source note will never pick up a second slug-colliding source note discovered later. We need `write_stub` to update `referenced_by` if it differs, while preserving Claude's classifier edits to other keys.

**Files:**

- Modify: `projects/monolith/knowledge/gap_stubs.py:22-56` (`write_stub`)
- Test: `projects/monolith/knowledge/gap_stubs_test.py`

**Step 1: Write the failing tests.**

Add to `projects/monolith/knowledge/gap_stubs_test.py`:

```python
def test_write_stub_updates_referenced_by_on_existing_stub(tmp_path):
    """write_stub updates referenced_by when the file exists with a stale list."""
    from knowledge.gap_stubs import write_stub
    import yaml

    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a", "src-b"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    stub = (tmp_path / "_researching" / "merkle-tree.md").read_text()
    fm = yaml.safe_load(stub.split("---\n", 2)[1])
    assert fm["referenced_by"] == ["src-a", "src-b"]


def test_write_stub_preserves_classifier_edits(tmp_path):
    """Classifier-edited keys (gap_class, status, classifier_version) survive a referenced_by update."""
    from knowledge.gap_stubs import write_stub
    import yaml

    stub_path = write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    # Simulate a classifier edit.
    text = stub_path.read_text()
    parts = text.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    fm["gap_class"] = "external"
    fm["status"] = "classified"
    fm["classifier_version"] = "opus-4-7@v1"
    fm["classified_at"] = "2026-04-25T01:00:00Z"
    new_fm = yaml.dump(fm, default_flow_style=False, sort_keys=False)
    stub_path.write_text(f"---\n{new_fm}---\n{parts[2]}")

    # Now discover_gaps re-runs and adds a second source note.
    write_stub(
        vault_root=tmp_path,
        note_id="merkle-tree",
        title="merkle-tree",
        referenced_by=["src-a", "src-b"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    fm_after = yaml.safe_load(stub_path.read_text().split("---\n", 2)[1])
    assert fm_after["referenced_by"] == ["src-a", "src-b"], "referenced_by should be updated"
    assert fm_after["gap_class"] == "external", "classifier edits must survive"
    assert fm_after["status"] == "classified"
    assert fm_after["classifier_version"] == "opus-4-7@v1"
    assert fm_after["classified_at"] == "2026-04-25T01:00:00Z"


def test_write_stub_idempotent_when_referenced_by_matches(tmp_path):
    """No write happens when referenced_by already matches — no mtime churn."""
    from knowledge.gap_stubs import write_stub

    stub_path = write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a", "b"],
        discovered_at="2026-04-25T00:00:00Z",
    )
    mtime_before = stub_path.stat().st_mtime_ns

    write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a", "b"],
        discovered_at="2026-04-25T00:00:00Z",
    )
    mtime_after = stub_path.stat().st_mtime_ns

    assert mtime_after == mtime_before, "no-change call must not rewrite the file"
```

**Step 2: Run the tests to verify they fail.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test --config=ci
```

Expected: FAIL — first two assertions fail because `write_stub` short-circuits on existing files; the third passes by accident (also short-circuits).

**Step 3: Update `write_stub`.**

In `projects/monolith/knowledge/gap_stubs.py`, replace the existing function with:

```python
def write_stub(
    *,
    vault_root: Path,
    note_id: str,
    title: str,
    referenced_by: list[str],
    discovered_at: str,
) -> Path:
    """Write a barebones gap stub to _researching/<note_id>.md.

    Three behaviors keyed off file existence:
      * No file: write a fresh stub with all default fields.
      * File exists, ``referenced_by`` already matches: no-op (preserves
        mtime — important for stable reconciler reads).
      * File exists, ``referenced_by`` differs: rewrite ONLY that field;
        all other frontmatter (classifier edits like ``gap_class``,
        ``status``, ``classifier_version``, body content) is preserved.

    Returns the stub path.
    """
    stub_dir = vault_root / RESEARCHING_DIR
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / f"{note_id}.md"

    if not stub.exists():
        fm: dict[str, Any] = {
            "id": note_id,
            "title": title,
            "type": "gap",
            "status": "discovered",
            "gap_class": None,
            "referenced_by": referenced_by,
            "discovered_at": discovered_at,
            "classified_at": None,
            "classifier_version": None,
        }
        fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False)
        stub.write_text(f"---\n{fm_str}---\n\n")
        return stub

    # File exists — only touch referenced_by, preserve everything else.
    text = stub.read_text()
    if not text.startswith("---\n"):
        return stub  # Not a frontmattered stub — leave it alone.
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return stub
    fm = yaml.safe_load(parts[1])
    if not isinstance(fm, dict):
        return stub

    if fm.get("referenced_by") == referenced_by:
        return stub  # No change — skip the write to avoid mtime churn.

    fm["referenced_by"] = referenced_by
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False)
    stub.write_text(f"---\n{fm_str}---\n{parts[2]}")
    return stub
```

**Step 4: Run the tests to verify they pass.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test --config=ci
```

Expected: PASS.

**Step 5: Run discover_gaps tests to confirm Task 2's collision test now also has the union appearing in the stub.**

```bash
bb remote test //projects/monolith:<gaps_test_target> //projects/monolith:knowledge_gap_stubs_test //projects/monolith:knowledge_reconciler_test --config=ci
```

Expected: all PASS.

**Step 6: Format and commit.**

```bash
format
git add projects/monolith/knowledge/gap_stubs.py projects/monolith/knowledge/gap_stubs_test.py
git commit -m "feat(knowledge): write_stub updates referenced_by on existing stubs"
```

---

## Task 4: Stub frontmatter dedup helper + gardener startup hook

**Why:** Bug 2 is partially addressed by Task 6 (prompt update) for _future_ edits, but ~600 stubs in production already have duplicate `status:` keys from Claude's append-not-replace edits. We need a one-shot vault sweep that re-parses each stub's frontmatter (PyYAML's `safe_load` does last-wins on duplicates) and rewrites if any duplicates were collapsed. Idempotent: subsequent runs are no-ops.

The hook fires once at gardener startup so production picks up the fix on the next pod restart. The function is also exposed as a top-level function for future testability / manual replay.

**Files:**

- Modify: `projects/monolith/knowledge/gap_stubs.py` (add `dedupe_stub_frontmatter`)
- Modify: `projects/monolith/knowledge/gardener.py` (call helper on first cycle)
- Test: `projects/monolith/knowledge/gap_stubs_test.py`

**Step 1: Write the failing tests.**

Add to `gap_stubs_test.py`:

```python
def test_dedupe_stub_frontmatter_collapses_duplicate_keys(tmp_path):
    """Stubs with duplicate status keys (from append-not-replace edits) get cleaned."""
    from knowledge.gap_stubs import dedupe_stub_frontmatter
    import yaml

    stub_dir = tmp_path / "_researching"
    stub_dir.mkdir()
    bad_stub = stub_dir / "accelerate.md"
    # Hand-crafted duplicate-key frontmatter — PyYAML's safe_load takes
    # last-wins, so this is parseable but ugly.
    bad_stub.write_text(
        "---\n"
        "id: accelerate\n"
        "title: accelerate\n"
        "type: gap\n"
        "status: discovered\n"
        "gap_class: external\n"
        "referenced_by:\n"
        "- sre-synthesis-pattern\n"
        "discovered_at: '2026-04-24T22:50:23Z'\n"
        "classified_at: '2026-04-24T23:00:00Z'\n"
        "classifier_version: opus-4-7@v1\n"
        "status: classified\n"
        "---\n\n"
    )

    cleaned = dedupe_stub_frontmatter(tmp_path)
    assert cleaned == 1, f"Expected one stub cleaned, got {cleaned}"

    # Round-tripped frontmatter has only one status key, last-wins value.
    fm = yaml.safe_load(bad_stub.read_text().split("---\n", 2)[1])
    assert fm["status"] == "classified"
    text = bad_stub.read_text()
    assert text.count("status:") == 1, f"Expected one status key, got {text.count('status:')}"


def test_dedupe_stub_frontmatter_idempotent(tmp_path):
    """Clean stubs and a second run is a no-op."""
    from knowledge.gap_stubs import dedupe_stub_frontmatter, write_stub

    write_stub(
        vault_root=tmp_path,
        note_id="m",
        title="m",
        referenced_by=["a"],
        discovered_at="2026-04-25T00:00:00Z",
    )

    first = dedupe_stub_frontmatter(tmp_path)
    second = dedupe_stub_frontmatter(tmp_path)
    assert first == 0, "Already-clean stub should not need cleaning"
    assert second == 0


def test_dedupe_stub_frontmatter_handles_missing_dir(tmp_path):
    """No _researching/ directory → no-op (returns 0)."""
    from knowledge.gap_stubs import dedupe_stub_frontmatter

    assert dedupe_stub_frontmatter(tmp_path) == 0
```

**Step 2: Run the tests to verify they fail.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test --config=ci
```

Expected: FAIL — `dedupe_stub_frontmatter` not defined.

**Step 3: Add the helper.**

Add to `projects/monolith/knowledge/gap_stubs.py` after `parse_stub_frontmatter`:

```python
def dedupe_stub_frontmatter(vault_root: Path) -> int:
    """Walk _researching/*.md and rewrite stubs with duplicate frontmatter keys.

    PyYAML's safe_load resolves duplicate top-level keys via last-wins, so
    the parsed dict is canonical. Re-dumping produces a clean single-key
    frontmatter. Skips files where the parsed and re-rendered frontmatter
    are byte-identical (idempotent).

    Returns the number of stubs that were rewritten.
    """
    stub_dir = vault_root / RESEARCHING_DIR
    if not stub_dir.is_dir():
        return 0

    cleaned = 0
    for stub in sorted(stub_dir.glob("*.md")):
        text = stub.read_text()
        if not text.startswith("---\n"):
            continue
        parts = text.split("---\n", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue

        canonical = yaml.dump(fm, default_flow_style=False, sort_keys=False)
        if canonical == parts[1]:
            continue  # already clean

        stub.write_text(f"---\n{canonical}---\n{parts[2]}")
        cleaned += 1
    return cleaned
```

**Step 4: Run the tests to verify they pass.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test --config=ci
```

Expected: PASS.

**Step 5: Wire the helper at gardener startup.**

Find the gardener's startup path. The cleanest hook is the `Gardener.__init__` or the first `run()` call — search for both:

```bash
grep -n 'class Gardener\|def __init__\|def run' /tmp/claude-worktrees/gap-classifier-hotfix/projects/monolith/knowledge/gardener.py | head
```

Add a one-shot guard so it only fires on the first cycle per process. Add to the `Gardener` class:

```python
class Gardener:
    def __init__(self, ...):
        ...
        self._frontmatter_deduped = False  # one-shot per process

    async def run(self) -> GardenStats:
        if not self._frontmatter_deduped:
            try:
                from knowledge.gap_stubs import dedupe_stub_frontmatter
                cleaned = dedupe_stub_frontmatter(self.vault_root)
                if cleaned:
                    logger.info(
                        "knowledge.garden: deduped %d stub frontmatters at startup",
                        cleaned,
                    )
            except Exception:
                logger.exception(
                    "knowledge.garden: stub frontmatter dedup failed (non-fatal)"
                )
            self._frontmatter_deduped = True
        ...
```

Match whatever exception/logging pattern the gardener already uses for similar one-shots (look at `_discover_and_classify_gaps`'s try/except pattern around line 511-518).

**Step 6: Add a gardener startup test.**

In `gardener_test.py` (or a new file if the existing one is too crowded), add a test that exercises the startup path:

```python
def test_gardener_runs_frontmatter_dedup_on_first_cycle(tmp_path, ...):
    """Gardener.run() invokes dedupe_stub_frontmatter on first call only."""
    # Drop a stub with duplicate keys into the vault.
    stub_dir = tmp_path / "_researching"
    stub_dir.mkdir()
    (stub_dir / "x.md").write_text(
        "---\nid: x\nstatus: discovered\nstatus: classified\n---\n"
    )

    gardener = make_gardener(vault_root=tmp_path, ...)  # follow existing test setup
    await gardener.run()

    text = (stub_dir / "x.md").read_text()
    assert text.count("status:") == 1, "first run cleans the stub"

    # Second run is a no-op (idempotent).
    mtime = (stub_dir / "x.md").stat().st_mtime_ns
    await gardener.run()
    assert (stub_dir / "x.md").stat().st_mtime_ns == mtime, "second run does not touch the file"
```

Match the existing gardener_test fixture style — read the surrounding tests to know the right setup.

**Step 7: Run all relevant tests.**

```bash
bb remote test //projects/monolith:knowledge_gap_stubs_test //projects/monolith:knowledge_gardener_test --config=ci
```

Expected: PASS.

**Step 8: Format and commit.**

```bash
format
git add projects/monolith/knowledge/gap_stubs.py \
        projects/monolith/knowledge/gap_stubs_test.py \
        projects/monolith/knowledge/gardener.py \
        projects/monolith/knowledge/gardener_test.py
git commit -m "feat(knowledge): dedupe stub frontmatter at gardener startup"
```

---

## Task 5: Classifier prompt — replace, don't append

**Why:** Claude's `Edit` invocations against existing stubs append new `status:`, `classified_at:` lines without removing the existing `status: discovered` line, producing duplicate keys. The fix is prompt-side: spell out the find-and-replace expectation explicitly, with an example.

**Files:**

- Modify: `projects/monolith/knowledge/gap_classifier.py:34-73` (`_CLASSIFIER_PROMPT`)
- Test: `projects/monolith/knowledge/gap_classifier_test.py`

**Step 1: Write the failing regression test.**

Add to `gap_classifier_test.py`:

```python
def test_classifier_prompt_explicitly_forbids_appending_duplicate_keys():
    """Drift detector: prompt must instruct find-and-replace, not append."""
    from knowledge.gap_classifier import _CLASSIFIER_PROMPT

    # Use phrase tokens, not exact wording — prompt iterations are expected,
    # but the substantive instruction must remain.
    assert "replace" in _CLASSIFIER_PROMPT.lower(), (
        "prompt must mention 'replace' to instruct find-and-replace edits"
    )
    assert "do not add a new" in _CLASSIFIER_PROMPT.lower() or \
           "do not append" in _CLASSIFIER_PROMPT.lower(), (
        "prompt must explicitly forbid appending new keys when one exists"
    )
    # YAML uniqueness justification — keeps the rule explainable to future readers.
    assert "duplicate" in _CLASSIFIER_PROMPT.lower() or \
           "yaml" in _CLASSIFIER_PROMPT.lower(), (
        "prompt should explain WHY (YAML key uniqueness)"
    )
```

**Step 2: Run the test to verify it fails.**

```bash
bb remote test //projects/monolith:knowledge_gap_classifier_test --config=ci
```

Expected: FAIL — current prompt doesn't contain those tokens.

**Step 3: Update the prompt.**

In `gap_classifier.py:60-66`, replace the bullet:

```python
- **Use the Edit tool** to set these fields in each stub's frontmatter:
  - `gap_class: <one of external/internal/hybrid/parked>`
  - `status: classified`
  - `classified_at: <current ISO timestamp in UTC, e.g. 2026-04-25T08:00:00Z>`
  - `classifier_version: {classifier_version}`
```

with:

```python
- **Use the Edit tool** to update these frontmatter fields. The stub's
  frontmatter already contains all four keys with placeholder values
  (`gap_class: null`, `status: discovered`, `classified_at: null`,
  `classifier_version: null`). For each key, find the existing line and
  replace it — do not add a new line. YAML requires unique top-level
  keys; appending a duplicate key produces an ugly stub even when YAML
  parsers tolerate it. Example:
  - find: `status: discovered` → replace with: `status: classified`
  - find: `gap_class: null` → replace with one of: `gap_class: external`
    | `gap_class: internal` | `gap_class: hybrid` | `gap_class: parked`
  - find: `classified_at: null` → replace with the current ISO timestamp
    (UTC, e.g. `classified_at: '2026-04-25T08:00:00Z'`)
  - find: `classifier_version: null` → replace with
    `classifier_version: {classifier_version}`
```

**Step 4: Run the test to verify it passes.**

```bash
bb remote test //projects/monolith:knowledge_gap_classifier_test --config=ci
```

Expected: PASS.

**Step 5: Format and commit.**

```bash
format
git add projects/monolith/knowledge/gap_classifier.py \
        projects/monolith/knowledge/gap_classifier_test.py
git commit -m "fix(knowledge): tighten classifier prompt to forbid duplicate frontmatter keys"
```

---

## Task 6: Drop gardener's legacy `classify_gaps(classifier=None)` call

**Why:** the new scheduled job (`knowledge.classify-gaps`) replaced the gardener-bundled classification. The gardener still calls `gaps.classify_gaps(self.session)` each cycle as a no-op, which logs a misleading `WARNING: 815 gaps awaiting classification but no classifier is wired` — confusing operators into thinking the rollout is broken when it isn't.

Keep `gaps.classify_gaps` defined (it's still imported by tests). Just stop invoking it.

**Files:**

- Modify: `projects/monolith/knowledge/gardener.py:494-518` (`_discover_and_classify_gaps`)
- Modify: `projects/monolith/knowledge/gardener.py:120-130` (`GardenStats` — remove `gaps_classified` field)
- Modify: `projects/monolith/knowledge/gardener.py:315-342` (caller — drop the field from log line)
- Test: `projects/monolith/knowledge/gardener_test.py`

**Step 1: Write the failing test.**

Add to `gardener_test.py`:

```python
def test_gardener_does_not_invoke_classify_gaps(monkeypatch, ...):
    """Legacy classify_gaps stays out of the gardener cycle."""
    import knowledge.gaps as gaps_module

    calls = []
    original = gaps_module.classify_gaps
    def tracker(*args, **kwargs):
        calls.append((args, kwargs))
        return 0
    monkeypatch.setattr(gaps_module, "classify_gaps", tracker)

    gardener = make_gardener(...)  # standard test fixture
    await gardener.run()

    assert calls == [], f"gardener must not call classify_gaps; got {len(calls)} call(s)"


def test_gardener_stats_no_longer_has_gaps_classified():
    """gaps_classified is removed from GardenStats — the scheduled job owns it now."""
    from knowledge.gardener import GardenStats
    assert not hasattr(GardenStats, "gaps_classified"), (
        "gaps_classified should be removed; the knowledge.classify-gaps "
        "job tracks classification via SigNoz logs now."
    )
```

If `GardenStats` is a dataclass, `hasattr` won't behave intuitively for fields with defaults — use `dataclasses.fields(GardenStats)` and assert no field named `gaps_classified` exists.

**Step 2: Run the tests to verify they fail.**

```bash
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

Expected: FAIL.

**Step 3: Update the gardener.**

In `gardener.py`:

1. **Remove `gaps_classified` from `GardenStats`** (line ~124): delete the field.
2. **Refactor `_discover_and_classify_gaps`**: rename to `_discover_gaps_only` (or just inline at the call site), remove the `classify_gaps` call, return only the discovery count:

```python
def _discover_gaps(self) -> int:
    """Discover unresolved wikilinks. Classification is owned by the
    knowledge.classify-gaps scheduled job — see service.py.

    Returns the discovered_count for this cycle.
    """
    try:
        from knowledge.gaps import discover_gaps
        return discover_gaps(self.session, self.vault_root)
    except Exception:
        logger.exception("knowledge.garden: discover_gaps failed (non-fatal)")
        return 0
```

3. **Update the caller** (line ~316): remove the tuple unpack, drop the field from `GardenStats(...)` and the log line / format string.

**Step 4: Run the tests to verify they pass.**

```bash
bb remote test //projects/monolith:knowledge_gardener_test --config=ci
```

Expected: PASS.

**Step 5: Run the full knowledge test suite to catch consumers of `gaps_classified`.**

```bash
bb remote test //projects/monolith/... --config=ci 2>&1 | tee /tmp/test-output.log
grep -E 'FAILED|ERROR' /tmp/test-output.log | head
```

Expected: all PASS. If a coverage / extra test references `gaps_classified`, fix it (likely a stale assertion).

**Step 6: Format and commit.**

```bash
format
git add projects/monolith/knowledge/gardener.py projects/monolith/knowledge/gardener_test.py
# Plus any test files updated for the gaps_classified removal:
git add projects/monolith/knowledge/<other_test_files_if_modified>
git commit -m "refactor(knowledge): drop legacy classify_gaps call from gardener cycle"
```

---

## Task 7: Chart bump + release

**Why:** ArgoCD pulls the monolith chart from OCI by version. Without bumping `Chart.yaml` and `application.yaml`'s `targetRevision` together, ArgoCD will keep deploying `0.53.8` and the hotfix never reaches production.

**Files:**

- Modify: `projects/monolith/chart/Chart.yaml` (version `0.53.8` → `0.53.9`)
- Modify: `projects/monolith/deploy/application.yaml` (targetRevision `0.53.8` → `0.53.9`)
- Modify: `projects/monolith/knowledge/README.md` (add hotfix note if there's a changelog section)

**Step 1: Confirm `0.53.9` is unclaimed.**

```bash
gh pr list --state all --search "0.53.9 chart" --json number,title,state | head -20
```

Expected: no open PR claims `0.53.9`. If one exists, bump to `0.53.10`.

**Step 2: Bump the chart version.**

In `projects/monolith/chart/Chart.yaml:3`, change:

```yaml
version: 0.53.8
```

to:

```yaml
version: 0.53.9
```

**Step 3: Bump the application targetRevision.**

In `projects/monolith/deploy/application.yaml:11` (the OCI source — there are two `targetRevision` lines; only the OCI one bumps; the git `values` source stays `HEAD`), change:

```yaml
targetRevision: 0.53.8
```

to:

```yaml
targetRevision: 0.53.9
```

**Step 4: Verify the chart still renders cleanly.**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml > /tmp/render.yaml
echo "exit=$?"
wc -l /tmp/render.yaml
```

Expected: exit 0, several thousand lines.

**Step 5: Commit.**

```bash
git add projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "chore(monolith): bump chart version to 0.53.9"
```

---

## Final review and ship

After all 7 tasks land:

**Step 1: Inspect the branch shape.**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

Expected: 7 commits (or 8 if a CLAUDE.md / memory update committed alongside), all conventional-commit prefixed, files match each task's scope.

**Step 2: Push the branch and open the PR. CI runs the full test suite on the push.**

Hand off to `superpowers:finishing-a-development-branch` for the push + PR creation flow. After the PR exists, monitor the CI run:

```bash
gh pr checks <pr-number> --watch
# or, for the BuildBuddy invocation directly:
bb view $(gh pr checks <pr-number> --json name,link --jq '.[] | select(.name|test("buildbuddy|test")) | .link' | head -1)
```

**Step 3: Iterate on CI failures by reading the BuildBuddy run output (`bb view <invocation>` / `bb ask`) and pushing fixes.** Don't try to short-circuit with `bb remote test` from your workstation — the pool's darwin runners aren't provisioned and the linux fallback is too flaky for the inner loop.

The PR body must call out:

- Two real bugs found via production rollout of #2194:
  - `MultipleResultsFound` in reconciler from slug collisions (31 stubs/cycle losing classifications).
  - Duplicate `status:` keys in stub frontmatter from Claude's append-not-replace edits.
- Fix scope:
  - `UNIQUE(note_id)` schema invariant + `discover_gaps` slug-keyed loop + `write_stub` `referenced_by` updates.
  - One-shot stub frontmatter dedup at gardener startup + classifier prompt update to forbid append.
  - Drop misleading legacy `classify_gaps` warning from gardener cycle.
- Chart bump `0.53.8` → `0.53.9`.
- Test plan items: monitor reconciler error count, classifier success rate (SigNoz `knowledge.classify-gaps complete`), and stub frontmatter cleanliness post-deploy.

---

## Plan complete

Plan saved to `docs/plans/2026-04-24-gap-classifier-hotfix-plan.md`. **The user has chosen subagent-driven execution** — no choice prompt needed. Proceed directly to `superpowers:subagent-driven-development` to dispatch the first implementer subagent on Task 1.
