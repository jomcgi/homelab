# Agent Orchestrator MCP Server Design

## Overview

A Python FastMCP service that wraps the agent orchestrator REST API as MCP tools, registered with Context Forge for use in Claude Code conversations.

## Architecture

Follows the established pattern from `buildbuddy_mcp` and `todo_mcp`:

- **Language:** Python (FastMCP + httpx)
- **Transport:** STREAMABLEHTTP (native, no translate sidecar)
- **Location:** `services/agent_orchestrator_mcp/`
- **Deployment:** Entry in `charts/mcp-servers/` values, registered with Context Forge gateway

## MCP Tools

| Tool | HTTP Method | Path | Description |
|------|-------------|------|-------------|
| `submit_job` | POST | `/jobs` | Submit a new agent job (task, profile, max_retries, source) |
| `list_jobs` | GET | `/jobs` | List jobs with optional status filter, limit, offset |
| `get_job` | GET | `/jobs/{id}` | Get single job with all attempt details |
| `cancel_job` | POST | `/jobs/{id}/cancel` | Cancel a pending or running job |
| `get_job_output` | GET | `/jobs/{id}/output` | Get latest attempt output (last 32KB) |

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `ORCHESTRATOR_URL` | — | Base URL of agent orchestrator service |
| `ORCHESTRATOR_PORT` | `8000` | MCP server listen port |

In-cluster URL: `http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080`

## File Structure

```
services/agent_orchestrator_mcp/
├── __init__.py
├── BUILD
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── BUILD
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── main_test.py
    └── BUILD
```

## Deployment

Added to `overlays/prod/mcp-servers/values.yaml` with:
- Image auto-update via ArgoCD Image Updater
- STREAMABLEHTTP registration with gateway
- Health check alert
- No secrets (orchestrator has no auth in MVP)

## Tool Permissions

5 entries added to `.claude/settings.json` allowlist.
