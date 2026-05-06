# Knowledge graph server-side layout — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the knowledge graph layout computation from the browser (600-tick d3 force simulation on every page load) to the server (NetworkX `spring_layout` once per gardener cycle, persisted on `knowledge.notes`).

**Architecture:** A pure Python `compute_layout()` function in `projects/monolith/knowledge/layout.py` is called once at the end of every reconcile cycle (post-commit, in its own transaction). Positions are stored as nullable `layout_x` / `layout_y` columns on `knowledge.notes` and shipped in the existing `/api/knowledge/graph` JSON. The frontend strips d3-force entirely and plots positions verbatim, with a random-center fallback for nodes that lack positions (small window between gardener add and next layout).

**Tech Stack:** Python (FastAPI / SQLModel), Postgres, plain SQL migrations under `projects/monolith/chart/migrations/` (Atlas checksums auto-updated by pre-commit hook), Bazel `aspect_rules_py` + pip via `bazel/requirements/all.in`, Svelte 5 frontend, Helm chart at `projects/monolith/chart/`.

**Repo conventions you must follow:**

- **No local test loop.** Per `CLAUDE.md`, do **not** run `bazel test`, `pytest`, `go test`, or `npm test` from a workstation — Mac runners aren't provisioned in BuildBuddy `workflows`. Tests run remotely on push. Each task writes the test _and_ the implementation, then commits. Test execution is deferred to **end-of-plan CI** on the pushed branch (Task 12). `gh pr checks <number> --watch` is the inner loop after that point.
- **Pre-commit hooks run on every commit.** They will auto-format Python (ruff/gofumpt/buildifier), update Bazel BUILD files via gazelle, and update Atlas migration checksums. If a hook fails, fix the underlying issue and create a NEW commit (never `--amend` after a hook failure — the commit didn't happen).
- **Conventional Commits format required.** A `commit-msg` hook enforces it. Use `feat(knowledge):`, `fix(knowledge):`, `refactor(knowledge):`, etc.
- **Code review is one pass at the end of the PR**, not per task. CLAUDE.md is explicit: "do one comprehensive code review per merged PR — not per sub-task."
- **`format` is the standalone command** that updates BUILD files + formats code. Run it before each commit when files were added/moved.
- **Helm rendering can be tested locally:** `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml`. Use this to verify Helm changes — it's a static templating operation, not a test run.

**Source of truth:** The design doc `docs/plans/2026-05-06-kg-server-side-layout-design.md` (already committed on this branch) is the spec. Refer to it whenever a task feels under-specified.

---

## Task 1: Add `networkx` to pip dependencies

**Files:**

- Modify: `bazel/requirements/all.in` (add a line)

**Step 1: Add the dep**

Add `networkx>=3.2` to `bazel/requirements/all.in`. Keep the file alphabetically sorted if it already is (check the existing pattern — preserve it).

**Step 2: Let pre-commit re-lock**

Stage and attempt to commit. The pre-commit "Update Python requirements" hook regenerates `bazel/requirements/all.txt` automatically. If the first commit fails because the lock file changed, stage the new `all.txt` and create a new commit (do not `--amend`).

**Step 3: Self-review**

- [ ] `all.in` has `networkx` on a single line
- [ ] `all.txt` has been updated by the hook (contains `networkx==<version>`)
- [ ] No other deps were touched

**Step 4: Commit**

```bash
git add bazel/requirements/all.in bazel/requirements/all.txt
git commit -m "build(deps): add networkx for server-side knowledge graph layout"
```

---

## Task 2: Pure layout module + unit tests

**Files:**

- Create: `projects/monolith/knowledge/layout.py`
- Create: `projects/monolith/knowledge/layout_test.py`

**Step 1: Write the layout module**

Create `projects/monolith/knowledge/layout.py` with:

```python
"""Server-side force-directed layout for the knowledge graph.

This module is intentionally pure: every public function takes inputs and
returns outputs with no I/O. The reconcile handler and the local preview
script both call ``compute_layout`` with identical ``LayoutParams`` so dev
and prod produce the same result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx

NoteId = str


@dataclass(frozen=True, slots=True)
class NodePos:
    id: NoteId
    prior_x: float | None
    prior_y: float | None


@dataclass(frozen=True, slots=True)
class EdgeRef:
    source: NoteId
    target: NoteId


@dataclass(frozen=True, slots=True)
class LayoutParams:
    link_distance: float = 0.05
    iterations: int = 50
    seed: int = 42
    scale: float = 1.0

    def __post_init__(self) -> None:
        if not (self.link_distance > 0 and math.isfinite(self.link_distance)):
            raise ValueError(f"link_distance must be positive and finite, got {self.link_distance}")
        if self.iterations <= 0:
            raise ValueError(f"iterations must be positive, got {self.iterations}")
        if not (self.scale > 0 and math.isfinite(self.scale)):
            raise ValueError(f"scale must be positive and finite, got {self.scale}")


def compute_layout(
    nodes: list[NodePos],
    edges: list[EdgeRef],
    params: LayoutParams,
) -> dict[NoteId, tuple[float, float]]:
    """Compute (x, y) positions for the graph using NetworkX spring_layout.

    Surviving nodes (those with prior_x/prior_y) seed the algorithm so the
    result evolves smoothly from the previous layout. Newcomers get random
    starting positions chosen by NetworkX; their final positions are
    determined by the iterations.

    Non-finite outputs (NaN/Inf) are filtered out. Caller treats missing
    positions as "use random-center fallback at render time."
    """
    if not nodes:
        return {}

    g = nx.Graph()
    for n in nodes:
        g.add_node(n.id)
    for e in edges:
        if e.source in g and e.target in g:
            g.add_edge(e.source, e.target)

    prior: dict[NoteId, tuple[float, float]] = {
        n.id: (n.prior_x, n.prior_y)
        for n in nodes
        if n.prior_x is not None and n.prior_y is not None
    }

    raw = nx.spring_layout(
        g,
        pos=prior or None,
        iterations=params.iterations,
        k=params.link_distance,
        seed=params.seed,
        scale=params.scale,
    )

    return {
        nid: (float(x), float(y))
        for nid, (x, y) in raw.items()
        if math.isfinite(x) and math.isfinite(y)
    }
```

**Step 2: Write unit tests**

Create `projects/monolith/knowledge/layout_test.py`. The test file mirrors the test cases listed in the design doc's "Testing strategy → Unit" section. Cover, at minimum:

- `test_compute_layout_is_deterministic_with_fixed_seed` — call twice, assert byte-identical output dict.
- `test_compute_layout_preserves_prior_positions_under_no_op_refine` — pass prior positions on a graph with no shape change; surviving nodes' final positions are within `0.1` of the priors (NetworkX in normalized [-1, 1] space).
- `test_compute_layout_places_new_node_finitely` — start with two-node graph + prior positions; add a third node; assert third node has finite (x, y).
- `test_compute_layout_handles_empty_graph` — `compute_layout([], [], params) == {}`.
- `test_compute_layout_handles_single_node` — one node, no edges, returns one finite position.
- `test_compute_layout_handles_disconnected_components` — two cliques with no shared nodes; all nodes positioned, all finite, all coordinates within `[-params.scale, params.scale]`.
- `test_compute_layout_filters_nan_inputs_via_module_contract` — pass a node whose `prior_x` is `float('nan')`; assert the output is finite for that node (NaN priors should be ignored in seed dict — assert the filter is in `compute_layout`, not in the caller).
- `test_compute_layout_param_sensitivity` — same graph, two different `link_distance` values, assert position dicts are not equal (proves the knob does something).
- `test_layout_params_validates_positive_iterations` — `LayoutParams(iterations=0)` raises `ValueError`.
- `test_layout_params_validates_positive_link_distance` — `LayoutParams(link_distance=-1.0)` raises.
- `test_layout_params_validates_finite_link_distance` — `LayoutParams(link_distance=float('inf'))` raises.

For each test, prefer small explicit graphs (3–6 nodes) — easy to reason about, fast.

**Step 3: Self-review**

- [ ] No I/O in `layout.py` (no DB, file, or network calls)
- [ ] All public symbols (`NodePos`, `EdgeRef`, `LayoutParams`, `compute_layout`) have type hints
- [ ] Tests don't depend on each other (no shared state)
- [ ] Determinism test uses the _same_ `seed` value on both calls
- [ ] Stability test asserts a tolerance epsilon, not equality (NetworkX uses float math)
- [ ] At least one test exercises the non-finite filter

**Step 4: Run `format`**

```bash
format
```

This regenerates BUILD files (gazelle should pick up the new module + test) and formats Python.

**Step 5: Commit**

```bash
git add projects/monolith/knowledge/layout.py projects/monolith/knowledge/layout_test.py projects/monolith/knowledge/BUILD
git commit -m "feat(knowledge): add pure compute_layout function with NetworkX"
```

(If `BUILD` doesn't exist as a tracked file in this directory, `format` will create it and the `git add` should pick it up — verify with `git status` before committing.)

---

## Task 3: SQL migration + model update for `layout_x` / `layout_y`

**Files:**

- Create: `projects/monolith/chart/migrations/20260506000000_knowledge_notes_layout_columns.sql`
- Modify: `projects/monolith/knowledge/models.py`
- Modify: `projects/monolith/knowledge/models_test.py`

**Step 1: Write the migration**

Create the SQL file. The schema is `knowledge`; the table is `notes`:

```sql
ALTER TABLE knowledge.notes
    ADD COLUMN layout_x DOUBLE PRECISION,
    ADD COLUMN layout_y DOUBLE PRECISION;
```

Both columns are nullable. No backfill — the next reconcile populates positions; until then, the frontend's random-center fallback handles missing values.

**Step 2: Add fields to `Note`**

In `projects/monolith/knowledge/models.py`, find the `Note` SQLModel class (around line 52 per the explore in the design phase). Add:

```python
layout_x: float | None = None
layout_y: float | None = None
```

Place them after `indexed_at` to match the column order in the migration (purely cosmetic — Postgres doesn't care, but readers do).

**Step 3: Add a model test**

In `projects/monolith/knowledge/models_test.py`, add:

```python
def test_note_model_has_optional_layout_columns():
    note = Note(note_id="n1", path="x.md", title="X", content_hash="h")
    assert note.layout_x is None
    assert note.layout_y is None
    note.layout_x = 0.1
    note.layout_y = -0.2
    assert note.layout_x == 0.1
    assert note.layout_y == -0.2
```

**Step 4: Self-review**

- [ ] Migration filename is `YYYYMMDDhhmmss_<name>.sql` and the timestamp is monotonic relative to existing migrations
- [ ] Both columns are `DOUBLE PRECISION` and nullable
- [ ] `Note` model fields default to `None`, not `0.0`
- [ ] Test asserts the _defaults_ (None), not just presence

**Step 5: Commit**

```bash
git add projects/monolith/chart/migrations/20260506000000_knowledge_notes_layout_columns.sql projects/monolith/knowledge/models.py projects/monolith/knowledge/models_test.py
git commit -m "feat(knowledge): add layout_x/layout_y columns on notes"
```

The "Update Atlas migration checksums" pre-commit hook regenerates checksums; if it modifies a checksums file, stage that and create a new commit. **Do not `--amend` after a hook failure.**

---

## Task 4: Update `KnowledgeStore.graph()` to ship positions and server-side degree

**Files:**

- Modify: `projects/monolith/knowledge/store.py` (the `graph` method, ~lines 335–374 per design doc)
- Modify: `projects/monolith/knowledge/store_test.py` (or add to `store_extra_test.py` if more appropriate by existing pattern)

**Step 1: Add the new behavior to `graph()`**

The current `graph()` returns `{nodes: [{id, title, type}], edges: [...], indexed_at}`. Change it to return `{nodes: [{id, title, type, degree, x, y}], edges: [...], indexed_at}`:

- Extend the SELECT to include `n.layout_x, n.layout_y`.
- Compute `degree` server-side. The cleanest path: a separate `SELECT src_note_fk, COUNT(*) FROM knowledge.note_links GROUP BY src_note_fk`, build a `{note_fk: degree}` dict, then look up each node's degree by its `id` (the SQLModel PK, which `note_fk` references). Avoid a `LEFT JOIN ... GROUP BY n.id` on the main query if SQLModel/SQLAlchemy makes that awkward — two queries that join in Python is fine and easier to read.
- Node payload becomes:

```python
{
    "id": row.note_id,
    "title": row.title,
    "type": row.type,
    "degree": degree_by_pk.get(row.id, 0),
    "x": row.layout_x,
    "y": row.layout_y,
}
```

`x` and `y` are `None` when the layout hasn't run yet — the frontend handles that.

**Step 2: Update tests**

Find the existing test that asserts on the `graph()` response shape (likely in `store_test.py`). Update its assertion to include `degree`, `x`, `y` keys. Add a new test:

```python
def test_graph_response_includes_degree_and_positions(session):
    # Seed 3 notes; add edges note1→note2 and note1→note3.
    # Set layout_x/layout_y on note1 only.
    ...
    result = KnowledgeStore(session).graph()
    by_id = {n["id"]: n for n in result["nodes"]}
    assert by_id["note1"]["degree"] == 2
    assert by_id["note2"]["degree"] == 1
    assert by_id["note1"]["x"] == 0.3
    assert by_id["note2"]["x"] is None
```

**Step 3: Self-review**

- [ ] Every node payload has all six keys (id, title, type, degree, x, y) — even when `x`/`y` are `None`
- [ ] `degree` is computed from the actual `note_links` rows, not hardcoded
- [ ] No `JOIN` in a way that would double-count edges (count distinct edges per node)
- [ ] Test seeds at least one edge and one isolated node to verify both branches

**Step 4: Run `format` and commit**

```bash
format
git add projects/monolith/knowledge/store.py projects/monolith/knowledge/store_test.py
git commit -m "feat(knowledge): include degree and layout positions in graph response"
```

---

## Task 5: Layout config from env + Helm values

**Files:**

- Modify: `projects/monolith/knowledge/layout.py` (add `LayoutParams.from_env()` classmethod)
- Create or modify: `projects/monolith/knowledge/layout_test.py` (add tests for the classmethod)
- Modify: `projects/monolith/chart/values.yaml` (add `knowledge.layout` block)
- Modify: `projects/monolith/chart/templates/deployment.yaml` (or wherever the monolith Deployment env block lives — `grep` for an existing `KNOWLEDGE_*` env var to find the right file)

**Step 1: Extend `LayoutParams`**

Add to `LayoutParams` in `layout.py`:

```python
@classmethod
def from_env(cls, environ: Mapping[str, str] | None = None) -> "LayoutParams":
    env = environ if environ is not None else os.environ
    return cls(
        link_distance=float(env.get("KNOWLEDGE_LAYOUT_LINK_DISTANCE", "0.05")),
        iterations=int(env.get("KNOWLEDGE_LAYOUT_ITERATIONS", "50")),
        seed=int(env.get("KNOWLEDGE_LAYOUT_SEED", "42")),
        scale=float(env.get("KNOWLEDGE_LAYOUT_SCALE", "1.0")),
    )
```

Add the `os` and `typing.Mapping` imports.

The existing `__post_init__` validation already runs on construction, so invalid env values raise on instantiation — which is what we want for fail-fast pod startup.

**Step 2: Test the classmethod**

```python
def test_layout_params_from_env_uses_defaults():
    params = LayoutParams.from_env({})
    assert params.iterations == 50
    assert params.seed == 42

def test_layout_params_from_env_reads_overrides():
    params = LayoutParams.from_env({
        "KNOWLEDGE_LAYOUT_ITERATIONS": "100",
        "KNOWLEDGE_LAYOUT_LINK_DISTANCE": "0.1",
    })
    assert params.iterations == 100
    assert params.link_distance == 0.1

def test_layout_params_from_env_validates_invalid_values():
    with pytest.raises(ValueError):
        LayoutParams.from_env({"KNOWLEDGE_LAYOUT_ITERATIONS": "0"})
```

**Step 3: Add Helm values**

In `projects/monolith/chart/values.yaml`, add at the existing `knowledge:` block (search for an existing `knowledge.something:` to find it; if there isn't one, add the whole block):

```yaml
knowledge:
  layout:
    linkDistance: 0.05
    iterations: 50
    seed: 42
    scale: 1.0
```

In the deployment template (find by `grep -l "KNOWLEDGE_" projects/monolith/chart/templates/`), add four new env vars to the monolith container's `env:` list:

```yaml
- name: KNOWLEDGE_LAYOUT_LINK_DISTANCE
  value: { { .Values.knowledge.layout.linkDistance | quote } }
- name: KNOWLEDGE_LAYOUT_ITERATIONS
  value: { { .Values.knowledge.layout.iterations | quote } }
- name: KNOWLEDGE_LAYOUT_SEED
  value: { { .Values.knowledge.layout.seed | quote } }
- name: KNOWLEDGE_LAYOUT_SCALE
  value: { { .Values.knowledge.layout.scale | quote } }
```

**Step 4: Verify Helm rendering locally**

```bash
helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A1 "KNOWLEDGE_LAYOUT_"
```

Expected: four env entries with the default values (or overrides if `deploy/values.yaml` has any). This is a local templating operation, not a test run — it's allowed.

**Step 5: Bump chart version**

Per `CLAUDE.md`, "When bumping `Chart.yaml` version, ALWAYS also update `targetRevision` in the service's `deploy/application.yaml`. Both files must stay in sync." Bump the patch version in `projects/monolith/chart/Chart.yaml` and the matching `targetRevision` in `projects/monolith/deploy/application.yaml`.

**Step 6: Self-review**

- [ ] `from_env` defaults match the values in `values.yaml` (so absent env still produces a valid `LayoutParams`)
- [ ] All four env vars are quoted in the template (Helm requires it for non-string values)
- [ ] Chart version bumped AND `targetRevision` bumped — the two MUST match
- [ ] `helm template` output looks correct

**Step 7: Run `format` and commit**

```bash
format
git add projects/monolith/knowledge/layout.py projects/monolith/knowledge/layout_test.py projects/monolith/chart/values.yaml projects/monolith/chart/templates/deployment.yaml projects/monolith/chart/Chart.yaml projects/monolith/deploy/application.yaml
git commit -m "feat(knowledge): plumb layout params from Helm values to LayoutParams.from_env"
```

---

## Task 6: Wire `compute_layout` into `reconcile_handler`

**Files:**

- Modify: `projects/monolith/knowledge/service.py` (look for `reconcile_handler` — confirmed present per Task 2 exploration)
- Modify: `projects/monolith/knowledge/service_test.py`

**Step 1: Add the post-commit layout step**

Inside `reconcile_handler`, after the existing upsert transaction commits, add a _separate_ try-wrapped block that opens a fresh transaction and runs the layout. Pseudocode shape:

```python
# ... existing reconcile logic, ending with the upsert transaction commit ...

try:
    _run_layout_pass(session)
except Exception:
    logger.exception("knowledge layout step failed")
    # Increment metric; do not propagate. Reconcile success.
    LAYOUT_FAILURES.inc()
```

`_run_layout_pass(session)` is a new private function in the same module:

```python
def _run_layout_pass(session: Session) -> None:
    params = LayoutParams.from_env()
    rows = session.exec(select(Note.note_id, Note.layout_x, Note.layout_y)).all()
    nodes = [NodePos(id=r.note_id, prior_x=r.layout_x, prior_y=r.layout_y) for r in rows]
    edge_rows = session.exec(
        select(NoteLink.src_note_fk, NoteLink.target_id)
    ).all()
    # Resolve src_note_fk → note_id for the edge_refs (needs a lookup)
    fk_to_note_id = {r.id: r.note_id for r in session.exec(select(Note.id, Note.note_id)).all()}
    edges = [
        EdgeRef(source=fk_to_note_id[r.src_note_fk], target=r.target_id)
        for r in edge_rows
        if r.src_note_fk in fk_to_note_id
    ]
    positions = compute_layout(nodes, edges, params)
    if not positions:
        return
    # Bulk update — chunk if needed, but a few hundred rows is fine in one go.
    with session.begin():
        for note_id, (x, y) in positions.items():
            session.execute(
                update(Note).where(Note.note_id == note_id).values(layout_x=x, layout_y=y)
            )
    logger.info(
        "knowledge layout pass succeeded",
        extra={"node_count": len(nodes), "edge_count": len(edges), "positioned": len(positions)},
    )
```

The exact details of "open a separate transaction" depend on how this codebase manages SQLModel sessions in the scheduler — check the existing `reconcile_handler` for the session pattern and follow it (e.g., if the handler receives a session that's already in a transaction, you may need `session.commit()` first, then start a new `session.begin()` block).

Add a metrics counter `LAYOUT_FAILURES` (using whatever Prometheus / OTel metrics machinery the monolith already uses — `grep` for an existing counter to find the pattern).

**Step 2: Add an integration test**

In `service_test.py`:

```python
def test_reconcile_handler_populates_layout_positions(session):
    # Stage filesystem state with two notes that have wikilinks between them.
    # Run reconcile_handler.
    # Assert each note now has finite layout_x/layout_y.
    ...

def test_reconcile_handler_layout_failure_does_not_roll_back_upserts(session, monkeypatch):
    # Stage one new note in the filesystem.
    # Monkeypatch knowledge.service.compute_layout to raise RuntimeError.
    # Run reconcile_handler.
    # Assert: the new note exists in the DB (upsert committed).
    # Assert: the LAYOUT_FAILURES counter incremented.
    # Assert: reconcile_handler returned successfully (did not raise).
    ...

def test_reconcile_handler_preserves_positions_across_no_op_cycles(session):
    # Run reconcile twice with no filesystem changes.
    # Assert positions on the second run are within ε of the first run.
    ...
```

Use the existing reconcile-test fixtures — there's already `service_test.py` with the harness; mimic the patterns there.

**Step 3: Self-review**

- [ ] Layout step runs _after_ the upsert commit, not inside the same transaction
- [ ] Layout exception is caught at the layout-step boundary; reconcile returns success
- [ ] Counter is incremented in the except branch
- [ ] No `bare except:` — catch `Exception` specifically (so `KeyboardInterrupt`/`SystemExit` propagate)
- [ ] Test for failure-doesn't-rollback uses `monkeypatch`, not patching the import target globally

**Step 4: Run `format` and commit**

```bash
format
git add projects/monolith/knowledge/service.py projects/monolith/knowledge/service_test.py
git commit -m "feat(knowledge): run layout pass at end of every reconcile cycle"
```

---

## Task 7: Strip d3-force from `KnowledgeGraph.svelte`

**Files:**

- Modify: `projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.svelte`

**Step 1: Remove force imports and the simulation**

Remove these imports from the component's `<script>` block:

- `forceSimulation`, `forceLink`, `forceManyBody`, `forceCollide`, `forceCenter`, `forceX`, `forceY` (from d3-force)

Remove:

- The `settling` reactive state
- The `settleLayoutAsync` helper and the chunked tick loop (lines ~559–700 per design doc)
- The `simulation` variable and all references
- The `<div class="settling-overlay">…</div>` block (lines ~846–848)
- Its `.settling-overlay` CSS rules (whatever's tied to it)

**Step 2: Replace with direct render**

Where the simulation used to initialize, replace with:

```javascript
const cx = canvas.width / 2;
const cy = canvas.height / 2;
function jitter() {
  return (Math.random() - 0.5) * 100; // ±50px
}
simNodes = nodes.map((n) => ({
  ...n,
  x: n.x ?? cx + jitter(),
  y: n.y ?? cy + jitter(),
}));
rebuildQuadtree();
render();
```

Where the data-fingerprint reactive effect used to call `simulation.alpha(0.6).restart()` (lines ~783–803), replace with the same logic above (rebuild simNodes from new data, rebuild quadtree, render).

Cluster toggle, search dim, hover, focus-on-select stay exactly as they are — they don't depend on the simulation.

**Step 3: Self-review**

- [ ] No imports from `d3-force` remain in this file
- [ ] No references to `simulation` remain in this file
- [ ] No `settling`-named variables, classes, or DOM elements remain
- [ ] `simNodes[i].x` and `simNodes[i].y` are always defined (either from prop or from fallback) — confirm by reading the code path on mount and on data change
- [ ] Rendering is unchanged for hover, search, cluster toggle, focus-on-select

**Step 4: Quick local sanity check (allowed)**

```bash
cd projects/monolith/frontend
pnpm run check  # or whatever the existing typecheck command is
```

Type check is a static operation, allowed locally per the spirit of CLAUDE.md ("type checking and test suites verify code correctness" — type checks are fine; running tests is the forbidden part).

**Step 5: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.svelte
git commit -m "feat(knowledge): render graph from server-provided positions; drop d3-force"
```

---

## Task 8: Drop client-side degree computation in `+page.svelte`

**Files:**

- Modify: `projects/monolith/frontend/src/routes/private/notes/+page.svelte` (the `nodesWithDegree` derived, ~lines 41–50 per design doc)

**Step 1: Replace the derived**

The current `nodesWithDegree` builds a `Map` of degrees from edges and merges it onto each node. Since `degree` now arrives in the response, replace the whole derived with:

```javascript
const nodesWithDegree = $derived(data.graph.nodes);
```

(Or just rename references downstream and delete the derived entirely if cleaner.)

**Step 2: Verify nothing else used the local degree compute path**

`grep -n 'nodesWithDegree\|deg.set\|degree' projects/monolith/frontend/src/routes/private/notes/` — confirm the only producer was the derived you removed and that no consumer expects a _different_ shape than what the API now ships.

**Step 3: Self-review**

- [ ] The component-level `nodesWithDegree` no longer iterates edges
- [ ] `degree` is consumed from `data.graph.nodes[i].degree`, not recomputed
- [ ] No stale variables (`deg`, intermediate `Map`s) remain

**Step 4: Commit**

```bash
git add projects/monolith/frontend/src/routes/private/notes/+page.svelte
git commit -m "refactor(notes): consume server-supplied degree, drop client compute"
```

---

## Task 9: Frontend tests for the new render path

**Files:**

- Modify or create: `projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.test.js` (mirror existing test naming pattern — confirm with `ls` before creating)

**Step 1: Write tests**

Use whatever test framework the existing frontend tests use (`grep` for `vitest`, `@testing-library/svelte`, or `playwright`). Add:

- `renders nodes at provided positions` — mount with `nodes = [{id, title, x: 100, y: 50, degree: 0}, ...]`; assert internal `simNodes[0].x === 100`, `simNodes[0].y === 50`. (If the component doesn't expose internal state, assert via DOM — e.g., the canvas painted at the right transform — or refactor to expose a small inspection hook for tests.)
- `falls back to canvas-center jitter when positions are missing` — mount with `nodes = [{id, title, x: undefined, y: undefined, degree: 0}]`; assert `simNodes[0].x` is finite and within `[cx - 50, cx + 50]`.
- `does not render the loading overlay` — mount the component; assert `container.querySelector('.settling-overlay')` is `null` regardless of node state.

**Step 2: Self-review**

- [ ] Tests don't rely on `setTimeout` / wall-clock waits (the simulation is gone — there's nothing async to wait for)
- [ ] At least one test asserts the _absence_ of `.settling-overlay`, locking in the design choice

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.test.js
git commit -m "test(notes): cover position rendering and fallback in KnowledgeGraph"
```

---

## Task 10: `preview-layout.py` script

**Files:**

- Create: `projects/monolith/scripts/preview-layout.py`
- Create: `projects/monolith/scripts/preview_layout_test.py`

**Step 1: Write the script**

```python
"""Standalone layout preview tool.

Usage:
    python preview-layout.py --snapshot graph.json \\
        --link-distance 0.05 --iterations 50 --seed 42 --scale 1.0 \\
        --out preview.html

`graph.json` is a snapshot of the /api/knowledge/graph response (or
equivalent shape: {"nodes": [...], "edges": [...]}). `preview.html` is a
self-contained file you open in a browser to visualize the layout. No
force simulation runs in the browser — positions are baked in.

Once you find params you like, copy them into projects/monolith/deploy/values.yaml
and trigger `homelab scheduler jobs run-now knowledge.reconcile`.
"""

import argparse
import html
import json
import sys
from pathlib import Path

from monolith.knowledge.layout import EdgeRef, LayoutParams, NodePos, compute_layout


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--link-distance", type=float, default=0.05)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=Path("preview.html"))
    args = parser.parse_args(argv)

    payload = json.loads(args.snapshot.read_text())
    nodes = [
        NodePos(
            id=n["id"],
            prior_x=n.get("x"),
            prior_y=n.get("y"),
        )
        for n in payload["nodes"]
    ]
    edges = [EdgeRef(source=e["source"], target=e["target"]) for e in payload["edges"]]
    params = LayoutParams(
        link_distance=args.link_distance,
        iterations=args.iterations,
        seed=args.seed,
        scale=args.scale,
    )
    positions = compute_layout(nodes, edges, params)
    args.out.write_text(_render_html(payload, positions, params))
    print(f"Wrote {args.out} ({len(positions)} positioned of {len(nodes)} nodes)")
    return 0


def _render_html(payload, positions, params) -> str:
    nodes_with_pos = [
        {**n, "x": positions.get(n["id"], (0.0, 0.0))[0], "y": positions.get(n["id"], (0.0, 0.0))[1]}
        for n in payload["nodes"]
    ]
    data = json.dumps({"nodes": nodes_with_pos, "edges": payload["edges"]})
    title = html.escape(f"layout preview (k={params.link_distance}, iter={params.iterations})")
    # Minimal SVG plot. Positions are in [-scale, scale]; map to a 1200x800 viewport.
    return f"""<!doctype html>
<html><head><title>{title}</title></head><body>
<h1>{title}</h1>
<svg width="1200" height="800" viewBox="-{params.scale} -{params.scale} {2 * params.scale} {2 * params.scale}" preserveAspectRatio="xMidYMid meet" style="background:#111">
<g id="g"></g>
</svg>
<script>
const data = {data};
const g = document.getElementById('g');
const ns = "http://www.w3.org/2000/svg";
const byId = new Map(data.nodes.map(n => [n.id, n]));
for (const e of data.edges) {{
  const a = byId.get(e.source), b = byId.get(e.target);
  if (!a || !b) continue;
  const line = document.createElementNS(ns, 'line');
  line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
  line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
  line.setAttribute('stroke', '#666'); line.setAttribute('stroke-width', '0.005');
  g.appendChild(line);
}}
for (const n of data.nodes) {{
  const c = document.createElementNS(ns, 'circle');
  c.setAttribute('cx', n.x); c.setAttribute('cy', n.y);
  c.setAttribute('r', '0.015'); c.setAttribute('fill', '#4af');
  g.appendChild(c);
}}
</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

**Step 2: Write a smoke test**

```python
def test_preview_layout_writes_html_with_circles(tmp_path):
    snap = tmp_path / "graph.json"
    snap.write_text(json.dumps({
        "nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
        "edges": [{"source": "a", "target": "b"}],
    }))
    out = tmp_path / "preview.html"
    rc = main(["--snapshot", str(snap), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    body = out.read_text()
    assert "<svg" in body
    assert body.count("<circle") == 2
    assert "<line" in body
```

**Step 3: Self-review**

- [ ] Script accepts `--snapshot` JSON and writes a single self-contained HTML file
- [ ] HTML works offline (no external script tags / CDN URLs)
- [ ] Script imports `compute_layout` from the same module the runtime uses (no duplicate copy)
- [ ] Output filename, path, and node/edge counts are printed for the user

**Step 4: Run `format` and commit**

```bash
format
git add projects/monolith/scripts/preview-layout.py projects/monolith/scripts/preview_layout_test.py
git commit -m "feat(knowledge): add local preview-layout.py for parameter iteration"
```

---

## Task 11: ~~`homelab scheduler jobs run-now knowledge.reconcile` CLI + endpoint~~ — SKIPPED

**Status:** Skipped after discovering the existing scheduler infrastructure already covers this need.

The plan originally proposed adding a new `/internal/knowledge/recompute-layout` endpoint plus a `homelab scheduler jobs run-now knowledge.reconcile` CLI subcommand. While building Task 11, we found:

- `projects/monolith/scheduler/router.py` already exposes `POST /api/scheduler/jobs/{name}/run-now` — marks a registered job for immediate execution on the next scheduler tick.
- `tools/cli/scheduler_cmd.py` already exposes `homelab scheduler jobs run-now <name>`.

After Task 6, the layout pass runs as the last step of `knowledge.reconcile`. So the manual trigger path is:

```bash
homelab scheduler jobs run-now knowledge.reconcile
```

A no-op reconcile (no filesystem changes) is sub-second; the layout pass at the end is a few hundred ms on a homelab graph. A separate "layout-only" path was discarded as YAGNI: invisible latency benefit, redundant code surface, no clear use case beyond what `run-now` already covers.

If a layout-only path becomes useful later (e.g., the graph grows large enough that the reconcile no-op is noticeable), revisit this as a follow-up. For now: nothing to build.

---

## Task 12: Push, watch CI, iterate to green

**Step 1: Push the branch**

```bash
git push -u origin worktree-kg-server-side-layout
```

(If you renamed the branch to `feat/kg-server-side-layout`, push that instead.)

**Step 2: Open the PR**

```bash
gh pr create --title "feat(knowledge): server-side graph layout precomputation" --body "$(cat <<'EOF'
## Summary
- Compute knowledge graph node positions on the server in NetworkX once per gardener reconcile cycle, persist on `knowledge.notes`, and ship them in the `/api/knowledge/graph` JSON.
- Strip the client-side d3-force simulation; render directly from server-supplied positions. The "LOADING KNOWLEDGE GRAPH" overlay is gone.
- Layout parameters live in Helm values; iterate locally with `projects/monolith/scripts/preview-layout.py`, force a pass without waiting for the scheduler with `homelab scheduler jobs run-now knowledge.reconcile`.

Design: docs/plans/2026-05-06-kg-server-side-layout-design.md
Plan: docs/plans/2026-05-06-kg-server-side-layout-plan.md

## Test plan
- [ ] CI green on push (BuildBuddy runs all unit + integration tests)
- [ ] Manual: deploy to dev, confirm graph page loads with no overlay and immediate positioned graph
- [ ] Manual: search/cluster/hover/focus all behave identically to before
- [ ] Manual: `homelab scheduler jobs run-now knowledge.reconcile` runs successfully against dev cluster
- [ ] Manual: `python projects/monolith/scripts/preview-layout.py --snapshot <real-graph.json>` opens a sane preview.html

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Watch CI**

```bash
gh pr checks <number> --watch
```

**Step 4: Iterate on failures**

When a check fails, fetch the actual log via the BuildBuddy MCP tools (per CLAUDE.md):

```
mcp__buildbuddy__get_invocation (commitSha selector)
  → mcp__buildbuddy__get_target (find failing target)
    → mcp__buildbuddy__get_log (read trace)
```

**Quote the actual assertion error verbatim before hypothesizing.** CLAUDE.md is explicit: do not blame infrastructure ("BuildBuddy flake", "RBE hiccup") until a real failure has been ruled out — Claude has hallucinated infra failures here before.

Common failure modes to expect:

- **Migration order/checksum mismatch** — re-run the migration-checksum hook (it auto-fixes)
- **Gazelle/BUILD changes not staged** — re-run `format` and stage all changes
- **Frontend type errors** — fix locally with `pnpm check`
- **Test asserts on the _old_ JSON shape somewhere we missed** — `grep` for `degree` and `'x'` and `'y'` in test files
- **`networkx` missing in a sub-target** — gazelle should add the dep; if not, add it manually to the BUILD file's `deps`

Fix, commit (a NEW commit, not `--amend`), push, watch again. Repeat until green.

---

## Task 13: Manual visual verification on the dev cluster

**Step 1: Confirm the new image deployed**

```bash
# Watch ArgoCD sync the monolith app after merge to a dev branch (or sync to dev manually).
# Use the argocd-mcp-* tools or `kubectl get app monolith -n argocd -w` if MCP isn't loaded.
```

**Step 2: Visit the graph page**

Open `/private/notes` in the dev cluster's domain. Confirm:

- **No "LOADING KNOWLEDGE GRAPH" overlay.**
- Graph appears positioned within ~100ms of the page rendering.
- Search box dims non-matching nodes — same behavior as before.
- Cluster toggle chips show/hide nodes — same.
- Hover highlights, click-to-focus, pan/zoom — same.

If the visual is meaningfully worse than today, iterate on params via `preview-layout.py` against a fresh snapshot, copy the winning values into `projects/monolith/deploy/values.yaml`, push, and run `homelab scheduler jobs run-now knowledge.reconcile` to apply without waiting.

**Step 3: Take before/after screenshots**

You already have `topology-groups-*.png` files in the working tree from prior iteration — keep the convention. Capture before/after at the same zoom and selection state.

**Step 4: If something's off and the dev cluster doesn't allow you to debug it interactively, say so explicitly.** Per CLAUDE.md: "if you can't test the UI, say so explicitly rather than claiming success."

---

## Task 14: End-of-PR comprehensive code review

**Per CLAUDE.md: one comprehensive code review per merged PR, not per sub-task.**

Use the `pr-review-toolkit:review-pr` slash command (or invoke `pr-review-toolkit:code-reviewer` directly via the Agent tool):

```
/review <PR-number>
```

Address review feedback in NEW commits on the same branch. Push, re-run `gh pr checks --watch`, repeat until clean.

---

## Task 15: Merge

**Step 1: Confirm CI green and review approved.**

```bash
gh pr view <number> --json state,mergeStateStatus,statusCheckRollup
```

**Step 2: Merge with rebase (the only allowed method per CLAUDE.md):**

```bash
gh pr merge <number> --rebase
```

**Step 3: Watch the rollout:**

ArgoCD picks up the merged commit, builds the new monolith image, runs the migration on pod startup, and starts the new pod. Watch via the argocd-mcp-\* tools or `kubectl rollout status deployment/monolith -n monolith`.

**Step 4: Confirm production:**

- Visit the prod graph page. Confirm no overlay, immediate positioned graph.
- Check SigNoz for any `layout_failures_total` increments. Should be zero.
- Check the `layout_compute_seconds` histogram for sane values (sub-second on a graph this size).

**Done.** Followups (component centering, per-edge-type strength, alert config) live in the design doc's "Followups" section — out of scope for this PR.

---

## Out-of-scope reminders

These are listed in the design doc as explicit non-goals. **Do not** silently expand scope in this PR:

- Component-centering post-process (only if disconnected groups visibly drift after merge)
- Per-edge-type layout strength variation
- SigNoz alert on `layout_failures_total > 0` (add only after baseline noise is observed)
- Audit table for layout history
- Eliminating client-side d3 entirely (zoom/quadtree stay)
