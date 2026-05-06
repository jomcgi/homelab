# Knowledge graph: server-side layout precomputation

Date: 2026-05-06
Status: Approved (brainstorming complete)

## Problem

The knowledge graph at `/private/notes` shows a "LOADING KNOWLEDGE GRAPH" overlay
for ~1–2 seconds on every page load. The data layer is already CDN-cacheable
(`/api/knowledge/graph` ships with `s-maxage=3600, stale-while-revalidate=86400`,
plus ETag/Last-Modified). The latency is _not_ in the network fetch — it is in
the d3-force simulation that runs 600 pre-ticks client-side at every mount,
seeded with all nodes at `(0, 0)`. See `KnowledgeGraph.svelte:559–700`.

This design moves layout computation from "client onMount, every visit" to
"server, once per gardener cycle." Positions ship in the JSON; the frontend
plots them and never runs a force simulation.

## Goals

- Eliminate the layout-settle delay (and the loading badge) on page load.
- Keep the visual character of the current graph (Fruchterman–Reingold family,
  hub-and-spoke arrangement, recognisable cluster shape).
- Keep all existing interactivity bit-for-bit: search dim, cluster toggle,
  hover, focus-on-select, pan/zoom. None of those depend on a live simulation
  today (see `KnowledgeGraph.svelte:819–824`); they are render-time masks.
- Make layout parameters tunable without redeploying the monolith image, via
  Helm `values.yaml`.
- Provide a local preview script so layout-parameter iteration runs at
  terminal speed, not deploy speed.

## Non-goals

- Eliminating client-side d3 entirely. Render code (canvas paint, quadtree
  hit-testing, zoom transforms) stays on the client. Only the _force
  simulation_ goes away.
- Pixel-equivalent reproduction of the current d3 layout. We accept that
  NetworkX `spring_layout` will produce a visually-similar-but-not-identical
  arrangement.
- Historical layout snapshots. We persist only the current layout.
- Per-user layouts. Positions are global, identical for every viewer.

## Design decisions (locked)

| Dimension              | Decision                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------- |
| Layout language        | Python force-directed (NetworkX `spring_layout`)                                                               |
| Cadence                | At end of every reconcile cycle, post-commit                                                                   |
| Stability              | Soft: seed prior positions, run 50–100 refine iterations                                                       |
| Frontend behavior      | Pure render — strip d3-force, plot positions verbatim                                                          |
| Storage                | `layout_x`, `layout_y` columns on `knowledge.notes`                                                            |
| Tunability (params)    | Helm `values.yaml` → env → `LayoutParams.from_env()`                                                           |
| Tunability (iteration) | Local `preview-layout.py` script + `homelab scheduler jobs run-now knowledge.reconcile` to skip the 5-min wait |
| Orphan handling        | None initially — iterate on standard params; revisit only if visually wrong                                    |

## Architecture

A single new module — `projects/monolith/knowledge/layout.py` — exposes one pure
function:

```python
def compute_layout(
    nodes: list[NodePos],     # id, prior_x | None, prior_y | None
    edges: list[EdgeRef],     # source, target
    params: LayoutParams,     # link_distance, charge, iterations, seed, ...
) -> dict[NoteId, tuple[float, float]]:
    ...
```

Internally builds a `networkx.Graph`, calls `spring_layout(G, pos=prior_pos,
iterations=params.iterations, k=params.link_distance, seed=params.seed,
scale=1.0)`, returns a dict of finite (x, y) per node.

This function is **pure** (no I/O, deterministic given a seed). Both the
runtime hook in `reconcile_handler` and the local `preview_layout.py` script
call it identically with the same `LayoutParams` dataclass — there is no code
path where layout differs between dev and prod.

### Wiring into the runtime

After `reconcile_handler` finishes its upserts and **commits** them, a
_separate_ transaction runs the layout step:

```
Postgres scheduler tick
  └─ knowledge.reconcile_handler  (service.py)
      ├─ scan _processed/ for new/changed .md files
      ├─ for each file: KnowledgeStore.upsert_note(...)
      ├─ for each file: rebuild note_links
      ├─ COMMIT  ← upserts land first
      └─ NEW: layout step (separate transaction)
          ├─ rows = SELECT note_id, layout_x, layout_y FROM notes
          ├─ edges = SELECT source_id, target_id FROM note_links
          ├─ params = LayoutParams.from_env()
          ├─ positions = compute_layout(rows, edges, params)
          ├─ batch UPDATE notes SET layout_x=?, layout_y=? WHERE note_id=?
          └─ COMMIT
```

The split is load-bearing: layout failure must not roll back upserts, or a
persistent layout bug would block all gardener writes.

## Components

### Backend — new files

1. **`projects/monolith/knowledge/layout.py`** — pure layout function and
   `LayoutParams` dataclass.
2. **`projects/monolith/scripts/preview_layout.py`** — CLI tool. Loads a graph
   JSON snapshot (downloaded from `/api/knowledge/graph` or pulled via
   `psql`), accepts params via flags, runs `compute_layout`, writes a
   self-contained `preview.html` with d3 plotting positions in plain SVG (no
   force sim). Used to iterate on params; once a winner is found, copy values
   into `deploy/values.yaml`.

### Backend — changed files

3. **`projects/monolith/knowledge/models.py`** — add nullable
   `layout_x: float | None`, `layout_y: float | None` to `Note`.
4. **Alembic migration** — `ADD COLUMN layout_x DOUBLE PRECISION, ADD COLUMN
layout_y DOUBLE PRECISION` on `knowledge.notes`. Both nullable; backfill
   not needed (next reconcile populates).
5. **`projects/monolith/knowledge/store.py`** — modify `KnowledgeStore.graph()`
   (lines 335–374):
   - Add `layout_x, layout_y` to the SELECT.
   - Compute `degree` via `LEFT JOIN note_links … GROUP BY n.id`.
   - Response payload becomes
     `{nodes: [{id, title, type, degree, x, y}, ...], edges: [...], indexed_at}`.
6. **`projects/monolith/knowledge/service.py`** — `reconcile_handler` gains a
   post-commit layout step. Wrapped in a top-level `try/except` that logs and
   increments `layout_failures_total` rather than propagating.
7. **`projects/monolith/config.py`** (or wherever monolith env config lives) —
   read layout knobs from env, default to known-good values, validate at
   construction (positive iterations, finite floats). Invalid config fails
   pod startup — no silent fallback.
8. **`requirements.txt` + relevant `BUILD.bazel`** — add `networkx` to pip
   deps and the monolith `py_library`. Run `format` to update generated
   files.
9. **No new CLI subcommand needed.** The existing
   `homelab scheduler jobs run-now knowledge.reconcile` already triggers
   the reconcile job on the next scheduler tick, and (post this design)
   the layout pass runs as the last step of every reconcile. The escape
   hatch for "I edited values, don't want to wait 5 minutes" is just
   that command.

### Helm

10. **`projects/monolith/chart/values.yaml`** — new block:

    ```yaml
    knowledge:
      layout:
        linkDistance: 0.05 # NetworkX `k` (optimal distance, normalized)
        iterations: 50
        seed: 42
        scale: 1.0
    ```

11. **`projects/monolith/chart/templates/deployment.yaml`** — plumb the
    values through as env vars to the monolith pod.

12. **`projects/monolith/deploy/values.yaml`** — empty override block ready
    for prod tuning once the preview script identifies winning values.

### Frontend

13. **`projects/monolith/frontend/src/lib/components/notes/KnowledgeGraph.svelte`**
    — substantial simplification: - Remove imports: `forceSimulation`, `forceLink`, `forceManyBody`,
    `forceCollide`, `forceCenter`, `forceX`, `forceY`. - Remove `settling` state, `settleLayoutAsync`, the 600-tick chunk loop. - Remove `<div class="settling-overlay">` (lines 846–848 today). - Remove the `simulation.alpha(0.6).restart()` re-heating effect
    (lines 783–803). Replace with a plain `simNodes = …; rebuildQuadtree(); render()`. - On mount: `simNodes = nodes.map(n => ({...n, x: n.x ?? cx + jitter(),
y: n.y ?? cy + jitter()}))`. The fallback handles the brief window
    where a new node arrived but layout hasn't run yet. - Render loop, hover, search-dim, cluster-toggle, focus-on-select all
    stay as-is — they were already render-only.

14. **`projects/monolith/frontend/src/routes/private/notes/+page.svelte`** —
    strip the client-side degree computation (lines 41–50). `degree` is now
    a server-supplied field on each node.

### Tests

15–17 — see "Testing strategy" section below.

## Data flow

### Path 1: Reconcile (every 5 minutes)

```
Postgres scheduler
  └─ reconcile_handler
      ├─ upsert notes from filesystem changes  (transaction T1, COMMIT)
      └─ layout step                           (transaction T2, COMMIT)
          ├─ load (note_id, layout_x, layout_y) for all notes
          ├─ load all edges from note_links
          ├─ compute_layout(...)
          ├─ filter non-finite outputs
          └─ batch UPDATE positions
```

Errors in T2 do not affect T1. New nodes from T1 with a failed T2 carry NULL
positions, handled by the frontend fallback.

### Path 2: Serve `/api/knowledge/graph`

```
Browser → GET /api/knowledge/graph
  └─ KnowledgeStore.graph()
      ├─ SELECT n.note_id, n.title, n.type, n.layout_x, n.layout_y,
      │         COUNT(l.id) AS degree
      │  FROM notes n LEFT JOIN note_links l ON l.src_note_fk = n.id
      │  GROUP BY n.id
      ├─ SELECT source, target, kind, edge_type FROM resolved_edges
      └─ return JSON

Browser receives JSON
  └─ KnowledgeGraph.svelte
      ├─ simNodes = nodes.map(n => ({...n, x: n.x ?? cx, y: n.y ?? cy}))
      ├─ rebuildQuadtree()
      ├─ render()
      └─ DONE  (no settle, no overlay, no 600 ticks)
```

Existing CDN caching headers keep working unchanged: `indexed_at` invalidates
the ETag exactly when the gardener mutates anything, which is exactly when
positions change.

### Path 3: Tuning loop

```
$ python scripts/preview_layout.py \
    --snapshot graph.json \
    --link-distance 0.06 \
    --iterations 80 \
    --out preview.html

   ├─ loads graph.json
   ├─ compute_layout(...)
   └─ writes preview.html (open in browser)
```

Iterate, find winning params, edit `deploy/values.yaml`, push, ArgoCD syncs,
optionally `homelab scheduler jobs run-now knowledge.reconcile` to skip the 5-minute wait.

### Path 4: Manual recompute

```
$ homelab scheduler jobs run-now knowledge.reconcile
  └─ POST /api/scheduler/jobs/knowledge.reconcile/run-now
      └─ marks the job for immediate run; on the next scheduler tick the
         existing reconcile_handler runs (vault walk + upsert + layout pass).
```

We rejected adding a layout-only endpoint: the existing scheduler
`run-now` already triggers reconcile (which now ends with a layout
pass), and a no-op vault walk is sub-second. A separate "layout-only"
path was discarded as YAGNI for a homelab graph this size.

## Error handling

1. **`compute_layout` raises** — caught at the layout-step boundary. Upserts
   are already committed (separate transaction). Log structured error,
   increment `layout_failures_total`, return. Reconcile success.

2. **New node, no position** — frontend falls back to `cx + jitter, cy +
jitter`. Self-heals on next successful layout pass. Acceptable for at
   most one cycle.

3. **Disconnected components** — `spring_layout(scale=1.0)` keeps positions
   in `[-1, 1]` and centers the bounding box. If components drift unpleasantly
   in practice, post-process step (translate each component's centroid toward
   origin) is a 5-line addition. Not shipped initially.

4. **Non-finite outputs** — filter before persisting:
   `{nid: (x, y) for nid, (x, y) in raw.items() if math.isfinite(x) and math.isfinite(y)}`.
   Skipped nodes get NULL positions; frontend fallback handles them. Log the
   skipped count.

5. **Invalid config from `values.yaml`** — `LayoutParams.from_env()` validates
   at construction; failure crashes pod startup so ArgoCD surfaces a
   `CrashLoopBackOff`. No silent default-fallback.

6. **Schema rollout** — Alembic migration runs on monolith pod startup
   (existing pattern). During the rollout window, old pods serve old JSON
   shape; new pods serve with positions (or NULLs until first reconcile).
   Frontend handles either case via the random-center fallback.

7. **Concurrent reconciles** — existing scheduler lock leases
   (`ttl_secs=1200`) prevent overlap. Since manual recompute uses the same
   `scheduler/run-now` mechanism (just marks the existing reconcile job
   for immediate run), it's covered by the same lock.

8. **Observability** — every layout pass emits one structured log line and
   metrics:
   - `layout_compute_seconds` (histogram)
   - `layout_nodes_count`
   - `layout_edges_count`
   - `layout_skipped_nonfinite` (counter — should always be 0)
   - `layout_failures_total` (counter — alert if > 0)

## Testing strategy

Per `CLAUDE.md`, no local test loop — tests run on BuildBuddy CI on push.
Strategy: write tests up-front in the same PR; iterate via `gh pr checks`.

### Unit (pure function) — `projects/monolith/knowledge/layout_test.py`

- **Determinism** — same `(nodes, edges, params)` with fixed seed → byte-identical output.
- **Stability** — given prior positions, surviving nodes move by < ε after a 50-iteration refine.
- **New node placement** — adding one node leaves existing nodes nearly unchanged; new node lands somewhere finite.
- **Empty graph** — returns `{}`.
- **Single-node graph** — returns one finite position.
- **Disconnected components** — both finite, both within `scale=1.0`.
- **Non-finite filtering** — degenerate inputs produce no NaN/Inf in persisted output.
- **Param sensitivity** — different `link_distance` values produce visibly different positions on a known small graph.

### Integration — `projects/monolith/knowledge/service_test.py`

- **Reconcile populates positions** — null → non-null after one cycle.
- **Reconcile preserves positions across no-op cycles** — second-cycle positions within ε of first-cycle positions.
- **Layout failure does not roll back upserts** — monkeypatch `compute_layout` to raise; upserts still commit; `layout_failures_total` increments.
- **Concurrent runs blocked** — manual recompute and scheduled reconcile do not overlap.

### API — `projects/monolith/knowledge/store_test.py`

- **Graph response shape** — fixture-driven; nodes have `x`, `y`, `degree`; edges unchanged.

### Frontend

- **Renders with provided positions** — no simulation runs; no `settling-overlay` element.
- **Random-center fallback** — undefined positions → finite, in-viewport positions.

### Preview script — `scripts/preview_layout_test.py`

- **Generates plottable HTML** — output parses, contains `<svg>` with `<circle>` elements at computed positions.

### Visual / manual verification

Per `CLAUDE.md`, frontend changes require browser verification:

- Run dev server, confirm no loading badge, graph appears immediately positioned, search/cluster/hover work as before.
- Capture before/after screenshots.
- If dev server cannot be run against representative data, defer visual check to dev cluster and say so explicitly rather than claiming success.

## Followups (out of scope for this PR)

- Component-centering post-process if disconnected groups drift visibly.
- Per-edge-type layout strength variation (e.g., stronger pulls along
  `edge_type=parent`). Probably the right next step if visual feels generic.
- Alert on `layout_failures_total > 0` in SigNoz once we have baseline noise data.
- Audit table for layout history (debug "why did the graph hop") if it ever
  becomes a real diagnostic need.
