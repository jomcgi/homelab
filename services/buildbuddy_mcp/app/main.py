"""BuildBuddy MCP server."""

from __future__ import annotations

import re

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ERROR_RE = re.compile(
    r"(ERROR|FAIL|FAILED|TIMEOUT|FATAL|error:|failure:)", re.IGNORECASE
)
_SUMMARY_RE = re.compile(r"Executed \d+ out of \d+ tests?:")


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

    IMPORTANT: commit_sha must be a full 40-character hex SHA. Short SHAs
    (e.g. "88a97bd0") will return no results. Use `git rev-parse <short>`
    to resolve before calling.

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
    errors_only: bool = False,
    page_token: str | None = None,
) -> dict:
    """Get build logs for an invocation.

    Returns the build log contents as a string. Logs may be paginated
    for large builds — use page_token to fetch subsequent pages.

    Set errors_only=True to fetch all pages, strip ANSI codes, and return
    only error/failure lines with 3 lines of surrounding context plus
    the final test summary line. Much smaller output for CI debugging.
    """
    if not errors_only:
        body: dict = {"selector": {"invocation_id": invocation_id}}
        if page_token:
            body["page_token"] = page_token
        return await _post("/GetLog", body)

    # errors_only: fetch all pages, filter to error lines
    all_text = []
    token = page_token
    while True:
        body: dict = {"selector": {"invocation_id": invocation_id}}
        if token:
            body["page_token"] = token
        result = await _post("/GetLog", body)
        if "error" in result:
            return result
        contents = result.get("log", {}).get("contents", "")
        all_text.append(contents)
        token = result.get("next_page_token") or result.get("nextPageToken")
        if not token:
            break

    full_log = "".join(all_text)
    clean_log = _ANSI_RE.sub("", full_log)
    lines = clean_log.splitlines()

    context_radius = 2
    matched_indices: set[int] = set()
    summary_line = None

    for i, line in enumerate(lines):
        if _ERROR_RE.search(line):
            for j in range(
                max(0, i - context_radius), min(len(lines), i + context_radius + 1)
            ):
                matched_indices.add(j)
        if _SUMMARY_RE.search(line):
            summary_line = line

    filtered = [lines[i] for i in sorted(matched_indices)]
    if summary_line and summary_line not in filtered:
        filtered.append(summary_line)

    return {"log": {"contents": "\n".join(filtered)}}


@mcp.tool
async def get_target(
    invocation_id: str,
    target_id: str | None = None,
    tag: str | None = None,
    label: str | None = None,
    status: str | None = None,
    page_token: str | None = None,
) -> dict:
    """Get targets for an invocation.

    Returns target labels, statuses (PASSED/FAILED/FLAKY), timing, rule
    types, and languages. Filter by target_id, tag, or label.

    The status parameter is a client-side filter (not supported by the API).
    When set, all pages are fetched and only targets matching the given
    status are returned. Use status="FAILED" to find failing tests.
    """
    selector: dict = {"invocation_id": invocation_id}
    if target_id:
        selector["target_id"] = target_id
    if tag:
        selector["tag"] = tag
    if label:
        selector["label"] = label

    if status:
        # Client-side filter: fetch all pages and filter
        all_targets = []
        token = page_token
        while True:
            body: dict = {"selector": selector}
            if token:
                body["page_token"] = token
            result = await _post("/GetTarget", body)
            if "error" in result:
                return result
            all_targets.extend(result.get("target", []))
            token = result.get("next_page_token")
            if not token:
                break
        filtered = [t for t in all_targets if t.get("status") == status]
        return {"target": filtered}

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

    Use target_label or target_id to scope results to a single target.
    action_id alone returns all targets sharing that ID — always combine
    with target_id for a single result.
    configuration_id is a bazel configuration hash, useful for precise lookups.
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
    """Download a file by its bytestream URI and decode as text.

    Use URIs from get_action file references. Returns decoded UTF-8 text
    contents. Returns an error for binary files that can't be decoded.
    """
    import base64

    result = await _post("/GetFile", {"uri": uri})
    if "error" in result:
        return result
    data = result.get("data", "")
    if not data:
        return {"error": "Empty file data returned"}
    try:
        raw = base64.b64decode(data)
        contents = raw.decode("utf-8")
        return {"contents": contents}
    except UnicodeDecodeError:
        return {
            "error": "Binary file, cannot display as text",
            "size_bytes": len(raw),
        }
    except Exception as e:
        return {"error": f"Failed to decode file: {e}"}


@mcp.tool
async def execute_workflow(
    repo_url: str,
    branch: str | None = None,
    commit_sha: str | None = None,
    action_names: list[str] | None = None,
    run_async: bool = True,
    env: dict[str, str] | None = None,
    visibility: str | None = None,
    disable_retry: bool = False,
) -> dict:
    """Trigger a BuildBuddy workflow run.

    Re-runs CI for a repo/branch/commit. Returns invocation IDs for
    each triggered action. Runs async by default.

    Use action_names to run specific actions from buildbuddy.yaml
    (e.g. ["Format check"]). Set env to override environment variables.
    """
    body: dict = {"repo_url": repo_url, "async": run_async}
    if branch:
        body["branch"] = branch
    if commit_sha:
        body["commit_sha"] = commit_sha
    if action_names:
        body["action_names"] = action_names
    if env:
        body["env"] = env
    if visibility:
        body["visibility"] = visibility
    if disable_retry:
        body["disable_retry"] = True
    return await _post("/ExecuteWorkflow", body)


@mcp.tool
async def run(
    repo_url: str,
    steps: list[str],
    branch: str | None = None,
    commit_sha: str | None = None,
    env: dict[str, str] | None = None,
    timeout: str | None = None,
    wait_until: str = "COMPLETED",
) -> dict:
    """Run commands on a remote BuildBuddy runner.

    Each string in steps becomes a bash command executed in order.
    Use for running bazel query, reproducing test failures, or any
    remote command without needing bazel locally.

    wait_until controls when the response is returned:
    QUEUED (immediate), STARTED (after runner starts), COMPLETED (after finish).
    """
    body: dict = {
        "repo": repo_url,
        "steps": [{"run": step} for step in steps],
        "wait_until": wait_until,
    }
    if branch:
        body["branch"] = branch
    if commit_sha:
        body["commit_sha"] = commit_sha
    if env:
        body["env"] = env
    if timeout:
        body["timeout"] = timeout
    return await _post("/Run", body)


import services.buildbuddy_mcp.app.composite as _composite  # noqa: F401, E402


def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
