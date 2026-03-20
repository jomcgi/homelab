# Todo MCP Server

AI assistant interface for the todo-admin app, implemented as a [FastMCP](https://github.com/jlowin/fastmcp) server.

## Overview

Exposes MCP tools so AI assistants can read and update todo tasks via the todo-admin API. The server acts as a thin HTTP proxy — all state lives in the underlying Go todo service.

## MCP Tools

| Tool           | Description                                                |
| -------------- | ---------------------------------------------------------- |
| `get_tasks`    | Get current weekly focus task and up to 3 daily tasks      |
| `set_tasks`    | Update all tasks (weekly + 3 daily slots)                  |
| `reset_daily`  | Archive today's tasks and clear the 3 daily slots          |
| `reset_weekly` | Archive and clear all tasks (weekly + daily)               |

## Tech Stack

- Python + [FastMCP](https://github.com/jlowin/fastmcp)
- httpx for async HTTP requests to the todo admin API
- pydantic-settings for configuration

## Configuration

| Variable    | Description                         | Default |
| ----------- | ----------------------------------- | ------- |
| `TODO_URL`  | Base URL of the todo admin API      | required |
| `TODO_PORT` | Port for the MCP HTTP server        | `8000`  |

## Running Locally

```bash
export TODO_URL=http://localhost:8080
bazel run //projects/todo_app/todo_mcp:main
```

## Related

- `projects/todo_app/` — The todo Go API and nginx deployment
