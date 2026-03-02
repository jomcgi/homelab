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

_client: httpx.AsyncClient | None = None


def configure(settings: Settings) -> None:
    """Configure the HTTP client with the given settings."""
    global _client
    _client = httpx.AsyncClient(
        base_url=f"{settings.url}/api/v1",
        headers={
            "x-buildbuddy-api-key": settings.api_key,
            "Content-Type": "application/json",
        },
    )


async def _post(endpoint: str, body: dict) -> dict:
    """POST to a BuildBuddy API endpoint and return parsed JSON.

    Returns an error dict on HTTP failures instead of raising, so FastMCP
    output schema validation gets a valid dict rather than an exception.
    """
    try:
        resp = await _client.post(endpoint, json=body)
        if not resp.is_success:
            return {"error": f"BuildBuddy API error: {resp.status_code} {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"error": f"BuildBuddy API request failed: {e}"}


@mcp.tool
async def get_invocation(
    invocation_id: str | None = None,
    commit_sha: str | None = None,
    include_child_invocations: bool = False,
    include_metadata: bool = False,
    include_artifacts: bool = False,
    page_token: str | None = None,
) -> dict:
    """Get build invocation details by invocation ID or commit SHA.

    Returns build metadata including success status, duration, command,
    repo URL, branch, and bazel exit code.

    Set include_child_invocations=True to get inner bazel invocation IDs
    from workflow runs (needed to navigate to test results).
    """
    selector = {}
    if invocation_id:
        selector["invocation_id"] = invocation_id
    if commit_sha:
        selector["commit_sha"] = commit_sha
    body: dict = {"selector": selector}
    if include_child_invocations:
        body["include_child_invocations"] = True
    if include_metadata:
        body["include_metadata"] = True
    if include_artifacts:
        body["include_artifacts"] = True
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


@mcp.tool
async def get_action(
    invocation_id: str,
    target_id: str | None = None,
    configuration_id: str | None = None,
    action_id: str | None = None,
    target_label: str | None = None,
    page_token: str | None = None,
) -> dict:
    """Get actions for a target in an invocation.

    Returns action details including test shard, run, and attempt info,
    plus file references (test logs, outputs) with bytestream URIs.
    """
    selector: dict = {"invocation_id": invocation_id}
    if target_id:
        selector["target_id"] = target_id
    if configuration_id:
        selector["configuration_id"] = configuration_id
    if action_id:
        selector["action_id"] = action_id
    if target_label:
        selector["target_label"] = target_label
    body: dict = {"selector": selector}
    if page_token:
        body["page_token"] = page_token
    return await _post("/GetAction", body)


@mcp.tool
async def get_file(uri: str) -> dict:
    """Download a file by its bytestream URI.

    Use URIs from get_action file references. Supports ZSTD-compressed
    variants (append /compressed-blobs/zstd/ to URI).
    """
    return await _post("/GetFile", {"uri": uri})


@mcp.tool
async def execute_workflow(
    repo_url: str,
    branch: str | None = None,
    commit_sha: str | None = None,
    action_names: list[str] | None = None,
    run_async: bool = True,
) -> dict:
    """Trigger a BuildBuddy workflow run.

    Re-runs CI for a repo/branch/commit. Returns invocation IDs for
    each triggered action. Runs async by default.
    """
    body: dict = {"repo_url": repo_url, "async": run_async}
    if branch:
        body["branch"] = branch
    if commit_sha:
        body["commit_sha"] = commit_sha
    if action_names:
        body["action_names"] = action_names
    return await _post("/ExecuteWorkflow", body)


def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
