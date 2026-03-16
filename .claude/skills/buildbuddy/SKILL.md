---
name: buildbuddy
description: Use when debugging failed CI/CD jobs, analyzing build logs, or investigating build failures. Uses the bb CLI and curl fallback for BuildBuddy remote build execution insights.
---

# BuildBuddy - CI Debugging with `bb` CLI

## Tools

| Command       | Purpose                                           |
| ------------- | ------------------------------------------------- |
| `bb view`     | Show invocation metadata, status, targets, timing |
| `bb print`    | Print build/test logs for an invocation           |
| `bb ask`      | Ask natural-language questions about a build      |
| `bb remote`   | Run builds/tests remotely via BuildBuddy RBE      |
| `bb download` | Download artifacts from an invocation             |

## Authentication

- **Claude Code (local):** Uses git credential config. Run `bb login` if not configured.
- **Goose sandboxes:** Set `BUILDBUDDY_API_KEY` env var.

## Debugging Failed CI

```
PR fails
  │
  ▼
gh pr checks ──► extract invocation ID from BuildBuddy URL
  │
  ▼
bb view <invocation_id> ──► check status, failed targets, duration
  │
  ▼
bb print <invocation_id> ──► read build/test logs for errors
  │
  ▼
bb ask <invocation_id> "why did this fail?" ──► AI-assisted diagnosis
  │
  ▼
Fix root cause ──► push ──► verify
```

### Step 1: Get the Invocation ID

From a PR:

```bash
gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link' | grep -o '[^/]*$' | head -1
```

From a commit SHA (must be full 40-char SHA):

```bash
# Always expand short SHAs first
FULL_SHA=$(git rev-parse <short_sha>)
```

The invocation ID is the last path segment of the BuildBuddy URL:
`https://jomcgi.buildbuddy.io/invocation/<invocation_id>`

### Step 2: Investigate

```bash
# Overview — status, targets, timing
bb view <invocation_id>

# Full build/test logs
bb print <invocation_id>

# Ask specific questions about the failure
bb ask <invocation_id> "which targets failed and why?"
bb ask <invocation_id> "show me the test error output"

# Download build artifacts
bb download --invocation_id=<invocation_id> --output_path=/tmp/artifacts
```

`bb view` output includes target-level pass/fail info, so start there before reading full logs.

### Step 3: Reproduce

```bash
# Run the failing test remotely via BuildBuddy RBE
bb remote test //path/to:target --config=ci

# Run all tests (mirrors CI)
bb remote test //... --config=ci
```

## API Fallback

If `bb` CLI is unavailable, use curl with the BuildBuddy API.
See `references/api-requests.md` for request templates.

## Tips

- `bb view` includes target info — check it before pulling full logs with `bb print`
- `bb ask` accepts natural-language questions and can pinpoint failures quickly
- Always `git rev-parse` short SHAs to full 40-char SHAs — short SHAs silently fail
- BuildBuddy logs can be large — `bb print` handles pagination automatically
- Reproduce locally with `bazel test //... --config=ci` (routes through `bb` alias)
