# Knowledge Skill — Design

Expose the monolith's knowledge API on `private.jomcgi.dev` and build a
Claude Code skill that searches and reads the Obsidian knowledge graph from
a work laptop.

## Motivation

The MCP tools (`obsidian-vault-*`) work via Claude.ai remote MCP — they
aren't available from the Claude Code CLI on a work laptop. The monolith
already has semantic search and note retrieval endpoints backed by pgvector,
but they're only reachable inside the cluster (the private HTTPRoute
rewrites all paths to `/private/` and sends to the frontend on port 3000).

The skill should fire proactively — not as a manual `/knowledge` command,
but whenever conversational context suggests my notes might be relevant
("What does Joe think about X?", "What's the basis for this decision?",
"What do I mean by Y?").

## Infrastructure: HTTPRoute + Service

### Service change

Add port 8000 (named `api`) to the monolith Service so Gateway API
HTTPRoutes can target the backend container directly.

### HTTPRoute rules

Two **specific** rules added to `httproute-private.yaml`, before the
catch-all `/` → `/private/` rewrite:

| Path match              | Type       | Rewrite | Target port |
| ----------------------- | ---------- | ------- | ----------- |
| `/api/knowledge/search` | Exact      | none    | 8000        |
| `/api/knowledge/notes`  | PathPrefix | none    | 8000        |

- `/search` is Exact because query params are not part of path matching.
- `/notes` is PathPrefix to allow `/notes/{note_id}` dynamic segments.
- No changes to the public HTTPRoute — endpoints stay private-only behind
  Cloudflare Access SSO (`team: jomcgi`).

## Backend API: edges in responses

### Search (`GET /api/knowledge/search`)

Add a 3rd batched query after the existing 2-query flow (top-N notes → best
chunks):

```sql
SELECT src_note_fk, target_id, target_title, kind, edge_type
FROM knowledge.note_links
WHERE src_note_fk IN (:top_ids)
```

Stitch into each result as an `edges` list:

```json
{
  "note_id": "abc",
  "title": "Zettelkasten Method",
  "tags": ["pkm"],
  "score": 0.82,
  "section": "## Core Principles",
  "snippet": "...",
  "edges": [
    { "target_id": "def", "kind": "edge", "edge_type": "refines" },
    { "target_id": "ghi", "kind": "link", "target_title": "Evergreen Notes" }
  ]
}
```

### Note detail (`GET /api/knowledge/notes/{note_id}`)

Add `edges` to the response alongside existing `content`, `tags`, `type`.
Single query on `note_links` filtered by the note's FK.

Both changes are additive — existing frontend consumers ignore the new
field.

## Skill: `/knowledge`

### Trigger

Any scenario where context about my thinking, decisions, opinions,
knowledge base, or prior work might be relevant. The skill description is
written broadly so the superpowers "1% rule" catches it naturally.

### Auth flow

1. Check for cached Cloudflare Access JWT in `~/.cloudflared/`
2. If missing/expired → run `cloudflared access login https://private.jomcgi.dev`
3. Attach token as `CF_Authorization` cookie on API requests

### Workflow

1. Formulate a search query from conversational context
2. `GET /api/knowledge/search?q=<query>` — lightweight results
3. Review results, make a judgment call — only fetch full content for notes
   that look genuinely relevant
4. Return context to the conversation

### File location

`.claude/skills/knowledge/SKILL.md` — single file, uses `curl` via Bash
for API calls.

### Scope boundaries

- Read-only (write endpoints are future work)
- Does not replace MCP tools (those serve the Claude.ai remote context)
- No hook-based nudging (relies on superpowers discipline)

## Out of scope

- Write endpoint (`/api/knowledge/create-note`)
- Public HTTPRoute rules for knowledge endpoints
- Changes to the frontend search overlay
- Hook-based reminders to invoke the skill

## Change summary

| Component                                | Change                                                                                 |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `chart/templates/service.yaml`           | Add port 8000 (named `api`)                                                            |
| `chart/templates/httproute-private.yaml` | 2 rules: Exact `/api/knowledge/search` + PathPrefix `/api/knowledge/notes` → port 8000 |
| `knowledge/store.py`                     | Edges query in `search_notes_with_context` + `get_note_links`                          |
| `knowledge/router.py`                    | Include edges in both endpoint responses                                               |
| `.claude/skills/knowledge/SKILL.md`      | Skill with broad trigger, cloudflared auth, search → selective read                    |
