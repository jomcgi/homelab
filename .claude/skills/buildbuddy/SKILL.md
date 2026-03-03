---
name: buildbuddy
description: Use when debugging failed CI/CD jobs, analyzing build logs, or investigating GitHub Actions failures. Access BuildBuddy remote build execution and caching service for detailed build insights.
---

# BuildBuddy - Remote Build Execution & CI Debugging

## MCP Tools (Primary Interface)

Use BuildBuddy MCP tools via Context Forge. MCP handles authentication automatically.

Load tools with: `ToolSearch` query `+buildbuddy`

| Tool                              | Purpose                            |
| --------------------------------- | ---------------------------------- |
| `buildbuddy-mcp-get-invocation`   | Build metadata, status, duration   |
| `buildbuddy-mcp-get-log`          | Full build logs (stdout/stderr)    |
| `buildbuddy-mcp-get-target`       | Target information and results     |
| `buildbuddy-mcp-get-action`       | Action details and execution info  |
| `buildbuddy-mcp-get-file`         | Download files by URI              |
| `buildbuddy-mcp-execute-workflow` | Trigger a BuildBuddy workflow      |

## Debugging Failed CI

### Workflow

```
GitHub PR fails
      │
      ▼
gh pr checks ──► extract invocation ID from BuildBuddy URL
      │
      ▼
ToolSearch +buildbuddy ──► load MCP tools
      │
      ▼
buildbuddy-mcp-get-invocation ──► check success/failure, duration
      │
      ▼
buildbuddy-mcp-get-log ──► find error messages
      │
      ▼
Parse errors ──► fix root cause
```

### Step 1: Get the Invocation ID

```bash
# Extract invocation ID from PR check links
gh pr checks --json link | jq -r '.[] | select(.link | contains("buildbuddy")) | .link' | grep -o '[^/]*$' | head -1
```

The invocation ID is the last path segment of the BuildBuddy URL:
`https://jomcgi.buildbuddy.io/invocation/<invocation_id>`

### Step 2: Investigate with MCP Tools

Use the invocation ID with MCP tools — no API key or curl needed:

1. **Get overview:** `buildbuddy-mcp-get-invocation` — check `.invocation.success`, command, duration
2. **Get logs:** `buildbuddy-mcp-get-log` — search for error/fail/fatal messages
3. **Get targets:** `buildbuddy-mcp-get-target` — find which targets failed
4. **Get actions:** `buildbuddy-mcp-get-action` — dig into specific action failures
5. **Get files:** `buildbuddy-mcp-get-file` — download test outputs or artifacts

## Tips

- Reproduce locally with `bazel test //... --config=ci`
- BuildBuddy logs may be paginated — use page tokens for large logs
- Check `.invocation.success` boolean to quickly determine pass/fail
- A PreToolUse hook blocks direct `curl` to the BuildBuddy API — use MCP tools instead
