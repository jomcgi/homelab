# Replace BuildBuddy MCP Server with `bb` CLI + Skills — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the BuildBuddy MCP server and replace it with Claude Code skills that teach agents to use the `bb` CLI directly.

**Architecture:** Agents call `bb view`, `bb print`, `bb ask`, `bb remote` directly instead of going through Context Forge → BuildBuddy MCP → REST API. A PreToolUse hook redirects `bazel`/`bazelisk` commands to `bb remote`. The `bb` binary is added to Goose sandbox images.

**Tech Stack:** Shell (hooks), Markdown (skills), YAML (Helm values, apko), Starlark (BUILD files)

**Design doc:** `docs/plans/2026-03-14-buildbuddy-cli-skills-design.md`

---

### Task 1: Rewrite `/buildbuddy` Skill

Replace the MCP-based skill with one that teaches `bb` CLI usage, keeping the SKILL.md lean (~100 lines) with heavy reference material in a supporting file.

**Files:**

- Rewrite: `.claude/skills/buildbuddy/SKILL.md`
- Create: `.claude/skills/buildbuddy/references/api-requests.md`

**Step 1: Rewrite SKILL.md**

Replace the entire file with:

```markdown
---
name: buildbuddy
description: Use when debugging failed CI/CD jobs, analyzing build logs, or investigating build failures. Uses the bb CLI and curl fallback for BuildBuddy remote build execution insights.
---

# BuildBuddy — CI Debugging & Remote Execution

## Tools

| Command                                                 | Purpose                                           |
| ------------------------------------------------------- | ------------------------------------------------- |
| `bb view <invocation_id>`                               | Invocation metadata, status, duration, targets    |
| `bb print --invocation_id=<id>`                         | Full build logs (stdout/stderr)                   |
| `bb ask "<question>" --invocation_id=<id>`              | AI-powered diagnosis of build failures            |
| `bb remote <bazel_command>`                             | Run any bazel command on BuildBuddy cloud runners |
| `bb download --invocation_id=<id> --output_path=<path>` | Download build artifacts                          |

## Auth

- **Claude Code (local):** `bb` reads credentials from git config (`bb login` to set up)
- **Goose sandboxes:** `BUILDBUDDY_API_KEY` env var (already mounted from `agent-secrets`)

## Debugging Failed CI
```

GitHub PR fails
│
▼
gh pr checks ──► extract invocation ID from BuildBuddy URL
│
▼
bb view <id> ──► check success/failure, duration, targets
│
▼
bb print --invocation_id=<id> ──► find error messages in logs
│
▼
bb ask "why did this fail?" --invocation_id=<id> ──► AI diagnosis
│
▼
Parse errors ──► fix root cause

````

### Step 1: Get the Invocation ID

```bash
# From a PR
gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link' | grep -o '[^/]*$' | head -1

# From a commit (requires full 40-char SHA)
FULL_SHA=$(git rev-parse <short_sha>)
# Then search BuildBuddy UI: https://jomcgi.buildbuddy.io/invocation/?commit=$FULL_SHA
````

The invocation ID is the last path segment of the BuildBuddy URL:
`https://jomcgi.buildbuddy.io/invocation/<invocation_id>`

### Step 2: Investigate

1. **Get overview:** `bb view <invocation_id>` — check status, command, duration, failed targets
2. **Get logs:** `bb print --invocation_id=<id>` — search for error/fail/fatal messages
3. **AI diagnosis:** `bb ask "summarize the failure" --invocation_id=<id>` — BuildBuddy's built-in AI
4. **Download artifacts:** `bb download --invocation_id=<id> --output_path=/tmp/artifacts`

### Step 3: Reproduce Remotely

```bash
# Re-run the exact failing command on BuildBuddy cloud runners
bb remote test //path/to:target --config=ci
```

## API Fallback (curl)

For operations the `bb` CLI doesn't support (cache scorecard, execution details), use curl.
See `references/api-requests.md` for copy-paste templates.

> **Prefer `bb` CLI for all standard operations.** Only use curl for cache scorecards and execution-level detail.

## Tips

- `bb view` output includes target-level pass/fail — no need for a separate target query
- `bb ask` can answer specific questions: "which test failed?", "what changed?", "is this flaky?"
- Always `git rev-parse` short SHAs to full 40-char before using with BuildBuddy
- Reproduce locally with `bb remote test //... --config=ci`

````

**Step 2: Create references directory and api-requests.md**

```bash
mkdir -p .claude/skills/buildbuddy/references
````

Write `.claude/skills/buildbuddy/references/api-requests.md`:

````markdown
# BuildBuddy API Request Templates

> **Use `bb` CLI first.** These curl templates are fallback for operations the CLI doesn't support.

## Setup

```bash
# API key (already available in Goose sandboxes via BUILDBUDDY_API_KEY)
# For local use: bb login (stores in git config)
BB_URL="https://app.buildbuddy.io"
BB_API_KEY="${BUILDBUDDY_API_KEY}"
```
````

## GetInvocation

```bash
curl -s "${BB_URL}/api/v1/GetInvocation" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d '{"lookup":{"invocation_id":"'"${INVOCATION_ID}"'"}}' \
  | jq '.invocation[0] | {
    invocation_id: .invocation_id,
    success: .invocation_status,
    command: .command,
    pattern: .pattern,
    duration_usec: .duration_usec,
    commit_sha: .commit_sha,
    branch_name: .branch_name
  }'
```

## GetTarget (failed targets only)

```bash
curl -s "${BB_URL}/api/v1/GetTarget" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d '{"invocation_id":"'"${INVOCATION_ID}"'"}' \
  | jq '[.target[] | select(.status.status != 1) | {
    label: .id.target_id,
    status: .status
  }]'
```

## GetExecution (action-level details)

```bash
curl -s "${BB_URL}/api/v1/GetExecution" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d '{"execution_lookup":{"invocation_id":"'"${INVOCATION_ID}"'"}}' \
  | jq '[.execution[] | {
    action_digest: .action_digest,
    stage: .stage,
    status: .status,
    worker: .executed_action_metadata.worker
  }]'
```

## GetCacheScoreCard

```bash
curl -s "${BB_URL}/api/v1/GetCacheScoreCard" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d '{"invocation_id":"'"${INVOCATION_ID}"'","group_by":"GROUP_BY_TARGET"}' \
  | jq '{
    total_download_size_bytes: .score_card.total_download_size_bytes,
    total_upload_size_bytes: .score_card.total_upload_size_bytes,
    results: [.score_card.results[] | {
      target: .target_id,
      action_mnemonic: .action_mnemonic,
      cache_type: .cache_type,
      result: .result
    }]
  }'
```

## GetLog (paginated)

```bash
# First page
curl -s "${BB_URL}/api/v1/GetLog" \
  -H "Content-Type: application/json" \
  -H "x-buildbuddy-api-key: ${BB_API_KEY}" \
  -d '{"invocation_id":"'"${INVOCATION_ID}"'","page_token":""}' \
  | jq '{log: .log, next_page_token: .next_page_token}'

# Subsequent pages: set page_token to previous next_page_token
```

````

**Step 3: Commit**

```bash
git add .claude/skills/buildbuddy/SKILL.md .claude/skills/buildbuddy/references/api-requests.md
git commit -m "feat(buildbuddy): rewrite skill to use bb CLI instead of MCP tools

Replace MCP tool references with bb CLI commands (view, print, ask, remote).
Add curl/jq API request templates as fallback reference material."
````

---

### Task 2: Update `/bazel` Skill

Remove MCP tool references, teach `bb remote`, reference `/buildbuddy` for debugging.

**Files:**

- Modify: `.claude/skills/bazel/SKILL.md`

**Step 1: Update the skill**

Replace these sections in `.claude/skills/bazel/SKILL.md`:

1. In the **Overview** section, change the third bullet:
   - Old: `- **`/buildbuddy`** — debug CI failures via MCP tools`
   - New: `- **`/buildbuddy`** — debug CI failures via `bb` CLI`

2. In the **Writing BUILD Files > Querying Build Graph** section, update the comment and commands:
   - Old: `# These still work locally via bb CLI`
   - New: `# Run on BuildBuddy cloud runners (no local bazel server)`
   - Change `bazel query` to `bb remote query` (3 occurrences)

3. In the **Container Images > Updating Lock Files** section:
   - Change `bazel run @rules_apko//apko` to `bb remote run @rules_apko//apko`

4. Replace the entire **Debugging CI Failures** section:
   - Old: References MCP tools and `ToolSearch`
   - New:

     ```
     ## Debugging CI Failures

     Use the `/buildbuddy` skill or the `bb` CLI directly:

     1. Get invocation ID: `gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link'`
     2. View invocation: `bb view <invocation_id>`
     3. Get logs: `bb print --invocation_id=<id>`
     4. AI diagnosis: `bb ask "why did this fail?" --invocation_id=<id>`

     > **Important:** Always `git rev-parse` short SHAs to full 40-char before using with BuildBuddy.
     ```

5. Remove the **Cluster Inspection** section entirely (lines 101-103) — it's about MCP tools unrelated to Bazel.

**Step 2: Commit**

```bash
git add .claude/skills/bazel/SKILL.md
git commit -m "refactor(bazel): replace MCP tool references with bb CLI commands"
```

---

### Task 3: Add PreToolUse Hook — Redirect `bazel`/`bazelisk` to `bb remote`

Create a hook script that intercepts Bash commands containing `bazel ` or `bazelisk ` and suggests `bb remote` instead. Must exclude git commit messages (which may mention bazel in the message body).

**Files:**

- Create: `bazel/tools/hooks/prefer-bb-remote.sh`
- Modify: `.claude/settings.json` (add hook entry)

**Step 1: Create the hook script**

Write `bazel/tools/hooks/prefer-bb-remote.sh`:

```bash
#!/bin/bash
# PreToolUse hook: redirects bazel/bazelisk commands to bb remote.
# Blocks direct bazel invocations so all builds run on BuildBuddy cloud runners.
# Allows: git commit messages mentioning bazel, format command, bb commands
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the command
# Exit 2: block the command (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Allow git commits (message may mention bazel)
if [[ "$COMMAND" =~ ^git\ (commit|log|diff|show|rebase) ]]; then
	exit 0
fi

# Allow format command (runs gazelle which wraps bazel internally)
if [[ "$COMMAND" =~ ^format ]]; then
	exit 0
fi

# Allow bb commands (already using BuildBuddy CLI)
if [[ "$COMMAND" =~ ^bb\  ]] || [[ "$COMMAND" =~ /bb\  ]]; then
	exit 0
fi

# Block direct bazel/bazelisk invocations
if [[ "$COMMAND" =~ (^|[;&|])\ *bazel(isk)?\ ]] || [[ "$COMMAND" =~ (^|[;&|])\ *\.?/?bazel(isk)?\ ]]; then
	cat >&2 <<-'EOF'
		BLOCKED: Use `bb remote` instead of direct bazel/bazelisk commands.

		All Bazel commands should run on BuildBuddy cloud runners — no local bazel server.

		Examples:
		  bb remote test //...                    # Run all tests
		  bb remote build //path/to:target        # Build a target
		  bb remote query "deps(//path/to:target)" # Query build graph
		  bb remote run @rules_apko//apko -- lock path/to/apko.yaml

		For CI debugging, use the /buildbuddy skill or:
		  bb view <invocation_id>
		  bb print --invocation_id=<id>
		  bb ask "why did this fail?" --invocation_id=<id>
	EOF
	exit 2
fi

exit 0
```

**Step 2: Make executable**

```bash
chmod +x bazel/tools/hooks/prefer-bb-remote.sh
```

**Step 3: Add hook to settings.json**

In `.claude/settings.json`, add the new hook entry to the `PreToolUse[0].hooks` array (the Bash matcher), after the `prefer-argocd-mcp.sh` entry:

```json
{
  "type": "command",
  "command": "bazel/tools/hooks/prefer-bb-remote.sh",
  "timeout": 5
}
```

**Step 4: Commit**

```bash
git add bazel/tools/hooks/prefer-bb-remote.sh .claude/settings.json
git commit -m "feat: add PreToolUse hook to redirect bazel commands to bb remote"
```

---

### Task 4: Remove `prefer-buildbuddy-mcp.sh` Hook

Remove the hook that blocks `curl` to BuildBuddy API. Curl is now OK (but discouraged — skill says prefer `bb` CLI).

**Files:**

- Delete: `bazel/tools/hooks/prefer-buildbuddy-mcp.sh`
- Modify: `.claude/settings.json` (remove hook entry)

**Step 1: Delete the hook script**

```bash
git rm bazel/tools/hooks/prefer-buildbuddy-mcp.sh
```

**Step 2: Remove hook entry from settings.json**

In `.claude/settings.json`, remove these lines from the `PreToolUse[0].hooks` array:

```json
{
  "type": "command",
  "command": "bazel/tools/hooks/prefer-buildbuddy-mcp.sh",
  "timeout": 5
}
```

**Step 3: Commit**

```bash
git add bazel/tools/hooks/prefer-buildbuddy-mcp.sh .claude/settings.json
git commit -m "chore: remove prefer-buildbuddy-mcp hook (curl to API now allowed)"
```

> **Note:** Tasks 3 and 4 both modify `.claude/settings.json`. If done in separate commits, the second commit will include the combined state. Alternatively, combine Tasks 3 and 4 into a single commit.

---

### Task 5: Remove BuildBuddy MCP Server from Deployment

Remove the `buildbuddy-mcp` entry from the agent-platform Helm values.

**Files:**

- Modify: `projects/agent_platform/deploy/values.yaml` (lines 54-82)

**Step 1: Remove the buildbuddy-mcp server entry**

Delete the entire `- name: buildbuddy-mcp` block (lines 54-82) from the `agent-platform-mcp-servers.servers` list in `projects/agent_platform/deploy/values.yaml`.

**Step 2: Commit**

```bash
git add projects/agent_platform/deploy/values.yaml
git commit -m "chore(agent-platform): remove buildbuddy-mcp server from deployment"
```

---

### Task 6: Delete BuildBuddy MCP Server Code

Remove the entire `projects/agent_platform/buildbuddy_mcp/` directory.

**Files:**

- Delete: `projects/agent_platform/buildbuddy_mcp/` (entire directory — 12 files)

**Step 1: Delete the directory**

```bash
git rm -r projects/agent_platform/buildbuddy_mcp/
```

**Step 2: Commit**

```bash
git commit -m "chore(agent-platform): delete buildbuddy MCP server code

Replaced by bb CLI + /buildbuddy skill. See docs/plans/2026-03-14-buildbuddy-cli-skills-design.md"
```

---

### Task 7: Update CLAUDE.md

Remove BuildBuddy MCP references from the main project instructions.

**Files:**

- Modify: `.claude/CLAUDE.md`

**Step 1: Update the Cluster Investigation table**

Replace the **BuildBuddy CI** row:

- Old: `| **BuildBuddy CI**    | `buildbuddy-mcp-get-invocation`, `buildbuddy-mcp-get-log`, `buildbuddy-mcp-get-target`                    |`
- New: `| **BuildBuddy CI**    | Use `bb` CLI directly (`bb view`, `bb print`, `bb ask`) — see `/buildbuddy` skill                         |`

**Step 2: Update the CI section**

In the **Continuous Integration** section, the line:

```
Debug CI failures: use `/buildbuddy` skill or reproduce locally with `bazel test //... --config=ci`
```

Change to:

```
Debug CI failures: use `/buildbuddy` skill or reproduce with `bb remote test //... --config=ci`
```

**Step 3: Update Anti-Patterns**

Remove this anti-pattern (it no longer applies — we removed the hook):

```
- **Using kubectl/argocd CLI for cluster reads** — use MCP tools via Context Forge; PreToolUse hooks enforce this
```

Wait — that one is still valid (for kubectl/argocd). Leave it. No anti-pattern changes needed.

**Step 4: Update Essential Commands**

In the comment under Essential Commands:

```
Bazel runs **remotely via BuildBuddy CI** — not locally. Shell aliases route `bazel`/`bazelisk` to the BuildBuddy CLI (`bb`).
```

No change needed — this is still accurate.

**Step 5: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md to reference bb CLI instead of BuildBuddy MCP tools"
```

---

### Task 8: Clean Up BuildBuddy MCP Permissions

Remove BuildBuddy MCP tool permissions from settings files. These tools no longer exist.

**Files:**

- Modify: `.claude/settings.json` (remove `mcp__context-forge__buildbuddy-mcp-*` permissions)
- Modify: `.claude/settings.local.json` (remove BuildBuddy MCP tool permissions if present)

**Step 1: Clean up settings.json**

Remove these lines from the `permissions.allow` array in `.claude/settings.json`:

```
"mcp__context-forge__buildbuddy-mcp-execute-workflow",
"mcp__context-forge__buildbuddy-mcp-get-file",
"mcp__context-forge__buildbuddy-mcp-get-action",
"mcp__context-forge__buildbuddy-mcp-get-target",
"mcp__context-forge__buildbuddy-mcp-get-log",
"mcp__context-forge__buildbuddy-mcp-get-invocation",
```

**Step 2: Clean up settings.local.json**

Check `.claude/settings.local.json` for any `buildbuddy-mcp` permissions and remove them. This file accumulates per-session permissions — look for lines matching `buildbuddy-mcp` or `buildbuddy` in the allow list.

**Step 3: Add bb CLI permission**

Add `"Bash(bb:*)"` to the `permissions.allow` array in `.claude/settings.json` so the `bb` CLI is auto-allowed.

**Step 4: Commit**

```bash
git add .claude/settings.json .claude/settings.local.json
git commit -m "chore: clean up BuildBuddy MCP permissions, add bb CLI permission"
```

---

### Task 9: Add `bb` Binary to Goose Sandbox Image

Add the BuildBuddy CLI (`bb`) to the Goose agent container image so sandbox agents can use it directly.

**Files:**

- Modify: `projects/agent_platform/goose_agent/image/apko.yaml`

**Step 1: Check if `bb` is available as a wolfi package**

```bash
# Search for buildbuddy-cli or bb in wolfi packages
# If not available, we'll need to download the binary in a different way
```

The `bb` CLI is a Go binary distributed via GitHub releases at `https://github.com/buildbuddy-io/buildbuddy/releases`. It's NOT a wolfi package.

Since apko only supports wolfi packages, adding a custom binary requires either:

- (a) Creating a wolfi package (overkill)
- (b) Using a multi-stage approach with a separate download step
- (c) Adding it via the sandbox init script / workspace setup

The simplest approach: download `bb` in the Goose sandbox's workspace setup. The `SandboxTemplate` already clones the repo and runs setup — we can add `bb` installation there.

Alternatively, check if there's an existing mechanism for adding binaries to the image. Let the implementer investigate the current Goose image build pipeline and choose the simplest approach.

**Step 2: Add bb installation to sandbox setup**

This depends on the sandbox initialization mechanism. Options:

1. Add a `bb` download step to the goose agent's workspace setup script
2. Add `bb` to the bootstrap/tools setup

The implementer should:

1. Check how other CLI tools (like `gh`) are made available in the sandbox
2. Follow the same pattern for `bb`
3. `bb` v5.0.321 binary URL: `https://github.com/buildbuddy-io/buildbuddy/releases/download/cli-v5.0.321/bb-linux-amd64` (or `bb-linux-arm64`)

**Step 3: Commit**

```bash
git add <modified files>
git commit -m "feat(goose): add bb CLI to sandbox container image"
```

> **Note:** This task requires investigation of the image build pipeline. It may need a separate PR if the approach is complex. The `bb` CLI is not strictly required for the migration — agents can fall back to `curl` for API calls — but it's the preferred interface.

---

### Task 10: Fix Shell Alias (`bb` → BuildBuddy CLI)

The shell currently aliases `bb` to `bazelisk`. It should be the reverse: `bazel`/`bazelisk` aliased to `bb` (BuildBuddy CLI at `/usr/local/bin/bb`).

**Files:**

- This is a user environment change (shell profile, `.zshrc`, or direnv)
- Not a repo change — document in CLAUDE.md or skills

**Step 1: Verify current state**

```bash
which bb
type bb
/usr/local/bin/bb --help
```

**Step 2: Fix alias**

The user should update their shell config so that:

- `bb` resolves to `/usr/local/bin/bb` (BuildBuddy CLI) — remove any alias
- `bazel` and `bazelisk` alias to `bb` (so all bazel commands go through BuildBuddy)

This is already documented in CLAUDE.md: "Shell aliases route `bazel`/`bazelisk` to the BuildBuddy CLI (`bb`)"

The fix is: remove the `bb` → `bazelisk` alias, add `bazel` → `bb` and `bazelisk` → `bb` aliases.

**Step 3: No commit needed** — this is a local environment fix, not a repo change.

---

### Task 11: Run `format` and Verify

Run the format command to ensure BUILD files are updated after deleting the BuildBuddy MCP directory.

**Files:**

- Potentially modified: Various `BUILD` files (auto-generated)

**Step 1: Run format**

```bash
format
```

**Step 2: Check for changes**

```bash
git diff
git status
```

**Step 3: Commit any format changes**

```bash
git add -A
git commit -m "style: run format after removing buildbuddy MCP server"
```

---

### Task 12: Create PR

**Step 1: Push branch**

```bash
git push -u origin feat/buildbuddy-cli-skills
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: replace BuildBuddy MCP server with bb CLI + skills" --body "$(cat <<'EOF'
## Summary

- Rewrite `/buildbuddy` skill to use `bb` CLI (`view`, `print`, `ask`, `remote`) instead of MCP tools
- Add PreToolUse hook redirecting `bazel`/`bazelisk` commands to `bb remote`
- Remove BuildBuddy MCP server (code, deployment, hook, permissions)
- Update `/bazel` skill and CLAUDE.md to reference `bb` CLI
- Add `bb` CLI permission to settings

## What This Eliminates

- 1 container image (build, push, deploy cycle)
- 1 MCP server registration job
- 1 HTTPCheck health alert
- 1 ArgoCD Image Updater config
- ~550 lines of Python code + tests
- 8 MCP tools from Context Forge gateway (71 → 63 tools)

## What's New

- `/buildbuddy` skill teaches `bb view`, `bb print`, `bb ask`, `bb remote`
- `references/api-requests.md` has curl/jq fallback templates
- PreToolUse hook blocks direct bazel/bazelisk → suggests `bb remote`

## Test Plan

- [ ] Verify `bb view <invocation_id>` works with a real invocation
- [ ] Verify `bb print --invocation_id=<id>` returns logs
- [ ] Verify `bb remote test //...` runs tests on BuildBuddy
- [ ] Verify PreToolUse hook blocks `bazel test //...` with helpful message
- [ ] Verify PreToolUse hook allows `git commit -m "fix bazel test"`
- [ ] Verify PreToolUse hook allows `format` command
- [ ] Verify ArgoCD syncs after removing buildbuddy-mcp deployment entry
- [ ] Verify no orphaned pods/services from buildbuddy-mcp after sync
- [ ] CI passes (format check + bazel test)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Verify CI**

```bash
gh pr checks <number>
```
