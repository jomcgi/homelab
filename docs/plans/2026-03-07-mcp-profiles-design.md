# Design: Role-Based MCP Profiles for Goose Sandboxes

**Date:** 2026-03-07
**Status:** Approved
**Relates to:** [ADR 005 — Role-Based MCP Access](../../docs/decisions/agents/005-role-based-mcp-access.md)

---

## Problem

Goose sandbox agents connect to Context Forge with no authentication and see all 60+ MCP tools (Kubernetes, ArgoCD, SigNoz, BuildBuddy). This wastes context window tokens on irrelevant tool descriptions, increases wrong-tool selection, and provides no tool-level access control.

## Decision

Introduce **profiles** — named configurations that map to Context Forge teams, Goose recipes, and scoped JWT tokens. Each profile controls which MCP tools the agent can see by leveraging Context Forge's token-scoping layer.

## Architecture

```
Developer Laptop (one-time setup)
──────────────────────────────────
scripts/setup-mcp-profiles.sh
├─ op read JWT_SECRET_KEY
├─ Create teams in Context Forge API
├─ Set tool visibility to team-scoped
├─ Mint scoped JWTs per profile
└─ op item edit goose-mcp-tokens
         │
         │ 1Password Operator auto-syncs
         ▼
Kubernetes (goose-sandboxes namespace)
──────────────────────────────────────
Secret: goose-mcp-tokens
├─ CI_DEBUG_MCP_TOKEN (teams: [ci-debug])
└─ (future profile tokens)

SandboxTemplate mounts tokens as env vars
         │
         ▼
Goose Container Image
├─ config.yaml (default, all tools, no auth)
└─ recipes/
    ├─ ci-debug.yaml  (BuildBuddy via scoped token)
    └─ code-fix.yaml  (developer + github only)

agent-run --profile ci-debug "fix the build"
→ goose run --recipe recipes/ci-debug.yaml --no-profile \
            --params "task_description=fix the build"
```

### How Tool Scoping Works

Context Forge's two-layer auth model:

1. **Token scoping (visibility):** JWT `teams` claim filters which tools the agent sees. A token with `teams: ["ci-debug-uuid"]` only sees tools assigned to the `ci-debug` team.
2. **RBAC (permissions):** The `developer` role grants `tools.read` + `tools.execute`. All profile tokens use this role.

The `code-fix` profile needs no token — it simply omits the Context Forge extension from its recipe, so the agent has no MCP tools at all.

## Profiles

### Initial Profiles

| Profile    | Team       | Token Env Var        | Tools                   | Use Case                    |
| ---------- | ---------- | -------------------- | ----------------------- | --------------------------- |
| `ci-debug` | `ci-debug` | `CI_DEBUG_MCP_TOKEN` | BuildBuddy (6 tools)    | CI failure investigation    |
| `code-fix` | none       | none                 | developer + github only | Pure code changes           |
| (default)  | none       | none (no auth)       | All tools via ClusterIP | Current behavior, unchanged |

### Profile Definition File

`charts/goose-sandboxes/profiles.yaml` — documentation and reference for the setup script:

```yaml
profiles:
  ci-debug:
    description: "BuildBuddy tools only — for CI failure investigation"
    teams: ["ci-debug"]
    tools: ["buildbuddy-mcp"]
    token_env: CI_DEBUG_MCP_TOKEN
    recipe: ci-debug.yaml

  code-fix:
    description: "No cluster tools — pure code changes"
    teams: []
    tools: []
    token_env: null
    recipe: code-fix.yaml
```

## Components

### 1. Goose Recipes (baked into container image)

Recipes are YAML files at `/home/goose-agent/recipes/` that define which extensions load for a given profile. Key mechanism: `--no-profile` flag on `goose run` prevents `config.yaml` extensions from loading, so only the recipe's extensions are active.

**ci-debug.yaml:**

- Extensions: `developer` (builtin) + `context-forge` (streamable_http with `Authorization: Bearer ${CI_DEBUG_MCP_TOKEN}`) + `github` (stdio)
- Settings: `max_turns: 50`
- Instructions: guide agent to use BuildBuddy tools for CI debugging

**code-fix.yaml:**

- Extensions: `developer` (builtin) + `github` (stdio)
- No Context Forge extension — agent has no cluster tool access
- Settings: `max_turns: 50`
- Instructions: guide agent for pure code fixes

### 2. Setup Script (`scripts/setup-mcp-profiles.sh`)

Local script run from developer laptop. Requirements: `op` CLI (authenticated), `python3` with `PyJWT`, `curl`, `jq`.

Steps:

1. Read `JWT_SECRET_KEY` from 1Password: `op read "op://k8s-homelab/context-forge/JWT_SECRET_KEY"`
2. Mint short-lived admin JWT (5 min TTL)
3. Create `ci-debug` team via `POST /teams` (idempotent — skip if exists)
4. Add admin user as team member with `developer` role
5. Look up BuildBuddy tool IDs via `GET /tools`
6. Assign BuildBuddy tools to `ci-debug` team, set visibility to `team`
7. Mint 30-day scoped JWT: `teams: ["<ci-debug-uuid>"]`, `is_admin: false`
8. Create/update 1Password item: `op item edit goose-mcp-tokens --vault k8s-homelab "CI_DEBUG_MCP_TOKEN=<jwt>"`

Token rotation: re-run the script. 1Password Operator resyncs the Secret automatically.

### 3. Infrastructure Changes

**goose-sandboxes chart:**

- New `OnePasswordItem` for `goose-mcp-tokens` secret
- New env vars in SandboxTemplate for `CI_DEBUG_MCP_TOKEN`
- `profiles.yaml` as reference documentation

**goose-agent container image:**

- New `recipes/` directory with `ci-debug.yaml` and `code-fix.yaml`
- Packaged into image via BUILD rule (same pattern as existing `config.yaml`)

**agent-run CLI:**

- New `--profile` flag (string, optional)
- When set: validates against known profiles, constructs `goose run --recipe ... --no-profile --params ...`
- When unset: current behavior (`goose run --text <task>`)
- Design note: `--profile` maps cleanly to an API parameter for the in-progress agent-run API

### 4. Context Forge Configuration

No Helm chart changes needed. Team creation and tool assignment happen via the setup script calling the Context Forge admin API. The gateway already has `MCP_CLIENT_AUTH_ENABLED: "true"` from ADR 006.

In-cluster requests without a Bearer token continue to work (unauthenticated access sees public tools only — which is currently all tools). The default profile preserves this behavior.

## Token Design

JWT payload for `ci-debug` profile:

```json
{
  "sub": "goose-ci-debug@agents.jomcgi.dev",
  "iat": 1741305600,
  "exp": 1743897600,
  "jti": "<uuid>",
  "aud": "mcpgateway-api",
  "iss": "mcpgateway",
  "is_admin": false,
  "teams": ["<ci-debug-team-uuid>"]
}
```

- **HS256 symmetric signing** using `JWT_SECRET_KEY` (same key used for server registration)
- **30-day TTL** — sandbox pods are ephemeral, so stale tokens in running pods are short-lived
- **`sub` identifies the profile**, not a human user — useful for audit logs
- **`JWT_SECRET_KEY` never leaves 1Password** — the setup script reads it via `op read`, mints tokens locally, and stores only the tokens back in 1Password

## Security

- Profile tokens are **less privileged** than the current setup (no auth = all tools)
- `JWT_SECRET_KEY` is not exposed to sandbox pods — only pre-minted tokens
- Tokens are scoped to specific teams — a compromised `ci-debug` token only sees BuildBuddy tools
- The `code-fix` profile has no MCP access at all — smallest possible attack surface
- Default (no profile) behavior is unchanged — backwards compatible

## Not In Scope

- External client (Claude Code) profiles — handled by OAuth/SSO identity
- Agent-run API integration — designed to be compatible (`--profile` → API param)
- `.goosehints` file — orthogonal, can be added independently
- ADR 005 updates — this implements Phase 2 for sandboxes as designed
- Additional profiles beyond ci-debug and code-fix — add later as needed
