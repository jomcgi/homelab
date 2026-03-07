# MCP Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add profile-based MCP tool scoping to Goose sandboxes so different task types see only relevant tools.

**Architecture:** Goose recipes define per-profile extension sets. Context Forge teams + scoped JWTs control tool visibility server-side. A local setup script provisions teams and tokens via 1Password CLI. agent-run gains a `--profile` flag to select recipes.

**Tech Stack:** Go (agent-run), YAML (Goose recipes, Helm), Bash + Python (setup script), 1Password CLI (`op`), Context Forge REST API

**Design doc:** `docs/plans/2026-03-07-mcp-profiles-design.md`

---

## Task 1: Create Goose Recipe Files

**Files:**
- Create: `charts/goose-agent/image/recipes/ci-debug.yaml`
- Create: `charts/goose-agent/image/recipes/code-fix.yaml`

**Step 1: Create ci-debug recipe**

Create `charts/goose-agent/image/recipes/ci-debug.yaml`:

```yaml
version: "1.0.0"
title: "CI Debug"
description: "Debug CI build failures using BuildBuddy tools"
instructions: |
  You are debugging a CI build failure in the homelab repo.
  Use BuildBuddy MCP tools to investigate build logs and failing targets.
  Fix the issue, verify with bazel test, commit using conventional commits
  format, and create a PR.
  DO NOT use kubectl or argocd CLI commands.
prompt: "{{ task_description }}"
parameters:
  - key: task_description
    input_type: string
    requirement: required
extensions:
  - type: builtin
    name: developer
  - type: streamable_http
    name: context-forge
    uri: http://context-forge.mcp-gateway.svc.cluster.local:8000/mcp
    timeout: 300
    headers:
      Authorization: "Bearer ${CI_DEBUG_MCP_TOKEN}"
  - type: stdio
    name: github
    cmd: pnpm
    args: ["dlx", "@modelcontextprotocol/server-github"]
    env_keys: ["GITHUB_TOKEN"]
settings:
  max_turns: 50
```

**Step 2: Create code-fix recipe**

Create `charts/goose-agent/image/recipes/code-fix.yaml`:

```yaml
version: "1.0.0"
title: "Code Fix"
description: "Fix code issues without cluster access"
instructions: |
  Fix the described issue in the homelab repo.
  Run bazel test //... to verify your changes.
  Commit using conventional commits format and create a PR.
  You do NOT have access to cluster tools.
prompt: "{{ task_description }}"
parameters:
  - key: task_description
    input_type: string
    requirement: required
extensions:
  - type: builtin
    name: developer
  - type: stdio
    name: github
    cmd: pnpm
    args: ["dlx", "@modelcontextprotocol/server-github"]
    env_keys: ["GITHUB_TOKEN"]
settings:
  max_turns: 50
```

**Step 3: Commit**

```bash
git add charts/goose-agent/image/recipes/
git commit -m "feat(goose-agent): add ci-debug and code-fix recipe files"
```

---

## Task 2: Package Recipes Into Container Image

**Files:**
- Modify: `charts/goose-agent/image/BUILD`

**Step 1: Add recipes pkg_tar rule**

Add a new `pkg_tar` rule to `charts/goose-agent/image/BUILD` that packages the recipes directory into the image, alongside the existing `config_tar`:

```python
# Package Goose recipes into the image at ~/recipes/
pkg_tar(
    name = "recipes_tar",
    srcs = glob(["recipes/*.yaml"]),
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/home/goose-agent/recipes",
)
```

**Step 2: Add recipes_tar to image tars**

In the `apko_image` rule, add `:recipes_tar` to the `tars` list:

```python
apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@goose_agent_lock//:contents",
    multiarch_tars = [
        "@goose//:tar",
        "@bb//:tar",
    ],
    repository = "ghcr.io/jomcgi/homelab/goose-agent",
    tars = [
        ":config_tar",
        ":claude_code_tar",
        ":recipes_tar",
    ],
)
```

**Step 3: Verify image builds**

Run: `bazel build //charts/goose-agent/image`
Expected: BUILD SUCCESS — image includes recipes at `/home/goose-agent/recipes/`

**Step 4: Commit**

```bash
git add charts/goose-agent/image/BUILD
git commit -m "build(goose-agent): package recipe files into container image"
```

---

## Task 3: Add Profile Token Secret to goose-sandboxes Chart

**Files:**
- Modify: `charts/goose-sandboxes/templates/onepassworditem.yaml`
- Modify: `charts/goose-sandboxes/templates/sandboxtemplate.yaml`
- Modify: `charts/goose-sandboxes/values.yaml`
- Create: `charts/goose-sandboxes/profiles.yaml`

**Step 1: Add profiles.yaml documentation file**

Create `charts/goose-sandboxes/profiles.yaml`:

```yaml
# Profile definitions for Goose sandbox agents.
# This file documents available profiles and their tool scoping.
# It is not consumed by Helm — it serves as reference for the setup script
# (scripts/setup-mcp-profiles.sh) and for humans.
#
# To add a new profile:
#   1. Add entry here
#   2. Create recipe in charts/goose-agent/image/recipes/<name>.yaml
#   3. Add token_env to values.yaml profileTokens section
#   4. Run scripts/setup-mcp-profiles.sh to provision team + token
#   5. Add profile name to validProfiles in tools/agent-run/main.go

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

**Step 2: Add OnePasswordItem for goose-mcp-tokens**

Append to `charts/goose-sandboxes/templates/onepassworditem.yaml`:

```yaml
---
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: goose-mcp-tokens
  namespace: {{ .Release.Namespace }}
spec:
  itemPath: "vaults/{{ .Values.secrets.mcpTokens.vault }}/items/{{ .Values.secrets.mcpTokens.onePasswordItem }}"
```

**Step 3: Add mcpTokens to values.yaml secrets section**

In `charts/goose-sandboxes/values.yaml`, add to the `secrets` block:

```yaml
secrets:
  claudeAuth:
    onePasswordItem: litellm-claude-auth
    vault: k8s-homelab
  agentSecrets:
    onePasswordItem: agent-secrets
    vault: k8s-homelab
  mcpTokens:
    onePasswordItem: goose-mcp-tokens
    vault: k8s-homelab
```

**Step 4: Add CI_DEBUG_MCP_TOKEN env var to SandboxTemplate**

In `charts/goose-sandboxes/templates/sandboxtemplate.yaml`, add to the goose container's `env` list (after the existing BUILDBUDDY_API_KEY entry):

```yaml
            - name: CI_DEBUG_MCP_TOKEN
              valueFrom:
                secretKeyRef:
                  name: goose-mcp-tokens
                  key: CI_DEBUG_MCP_TOKEN
                  optional: true
```

Note: `optional: true` ensures the pod starts even if the 1Password item doesn't exist yet.

**Step 5: Verify chart renders**

Run: `helm template goose-sandboxes charts/goose-sandboxes/`
Expected: Output includes the new OnePasswordItem and the CI_DEBUG_MCP_TOKEN env var.

**Step 6: Commit**

```bash
git add charts/goose-sandboxes/
git commit -m "feat(goose-sandboxes): add profile token secret and env var"
```

---

## Task 4: Add --profile Flag to agent-run

**Files:**
- Modify: `tools/agent-run/main.go`
- Modify: `tools/agent-run/BUILD` (if deps change — unlikely)

**Step 1: Add profileFlag var and known profiles**

At the top of `main.go`, alongside the existing `issueFlag`, add:

```go
var profileFlag string

var validProfiles = map[string]string{
	"ci-debug": "/home/goose-agent/recipes/ci-debug.yaml",
	"code-fix": "/home/goose-agent/recipes/code-fix.yaml",
}
```

**Step 2: Register the flag**

In `func init()`, add:

```go
rootCmd.Flags().StringVar(&profileFlag, "profile", "", "Goose profile to use (ci-debug, code-fix)")
```

**Step 3: Validate profile in run()**

At the start of `func run()`, after resolving the task, add validation:

```go
if profileFlag != "" {
    if _, ok := validProfiles[profileFlag]; !ok {
        return fmt.Errorf("unknown profile %q, valid profiles: ci-debug, code-fix", profileFlag)
    }
}
```

**Step 4: Modify execGoose to use recipe when profile is set**

Replace the command construction in `execGoose()`. Change the static command:

```go
Command: []string{"goose", "run", "--text", task},
```

To a dynamic command based on profile:

```go
func buildGooseCommand(task, profile string) []string {
	if profile == "" {
		return []string{"goose", "run", "--text", task}
	}
	recipePath := validProfiles[profile]
	return []string{
		"goose", "run",
		"--recipe", recipePath,
		"--no-profile",
		"--params", fmt.Sprintf("task_description=%s", task),
	}
}
```

Update `execGoose` to accept the profile parameter and use `buildGooseCommand`.

**Step 5: Pass profileFlag through to execGoose**

Update the call in `run()`:

```go
exitCode, err := execGoose(ctx, config, clientset, podName, task, profileFlag)
```

And update `execGoose` signature:

```go
func execGoose(ctx context.Context, config *rest.Config, clientset kubernetes.Interface, podName, task, profile string) (int, error) {
```

Use `buildGooseCommand(task, profile)` for the `Command` field.

**Step 6: Print profile info**

Add after the "Running goose task" print line:

```go
if profileFlag != "" {
    fmt.Printf("Using profile: %s (recipe: %s)\n", profileFlag, validProfiles[profileFlag])
}
```

**Step 7: Verify it builds**

Run: `bazel build //tools/agent-run`
Expected: BUILD SUCCESS

**Step 8: Commit**

```bash
git add tools/agent-run/main.go
git commit -m "feat(agent-run): add --profile flag for recipe-based tool scoping"
```

---

## Task 5: Create Setup Script

**Files:**
- Create: `scripts/setup-mcp-profiles.sh`

**Step 1: Write the setup script**

Create `scripts/setup-mcp-profiles.sh`. The script:

1. Reads `JWT_SECRET_KEY` from 1Password via `op read`
2. Discovers the Context Forge API URL (port-forward or external)
3. Mints a short-lived admin JWT for API calls
4. Creates the `ci-debug` team (idempotent)
5. Looks up BuildBuddy tool IDs
6. Sets BuildBuddy tools to `visibility: team` and assigns to `ci-debug` team
7. Mints a 30-day scoped JWT for the `ci-debug` profile
8. Stores the token in 1Password

```bash
#!/usr/bin/env bash
# scripts/setup-mcp-profiles.sh
#
# Provisions Context Forge teams and scoped JWT tokens for Goose sandbox profiles.
# Stores tokens in 1Password; the 1Password Operator syncs them to Kubernetes.
#
# Prerequisites:
#   - op CLI authenticated (op signin)
#   - python3 with PyJWT installed (pip install pyjwt)
#   - curl, jq
#   - kubectl access to cluster (for port-forward, or use GATEWAY_URL env var)
#
# Usage:
#   ./scripts/setup-mcp-profiles.sh
#
# To rotate tokens, re-run the script.
set -euo pipefail

VAULT="k8s-homelab"
OP_ITEM="goose-mcp-tokens"
ADMIN_EMAIL="admin@jomcgi.dev"
TOKEN_TTL_DAYS=30

# Context Forge gateway URL — override with env var or default to port-forward
GATEWAY_URL="${GATEWAY_URL:-}"

cleanup() {
  if [[ -n "${PF_PID:-}" ]]; then
    kill "$PF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ -z "$GATEWAY_URL" ]]; then
  echo "Starting port-forward to Context Forge..."
  kubectl port-forward -n mcp-gateway svc/context-forge-mcp-stack-mcpgateway 4444:80 &
  PF_PID=$!
  sleep 3
  GATEWAY_URL="http://localhost:4444"
fi

echo "Using gateway: $GATEWAY_URL"

# Read signing key from 1Password
JWT_SECRET=$(op read "op://${VAULT}/context-forge/JWT_SECRET_KEY")

# Mint a short-lived admin token for API calls
mint_admin_token() {
  python3 -c "
import jwt, time, uuid
payload = {
    'sub': '${ADMIN_EMAIL}',
    'iat': int(time.time()),
    'exp': int(time.time()) + 300,
    'jti': str(uuid.uuid4()),
    'aud': 'mcpgateway-api',
    'iss': 'mcpgateway',
    'is_admin': True,
    'teams': None,
}
print(jwt.encode(payload, '${JWT_SECRET}', algorithm='HS256'))
"
}

# Mint a scoped profile token
mint_profile_token() {
  local sub="$1" teams_json="$2"
  python3 -c "
import jwt, time, uuid, json
payload = {
    'sub': '${sub}',
    'iat': int(time.time()),
    'exp': int(time.time()) + (${TOKEN_TTL_DAYS} * 86400),
    'jti': str(uuid.uuid4()),
    'aud': 'mcpgateway-api',
    'iss': 'mcpgateway',
    'is_admin': False,
    'teams': json.loads('${teams_json}'),
}
print(jwt.encode(payload, '${JWT_SECRET}', algorithm='HS256'))
"
}

ADMIN_TOKEN=$(mint_admin_token)

echo ""
echo "=== Setting up ci-debug profile ==="
echo ""

# Step 1: Create ci-debug team (idempotent)
echo "Creating ci-debug team..."
EXISTING_TEAM=$(curl -sf "${GATEWAY_URL}/teams" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[] | select(.name=="ci-debug") | .id // empty' 2>/dev/null || echo "")

if [[ -n "$EXISTING_TEAM" ]]; then
  echo "Team ci-debug already exists: ${EXISTING_TEAM}"
  TEAM_ID="$EXISTING_TEAM"
else
  TEAM_RESPONSE=$(curl -sf -X POST "${GATEWAY_URL}/teams" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name": "ci-debug", "description": "BuildBuddy tools for CI debugging"}')
  TEAM_ID=$(echo "$TEAM_RESPONSE" | jq -r '.id')
  echo "Created team ci-debug: ${TEAM_ID}"
fi

# Step 2: Add admin as team member with developer role
echo "Assigning developer role..."
curl -sf -X POST "${GATEWAY_URL}/rbac/users/${ADMIN_EMAIL}/roles" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"role_id\": \"developer\", \"scope\": \"team\", \"scope_id\": \"${TEAM_ID}\"}" > /dev/null 2>&1 || true
echo "Role assigned."

# Step 3: Find BuildBuddy tool IDs
echo "Looking up BuildBuddy tools..."
TOOLS_JSON=$(curl -sf "${GATEWAY_URL}/tools?limit=200" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}")
BB_TOOL_IDS=$(echo "$TOOLS_JSON" | jq -r '[.[] | select(.name | startswith("buildbuddy")) | .id] | join(",")')

if [[ -z "$BB_TOOL_IDS" ]]; then
  echo "WARNING: No BuildBuddy tools found. Checking tool names..."
  echo "$TOOLS_JSON" | jq -r '.[].name' | head -20
  echo ""
  echo "You may need to adjust the tool name filter. Searching for tools containing 'build'..."
  BB_TOOL_IDS=$(echo "$TOOLS_JSON" | jq -r '[.[] | select(.name | test("build"; "i")) | .id] | join(",")')
fi

echo "BuildBuddy tool IDs: ${BB_TOOL_IDS}"

# Step 4: Set BuildBuddy tools to team visibility
echo "Setting tool visibility to team..."
IFS=',' read -ra TOOL_ARRAY <<< "$BB_TOOL_IDS"
for tool_id in "${TOOL_ARRAY[@]}"; do
  curl -sf -X PUT "${GATEWAY_URL}/tools/${tool_id}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"visibility": "team"}' > /dev/null
  echo "  Set tool ${tool_id} to team visibility"
done

# Step 5: Mint scoped JWT for ci-debug
echo ""
echo "Minting ci-debug profile token (${TOKEN_TTL_DAYS}-day TTL)..."
CI_DEBUG_TOKEN=$(mint_profile_token "goose-ci-debug@agents.jomcgi.dev" "[\"${TEAM_ID}\"]")
echo "Token minted."

# Step 6: Store in 1Password
echo ""
echo "Storing token in 1Password (${VAULT}/${OP_ITEM})..."

# Create the item if it doesn't exist, otherwise update it
if op item get "$OP_ITEM" --vault "$VAULT" > /dev/null 2>&1; then
  op item edit "$OP_ITEM" --vault "$VAULT" \
    "CI_DEBUG_MCP_TOKEN=${CI_DEBUG_TOKEN}"
  echo "Updated existing 1Password item."
else
  op item create --category=login --vault "$VAULT" --title "$OP_ITEM" \
    "CI_DEBUG_MCP_TOKEN=${CI_DEBUG_TOKEN}"
  echo "Created new 1Password item."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Wait for 1Password Operator to sync the secret (~30s)"
echo "  2. New sandbox pods will pick up the token automatically"
echo "  3. Test with: agent-run --profile ci-debug 'list recent CI failures'"
echo ""
echo "To rotate tokens, re-run this script."
```

**Step 2: Make executable**

```bash
chmod +x scripts/setup-mcp-profiles.sh
```

**Step 3: Commit**

```bash
git add scripts/setup-mcp-profiles.sh
git commit -m "feat: add setup script for MCP profile provisioning"
```

---

## Task 6: End-to-End Verification

This task is manual and not committed — it validates the full chain works.

**Step 1: Push branch and wait for image build**

```bash
git push -u origin feat/mcp-profiles
```

Wait for CI to build the new goose-agent image with recipes baked in.

**Step 2: Run the setup script**

```bash
./scripts/setup-mcp-profiles.sh
```

Expected: Script creates team, assigns tools, mints token, stores in 1Password.

**Step 3: Verify 1Password item exists**

```bash
op item get goose-mcp-tokens --vault k8s-homelab --fields CI_DEBUG_MCP_TOKEN | head -c 20
```

Expected: Starts with `eyJ` (base64 JWT header).

**Step 4: Deploy chart changes**

Merge the PR or sync ArgoCD to pick up the new OnePasswordItem and SandboxTemplate env var. Verify the secret syncs:

Use MCP tool `kubernetes-mcp-resources-get` to check:
- Secret `goose-mcp-tokens` exists in `goose-sandboxes` namespace
- Contains key `CI_DEBUG_MCP_TOKEN`

**Step 5: Test ci-debug profile**

```bash
bazel run //tools/agent-run -- --profile ci-debug "List the most recent BuildBuddy invocation and summarize its status"
```

Expected: Agent uses only BuildBuddy tools from Context Forge. No SigNoz/ArgoCD/K8s tools appear in tool listings.

**Step 6: Test code-fix profile**

```bash
bazel run //tools/agent-run -- --profile code-fix "Add a comment to tools/agent-run/main.go explaining the profile flag"
```

Expected: Agent has developer + github extensions only. No MCP tools at all.

**Step 7: Test default (no profile)**

```bash
bazel run //tools/agent-run -- "List all ArgoCD applications"
```

Expected: Current behavior — all tools available (no auth, ClusterIP access).

---

## Task 7: Create PR

**Step 1: Push all commits**

```bash
git push -u origin feat/mcp-profiles
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: role-based MCP profiles for goose sandboxes" --body "$(cat <<'EOF'
## Summary

- Add profile-based tool scoping for Goose sandbox agents
- Two initial profiles: `ci-debug` (BuildBuddy only) and `code-fix` (no cluster tools)
- Goose recipes baked into container image control per-profile extensions
- Context Forge teams + scoped JWTs provide server-side tool filtering
- `agent-run --profile <name>` selects the recipe
- Local setup script provisions teams/tokens via 1Password CLI

Implements ADR 005 Phase 2 for sandbox agents.

## Test plan

- [ ] `bazel build //charts/goose-agent/image` — image builds with recipes
- [ ] `bazel build //tools/agent-run` — agent-run builds with --profile flag
- [ ] `helm template goose-sandboxes charts/goose-sandboxes/` — renders with new secret + env var
- [ ] Run `setup-mcp-profiles.sh` — provisions team and token
- [ ] `agent-run --profile ci-debug "describe recent CI runs"` — only BuildBuddy tools visible
- [ ] `agent-run --profile code-fix "fix a typo"` — no MCP tools
- [ ] `agent-run "list apps"` — all tools (default, unchanged)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
