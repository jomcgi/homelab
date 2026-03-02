# BuildBuddy MCP Server - Design

## Summary

Python MCP server wrapping the BuildBuddy REST API, built with FastMCP. Provides 6 tools (5 read-only + 1 workflow trigger) for CI/CD debugging directly from MCP clients. Packaged as a dual-arch OCI image via the repo's `py3_image` macro.

## Decisions

- **Framework:** FastMCP v3 (wraps official `mcp` SDK, decorator-based tool definition)
- **Transport:** Streamable-HTTP via `mcp.run(transport="http")`
- **Config:** Pydantic `BaseSettings` with `BUILDBUDDY_` env prefix, no defaults for `api_key` or `url`
- **Tool design:** Thin wrappers only — one MCP tool per BuildBuddy API endpoint
- **Scope:** Image only — no Helm chart, no cluster deployment, no Context Forge registration

## Structure

```
services/buildbuddy_mcp/
├── __init__.py
├── app/
│   ├── __init__.py
│   ├── BUILD
│   └── main.py        # FastMCP server, tools, Settings, httpx client
├── tests/
│   ├── BUILD
│   └── main_test.py
└── BUILD               # py3_image
```

## Configuration

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUILDBUDDY_")

    api_key: str      # required
    url: str          # required
    port: int = 8000
```

## Tools

| Tool               | Endpoint           | Read/Write | Purpose                                       |
| ------------------ | ------------------ | ---------- | --------------------------------------------- |
| `get_invocation`   | `/GetInvocation`   | Read       | Build metadata by invocation ID or commit SHA |
| `get_log`          | `/GetLog`          | Read       | Build logs (paginated)                        |
| `get_target`       | `/GetTarget`       | Read       | Target labels, status, timing                 |
| `get_action`       | `/GetAction`       | Read       | Action details, test shard/run info           |
| `get_file`         | `/GetFile`         | Read       | Download file by bytestream URI               |
| `execute_workflow` | `/ExecuteWorkflow` | Write      | Re-trigger CI workflow runs                   |

## HTTP Client

Module-level async `httpx.AsyncClient` with API key header:

```python
settings = Settings()
client = httpx.AsyncClient(
    base_url=f"{settings.url}/api/v1",
    headers={
        "x-buildbuddy-api-key": settings.api_key,
        "Content-Type": "application/json",
    },
)
```

## Container Image

```python
py3_image(
    name = "image",
    binary = "//services/buildbuddy_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/buildbuddy-mcp",
)
```

Dual-arch (amd64 + arm64) on Chainguard Python 3.13 base.

## Dependencies

- `fastmcp` — new, add to `pyproject.toml` + regenerate lockfile
- `httpx` — already in lockfile
- `pydantic-settings` — already in lockfile

## Out of Scope

- Helm chart / Kubernetes manifests
- Context Forge registration
- Composite/higher-level tools
- OpenTelemetry instrumentation (FastMCP includes it if needed later)
