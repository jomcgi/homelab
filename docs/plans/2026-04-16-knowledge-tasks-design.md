# Knowledge Graph Task Tracking

**Date:** 2026-04-16
**Status:** Design
**Replaces:** Home module (`/api/home`) — simple daily/weekly task lists with no knowledge graph integration

## Problem

Task tracking is split across two disconnected systems:

1. The Home module — ephemeral daily/weekly checklists with no links, no history, no search
2. Obsidian `active` type notes — rich context and edges but not queryable as tasks

Neither system is good enough on its own. The Home module has no context; active notes have no structured task fields.

## Solution

Promote `active` notes into first-class tasks within the knowledge graph. Tasks are notes with structured frontmatter, queryable via API and CLI, with gardener-powered decomposition, completion distillation, and daily/weekly consolidation.

## Design

### 1. Task Note Frontmatter Contract

Every task is a single note. One task, one note. Split multi-step work into separate linked notes.

```yaml
---
id: deploy-voyage-4-node-4
title: Deploy voyage-4 embedding model on node-4
type: active
tags: [gpu, embedding, infrastructure]
status: active # active | someday | blocked | done | cancelled
task-completed: null # ISO date when done/cancelled, null otherwise
due: null # optional ISO date deadline
size: medium # small | medium | large | unknown (gardener-estimated)
blocked-by: [] # list of note IDs
edges:
  derives_from: [voyage-4-embedding-research]
  related: [gemma-4-gpu-deployment]
---
Context, notes, links — whatever you want. Body is for humans, not the system.
```

**Field reference:**

| Field            | Type             | Required | Purpose                                                                          |
| ---------------- | ---------------- | -------- | -------------------------------------------------------------------------------- |
| `status`         | enum             | Yes      | `active` (committed), `someday` (uncommitted), `blocked`, `done`, `cancelled`    |
| `task-completed` | ISO date / null  | No       | Set when status → done or cancelled. Auto-set to today if omitted on transition. |
| `due`            | ISO date / null  | No       | Deadline. Used for daily/weekly rollup bucketing.                                |
| `size`           | enum             | No       | `small`, `medium`, `large`, `unknown`. Gardener-estimated, manually reviewable.  |
| `blocked-by`     | list of note IDs | No       | Creates queryable dependency edges. Gardener checks resolution.                  |

**Status semantics:**

- `active` — committed, working on it
- `someday` — on the radar, not committed. May be promoted or cancelled.
- `blocked` — committed but stuck on a dependency
- `done` — completed. Triggers distillation.
- `cancelled` — decided not to proceed. No distillation. Records the decision.

### 2. Monolith API

New endpoints under `/api/knowledge/tasks`. No new database tables — tasks are notes where `type = 'active'` with task fields in the `extra` JSONB column.

#### Endpoints

| Method  | Path                             | Purpose                                                |
| ------- | -------------------------------- | ------------------------------------------------------ |
| `GET`   | `/api/knowledge/tasks`           | List/filter tasks. Supports semantic search via `?q=`. |
| `GET`   | `/api/knowledge/tasks/daily`     | Today's consolidated task list (due today + overdue)   |
| `GET`   | `/api/knowledge/tasks/weekly`    | This week's consolidated task list                     |
| `PATCH` | `/api/knowledge/tasks/{note_id}` | Update any task fields                                 |

#### Query parameters for `GET /tasks`

| Param             | Example          | Purpose                                               |
| ----------------- | ---------------- | ----------------------------------------------------- |
| `q`               | `gpu deployment` | Semantic search (pgvector similarity) scoped to tasks |
| `status`          | `active,blocked` | Comma-separated status filter                         |
| `due_before`      | `2026-04-30`     | Deadline upper bound                                  |
| `due_after`       | `2026-04-16`     | Deadline lower bound                                  |
| `size`            | `unknown`        | Filter by size (useful for review)                    |
| `include_someday` | `false`          | Exclude someday tasks (default: false)                |

#### PATCH body

```json
{
  "status": "blocked",
  "blocked-by": ["discord-image-storage-pr"],
  "due": "2026-05-01",
  "size": "large"
}
```

Any task frontmatter field is patchable. `task-completed` is auto-set to today when status transitions to `done` or `cancelled` (if not explicitly provided). Transitioning away from `done`/`cancelled` clears it.

#### Two-way sync

| Direction  | Trigger                                                          |
| ---------- | ---------------------------------------------------------------- |
| Vault → DB | Gardener processes new/modified markdown file (existing flow)    |
| DB → Vault | Gardener detects DB fields updated via API, rewrites frontmatter |

Conflict resolution: last-write-wins based on timestamp.

### 3. Gardener Task Behaviors

Three new capabilities, each running as a phase in the existing gardener cycle.

#### 3a. Task Decomposition (Raw → Task Notes)

When decomposing raw notes, the gardener already creates `atom` and `fact` notes. Now it also creates `active` (task) notes when raw content contains actionable work.

**Example input (raw note):**

> "Looked into GPU utilization on node-4. ~6.2 GiB free VRAM. Should deploy voyage-4 there. Also need to figure out the discord image backfill once the storage PR lands."

**Output:**

- `atom`: GPU VRAM budgeting on node-4
- `active`: Deploy voyage-4 on node-4 (`status: active`, `size: medium`)
- `active`: Backfill Discord image history (`status: blocked`, `blocked-by: [discord-image-storage-pr]`, `size: unknown`)

The existing Claude subprocess prompt is extended to recognize task-shaped content and emit the task frontmatter contract.

#### 3b. Completion Distillation (Done → Knowledge)

When the gardener sees a task transition to `done`:

1. Read the task note's body and edges
2. Extract reusable learnings into new `atom`/`fact` notes
3. Link new atoms back via `derives_from`

**Cancelled tasks** skip distillation — the decision not to proceed is the artifact.

**Trigger:** During reconcile phase, check for tasks whose `status` changed to `done` since last cycle.

#### 3c. Daily/Weekly Consolidation (Task Rollups)

The gardener generates two rolling view notes, regenerated each cycle:

**`tasks-daily-YYYY-MM-DD`** — "What's on your plate today"

- All `active` tasks with `due` today or overdue
- Sorted by size (small first — quick wins), then due date
- Includes blocked tasks with what's blocking them

**`tasks-weekly-YYYY-Www`** — "What's on your plate this week"

- All `active` + `blocked` tasks with `due` within current week
- Grouped by day
- Size summary: "3 small, 1 medium, 1 large, 2 unknown (review these)"

These are `type: fact` notes — searchable and linkable. Overwritten each cycle (generated views, not authored content).

#### 3d. Size Estimation

When creating a task note (from decomposition or new vault file with `size` absent), the gardener estimates:

| Size      | Heuristic                                                  |
| --------- | ---------------------------------------------------------- |
| `small`   | Single-step, no dependencies, config change or similar     |
| `medium`  | Multi-step but well-understood, few edges                  |
| `large`   | Cross-cutting, multiple blocked-by deps, significant scope |
| `unknown` | Ambiguous — flagged for manual review in rollups           |

### 4. CLI Interface

Extends `homelab knowledge` with a `tasks` subcommand.

```bash
# List tasks (default: active + blocked, excludes someday)
homelab knowledge tasks
homelab knowledge tasks --status active,blocked,someday
homelab knowledge tasks --due-before 2026-04-30
homelab knowledge tasks --size unknown

# Semantic search across tasks
homelab knowledge tasks search "gpu deployment"

# View daily/weekly rollups
homelab knowledge tasks daily
homelab knowledge tasks weekly

# Status transitions
homelab knowledge tasks done <note_id>
homelab knowledge tasks cancel <note_id>
homelab knowledge tasks block <note_id> --by <blocker_note_id>
homelab knowledge tasks activate <note_id>

# Quick create
homelab knowledge tasks add "Deploy voyage-4 on node-4" --due 2026-04-30 --status active
```

**Output format** (matches existing `homelab knowledge search` style):

```
[active]  deploy-voyage-4-node-4 — Deploy voyage-4 on node-4 (medium, due 2026-04-30)
  blocked-by→discord-image-storage-pr, related→gemma-4-gpu-deployment
[someday] refactor-gardener-retry-logic — Refactor gardener retry logic (unknown)
  related→dead-letter-queue-pattern
```

### 5. Home Module Deprecation

The existing Home module (`/api/home`) is replaced by this system. Migration:

1. Any remaining daily/weekly tasks are converted to task notes
2. Home router and models are removed
3. Daily/weekly rollup notes serve the same purpose with full knowledge graph context

## Implementation Order

1. Frontmatter contract + API endpoints (query + patch)
2. CLI `tasks` subcommand
3. Gardener task decomposition (extend decomposition prompt)
4. Gardener size estimation
5. Daily/weekly consolidation
6. Completion distillation
7. DB → Vault writeback (two-way sync)
8. Home module removal
