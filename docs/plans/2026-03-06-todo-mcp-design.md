# Todo-Admin MCP Server Design

## Purpose

An MCP server that lets Claude interact with the todo-admin app — reading and writing tasks, resetting daily/weekly — so users can discuss, plan, and manage their tasks conversationally.

## Architecture

Thin Python FastMCP HTTP proxy over the todo-admin REST API. Deployed as an entry in the shared `charts/mcp-servers` Helm chart, registered with Context Forge gateway.

```
Claude → Context Forge Gateway → todo-mcp (FastMCP) → todo-admin API (Go)
```

No secrets required — the todo-admin API is unauthenticated within the cluster (Cloudflare Access protects external access only).

## MCP Tools

| Tool           | HTTP Method | Endpoint            | Description                           |
| -------------- | ----------- | ------------------- | ------------------------------------- |
| `get_tasks`    | GET         | `/api/todo`         | Returns full state (weekly + 3 daily) |
| `set_tasks`    | PUT         | `/api/todo`         | Updates weekly and/or daily tasks     |
| `reset_daily`  | POST        | `/api/reset/daily`  | Archives today, clears daily tasks    |
| `reset_weekly` | POST        | `/api/reset/weekly` | Archives today, clears all tasks      |

### Tool Details

**`get_tasks`** — No parameters. Returns:

```json
{
  "weekly": { "task": "string", "done": false },
  "daily": [
    { "task": "string", "done": false },
    { "task": "string", "done": false },
    { "task": "string", "done": false }
  ]
}
```

**`set_tasks`** — Accepts full state object (same shape as above). Sends PUT to `/api/todo`.

**`reset_daily`** / **`reset_weekly`** — No parameters. Triggers archival and task clearing.

## Implementation

### Source Code

```
services/todo_mcp/
├── __init__.py
├── BUILD
├── app/
│   ├── __init__.py
│   ├── main.py          # FastMCP server + tools
│   └── BUILD
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── main_test.py
    └── BUILD
```

Follows the `buildbuddy_mcp` pattern exactly:

- `pydantic_settings.BaseSettings` for config (`TODO_URL`, `TODO_PORT`)
- `httpx.AsyncClient` for HTTP calls
- `@mcp.tool` decorated async functions
- Error handling returns dicts (not exceptions)
- `setup_telemetry("todo-mcp")` for OpenTelemetry integration

### Dependencies

- `@pip//fastmcp`
- `@pip//httpx`
- `@pip//pydantic_settings`
- `@pip//opentelemetry_api` (via `setup_telemetry`)

### Container Image

Built with `py3_image` macro (same as buildbuddy-mcp):

```python
py3_image(
    name = "image",
    binary = "//services/todo_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/todo-mcp",
)
```

### Deployment

New entry in `overlays/prod/mcp-servers/values.yaml`:

```yaml
- name: todo-mcp
  image:
    repository: ghcr.io/jomcgi/homelab/services/todo-mcp
    tag: "main"
  port: 8000
  podAnnotations:
    instrumentation.opentelemetry.io/inject-python: "python"
  env:
    - name: TODO_URL
      value: "http://todo.todo.svc.cluster.local:8080"
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 128Mi
  translate:
    enabled: false
  registration:
    enabled: true
    transport: "STREAMABLEHTTP"
  imageUpdater:
    enabled: true
  alert:
    enabled: true
    url: "http://todo-mcp.mcp-servers.svc.cluster.local:8000/health"
```

## Testing

- Unit tests mock the httpx client and verify each tool calls the correct endpoint
- `conftest.py` provides a shared mock client fixture
- Verify with `bazel test //services/todo_mcp/...`

## What This Enables

Once deployed, Claude can:

- **Read tasks**: "What's on my todo list?" → calls `get_tasks`
- **Update tasks**: "Add 'review PR' as my second daily task" → calls `set_tasks`
- **Mark done**: "Mark the weekly task as done" → calls `get_tasks` then `set_tasks` with `done: true`
- **Reset**: "Reset my daily tasks" → calls `reset_daily`
- **Discuss**: "What should I focus on today?" → reads tasks and provides suggestions
