"""Todo-admin MCP server."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TODO_")

    url: str
    port: int = 8000


mcp = FastMCP("Todo")

_client: httpx.AsyncClient | None = None


def configure(settings: Settings) -> None:
    """Configure the HTTP client with the given settings."""
    global _client
    _client = httpx.AsyncClient(base_url=settings.url)


async def _request(method: str, path: str, **kwargs) -> dict:
    """Make an HTTP request to the todo-admin API.

    Returns an error dict on HTTP failures instead of raising, so FastMCP
    output schema validation gets a valid dict rather than an exception.
    """
    try:
        resp = await _client.request(method, path, **kwargs)
        if not resp.is_success:
            return {"error": f"Todo API error: {resp.status_code} {resp.text}"}
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        return resp.json()
    except Exception as e:
        return {"error": f"Todo API request failed: {e}"}


@mcp.tool
async def get_tasks() -> dict:
    """Get current todo tasks.

    Returns the weekly focus task and up to 3 daily tasks, each with
    a task description and done status.
    """
    return await _request("GET", "/api/todo")


@mcp.tool
async def set_tasks(
    weekly_task: str,
    weekly_done: bool,
    daily_1_task: str,
    daily_1_done: bool,
    daily_2_task: str,
    daily_2_done: bool,
    daily_3_task: str,
    daily_3_done: bool,
) -> dict:
    """Update todo tasks.

    Sets the weekly focus task and 3 daily tasks. Always provide all fields
    — call get_tasks first to read current state, then modify what you need.

    Use empty string for unused daily task slots.
    """
    state = {
        "weekly": {"task": weekly_task, "done": weekly_done},
        "daily": [
            {"task": daily_1_task, "done": daily_1_done},
            {"task": daily_2_task, "done": daily_2_done},
            {"task": daily_3_task, "done": daily_3_done},
        ],
    }
    return await _request("PUT", "/api/todo", json=state)


@mcp.tool
async def reset_daily() -> dict:
    """Reset daily tasks.

    Archives today's tasks to the historical record and clears the 3 daily
    task slots. The weekly task is preserved. This triggers a git commit
    in the todo-admin backend.
    """
    return await _request("POST", "/api/reset/daily")


@mcp.tool
async def reset_weekly() -> dict:
    """Reset weekly and daily tasks.

    Archives today's tasks and clears ALL task slots (weekly + daily).
    Normally runs automatically on Saturday midnight PST.
    This triggers a git commit in the todo-admin backend.
    """
    return await _request("POST", "/api/reset/weekly")


def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
