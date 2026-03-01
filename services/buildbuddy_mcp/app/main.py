"""BuildBuddy MCP server."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUILDBUDDY_")

    api_key: str
    url: str
    port: int = 8000


mcp = FastMCP("BuildBuddy")

settings = Settings()

_client = httpx.AsyncClient(
    base_url=f"{settings.url}/api/v1",
    headers={
        "x-buildbuddy-api-key": settings.api_key,
        "Content-Type": "application/json",
    },
)


async def _post(endpoint: str, body: dict) -> dict:
    """POST to a BuildBuddy API endpoint and return parsed JSON."""
    resp = await _client.post(endpoint, json=body)
    resp.raise_for_status()
    return resp.json()


@mcp.tool
async def get_invocation(
    invocation_id: str | None = None,
    commit_sha: str | None = None,
    page_token: str | None = None,
) -> dict:
    """Get build invocation details by invocation ID or commit SHA.

    Returns build metadata including success status, duration, command,
    repo URL, branch, and bazel exit code.
    """
    selector = {}
    if invocation_id:
        selector["invocation_id"] = invocation_id
    if commit_sha:
        selector["commit_sha"] = commit_sha
    body: dict = {"selector": selector}
    if page_token:
        body["page_token"] = page_token
    return await _post("/GetInvocation", body)


@mcp.tool
async def get_log(
    invocation_id: str,
    page_token: str | None = None,
) -> dict:
    """Get build logs for an invocation.

    Returns the build log contents as a string. Logs may be paginated
    for large builds — use page_token to fetch subsequent pages.
    """
    body: dict = {"selector": {"invocation_id": invocation_id}}
    if page_token:
        body["page_token"] = page_token
    return await _post("/GetLog", body)


@mcp.tool
async def get_target(
    invocation_id: str,
    target_id: str | None = None,
    tag: str | None = None,
    label: str | None = None,
    page_token: str | None = None,
) -> dict:
    """Get targets for an invocation.

    Returns target labels, statuses (PASSED/FAILED/FLAKY), timing, rule
    types, and languages. Filter by target_id, tag, or label.
    """
    selector: dict = {"invocation_id": invocation_id}
    if target_id:
        selector["target_id"] = target_id
    if tag:
        selector["tag"] = tag
    if label:
        selector["label"] = label
    body: dict = {"selector": selector}
    if page_token:
        body["page_token"] = page_token
    return await _post("/GetTarget", body)


def main():
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
