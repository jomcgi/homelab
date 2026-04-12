# Homelab CLI Design

**Date:** 2026-04-11
**Status:** Accepted

## Problem

Claude Code skills currently wrap API endpoints with raw `curl` commands and inline Cloudflare Access auth. Each new endpoint requires a new skill or skill update with duplicated auth blocks. MCP servers return verbose JSON that burns context tokens.

## Decision

Build a unified `homelab` CLI at `tools/cli/` using typer. Each domain (knowledge, future: k8s, signoz, argocd) is a separate module registered as a typer subgroup. The CLI handles auth, API calls, and token-efficient output formatting.

MCP servers remain for web chat (claude.ai) and cases where MCP simplifies auth. Claude Code locally uses the CLI exclusively.

## Scope (Phase 1: Knowledge)

Four commands covering the knowledge API (excluding `ingest`):

```
homelab knowledge search "query" [--limit N] [--type TYPE] [--json]
homelab knowledge note <note_id> [--json]
homelab knowledge dead-letters [--json]
homelab knowledge replay <raw_id>
```

## Structure

```
tools/cli/
  __init__.py
  main.py            # top-level typer app, registers subgroups
  auth.py            # cloudflared token management
  output.py          # compact formatting + tmpfile writing
  knowledge.py       # knowledge subcommands
  knowledge_test.py  # tests against FastAPI TestClient
  BUILD
```

## Auth (`auth.py`)

Single function: `get_cf_token(hostname) -> str`

- Reads `~/.cloudflared/*{hostname}*` token files
- Runs `cloudflared access login` if missing/expired
- Returns token for `Cookie: CF_Authorization={token}`
- Future domains add their own auth functions (kubeconfig, etc.)

## Output Design

Primary consumer is Claude Code — optimize for token efficiency.

**Compact line format** for lists:

```
[42] _raw/2026/04/11/note.md (obsidian) — invalid JSON [3 retries]
```

**Search results:**

```
[0.85] dead-letter-queue — Dead Letter Queue Pattern (atom)
  derives_from→book-building-event-driven-microservices, related→exactly-once-delivery
[0.62] dlq-threshold — DLQ Threshold as Retry-Exhaustion Signal (atom)
  derives_from→retry-aware-alert-condition
```

**Note command** — metadata on stdout, content to tmpfile:

```
Dead Letter Queue Pattern (atom) [architecture, event-driven, distributed-systems]
Edges: derives_from→book-building-event-driven-microservices
Content: /tmp/homelab-cli/notes/dead-letter-queue.md
```

**`--json` flag** on every command for raw API response.

## Testing

Import FastAPI `TestClient` directly (same pattern as existing knowledge tests). Mock embedding client via `dependency_overrides`. Run with `bb remote test //tools/cli:knowledge_test --config=ci`.

## HTTPRoute Fix

Replace the two specific knowledge API routes in `httproute-private.yaml` with a single `PathPrefix: /api/knowledge` rule. This unblocks dead-letter and future endpoints.

## Skill Consolidation

Replace `knowledge` + `debug-knowledge-ingest` skills with a single `knowledge` skill documenting CLI subcommands. No more curl/auth blocks.

## Future Domains

Adding a new domain (e.g., k8s):

1. Create `tools/cli/kubernetes.py` with typer subgroup
2. Register in `main.py`
3. Add auth function to `auth.py` if needed
4. Update/create skill
