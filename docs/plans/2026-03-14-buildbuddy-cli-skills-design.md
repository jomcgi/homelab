# Design: Replace BuildBuddy MCP Server with `bb` CLI + Skills

**Date:** 2026-03-14
**Status:** Approved

---

## Problem

The BuildBuddy MCP server (`projects/agent_platform/buildbuddy_mcp/`) wraps the BuildBuddy REST API in 8 MCP tools, deployed as a container behind Context Forge. This adds a full deployment lifecycle (image build, push, registration, health alerts, image updater) for what amounts to thin HTTP wrappers.

The `bb` CLI (BuildBuddy CLI, v5.0.321) already provides richer functionality: `bb view`, `bb print`, `bb ask`, `bb remote`, `bb execute`, `bb search`, `bb explain`. Agents can use these directly — no MCP indirection needed.

## Decision

Replace the BuildBuddy MCP server with:

1. A rewritten `/buildbuddy` skill that teaches agents to use the `bb` CLI
2. A PreToolUse hook that redirects `bazel`/`bazelisk` commands to `bb remote`
3. The `bb` binary added to Goose sandbox container images

## Architecture

```
Before:
  Agent → Context Forge → BuildBuddy MCP (Python) → BuildBuddy REST API

After:
  Agent → bb CLI → BuildBuddy (direct)
  Agent → curl (fallback) → BuildBuddy REST API
```

### Skill Structure

Following Claude Code skill best practices — lean SKILL.md with heavy reference material in supporting files:

```
.claude/skills/buildbuddy/
├── SKILL.md                    # ~100 lines: workflow, bb CLI commands
└── references/
    └── api-requests.md         # curl/jq templates for API-only operations
```

### Hook: Redirect bazel → bb remote

A PreToolUse hook on Bash intercepts commands containing `bazel ` or `bazelisk ` (excluding git commit messages) and blocks with a message suggesting `bb remote <command>` instead. This ensures all bazel commands run on BuildBuddy's cloud runners — no local bazel server.

### Auth

`BUILDBUDDY_API_KEY` is already mounted in Goose sandboxes from the `agent-secrets` 1Password item. The `bb` CLI reads this env var automatically. No infrastructure changes needed.

For Claude Code (local), `bb login` configures auth via git config.

## What Changes

### Add

| Item                            | Details                                                                                                                                                 |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/buildbuddy` skill (rewritten) | CI debugging via `bb view`, `bb print`, `bb ask`. `curl`/`jq` fallback for cache scorecard, execution details. Supporting files hold request templates. |
| PreToolUse hook                 | Intercepts `bazel`/`bazelisk` commands → suggests `bb remote`                                                                                           |
| `bb` binary in Goose image      | So sandbox agents can use the CLI directly                                                                                                              |

### Update

| Item           | Details                                                                         |
| -------------- | ------------------------------------------------------------------------------- |
| `/bazel` skill | Remove MCP references, teach `bb remote`, reference `/buildbuddy` for debugging |
| CLAUDE.md      | Remove BuildBuddy from MCP tools table, update CI debugging section             |
| Shell alias    | Fix `bb` → `/usr/local/bin/bb` (BuildBuddy CLI, not bazelisk)                   |

### Remove

| Item                  | Details                                                                         |
| --------------------- | ------------------------------------------------------------------------------- |
| BuildBuddy MCP server | `projects/agent_platform/buildbuddy_mcp/` — code, tests, BUILD, image           |
| MCP server deployment | Remove `buildbuddy-mcp` entry from `projects/agent_platform/deploy/values.yaml` |
| PreToolUse hook       | Remove hook blocking `curl` to BuildBuddy API                                   |

### No Changes Needed

| Item                  | Why                                                             |
| --------------------- | --------------------------------------------------------------- |
| Goose sandbox secrets | `BUILDBUDDY_API_KEY` already in `agent-secrets` OnePasswordItem |
| Context Forge gateway | BuildBuddy tools auto-deregister when the server stops          |

## Skill Design: `/buildbuddy`

**SKILL.md** (~100 lines) covers:

- When to use: CI failures, build investigation, re-triggering workflows
- Primary tools: `bb view`, `bb print`, `bb ask`, `bb remote`
- Workflow: get invocation ID → investigate → fix
- When to fall back to API: cache scorecard, execution node pinning
- Reference to `references/api-requests.md` for curl templates

**references/api-requests.md** covers:

- Common setup (base URL, API key handling)
- `GetInvocation`, `GetTarget`, `GetExecution`, `GetCacheScoreCard` request templates
- `jq` filters for extracting useful fields
- Adapted from sluongng/dotfiles buildbuddy-invocation-troubleshoot skill

Key principle: `bb` CLI first, `curl` fallback only for operations the CLI doesn't support.

## Skill Design: `/bazel` (updated)

Remove all MCP tool references. Update to:

- `bb remote test //...` for running tests
- `bb remote build //...` for building
- `bb remote query //...` for querying the build graph
- Reference `/buildbuddy` skill for debugging CI failures

## bb CLI → MCP Tool Mapping

| MCP Tool           | bb CLI Replacement                            |
| ------------------ | --------------------------------------------- |
| `get_invocation`   | `bb view <invocation_id>`                     |
| `get_log`          | `bb print --invocation_id=<id>`               |
| `get_target`       | `bb view` (target details in output)          |
| `diagnose_failure` | `bb ask` (BuildBuddy's built-in AI diagnosis) |
| `execute_workflow` | `bb remote test //...`                        |
| `run`              | `bb remote <command>` / `bb execute`          |
| `get_action`       | `curl` fallback (GetExecution API)            |
| `get_file`         | `bb download`                                 |

## What This Eliminates

- 1 container image (build, push, deploy cycle)
- 1 MCP server registration job
- 1 HTTPCheck health alert
- 1 ArgoCD Image Updater config
- ~350 lines of Python (main.py + composite.py)
- ~200 lines of tests
- 8 MCP tools from the Context Forge gateway (71 → 63 tools)

## References

| Resource                                                                                                    | Relevance                                       |
| ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| [sluongng/dotfiles buildbuddy skills](https://github.com/sluongng/dotfiles/tree/master/config/codex/skills) | Reference implementation by BuildBuddy engineer |
| [Claude Code skills docs](https://code.claude.com/docs/en/skills)                                           | Best practices for skill structure              |
| [BuildBuddy CLI docs](https://www.buildbuddy.io/docs/cli)                                                   | `bb` command reference                          |
