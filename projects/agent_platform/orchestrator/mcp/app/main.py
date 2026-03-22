"""Agent Orchestrator MCP server."""

from __future__ import annotations

import logging

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRATOR_")

    url: str
    port: int = 8000


logger = logging.getLogger(__name__)

mcp = FastMCP("AgentOrchestrator")

_client: httpx.AsyncClient | None = None


def configure(settings: Settings) -> None:
    """Configure the HTTP client with the given settings."""
    global _client
    _client = httpx.AsyncClient(base_url=settings.url, timeout=30.0)


async def _request(method: str, path: str, **kwargs) -> dict:
    """Make an HTTP request to the agent orchestrator API.

    Returns an error dict on HTTP failures instead of raising, so FastMCP
    output schema validation gets a valid dict rather than an exception.
    """
    try:
        resp = await _client.request(method, path, **kwargs)
        if not resp.is_success:
            return {"error": f"Orchestrator API error: {resp.status_code} {resp.text}"}
        return resp.json()
    except Exception as e:
        logger.warning("Orchestrator API request failed: %s", e)
        return {"error": f"Orchestrator API request failed: {e}"}


@mcp.tool
async def submit_job(
    task: str,
    profile: str | None = None,
    max_retries: int | None = None,
    source: str | None = None,
) -> dict:
    """Submit a new agent job for execution.

    Creates a job that runs the given task in an isolated Kubernetes sandbox
    using a Goose AI agent. The job is queued and executed asynchronously.

    Args:
        task: Description of what the agent should do (required).
        profile: Optional recipe profile — "ci-debug" or "code-fix".
            Empty means default goose config with all tools.
        max_retries: Override default retry count (0-10). On failure,
            retries inherit context from previous attempt output.
        source: Origin tag — "api", "github", or "cli". Defaults to "api".

    Returns the job ID, status (always PENDING), and creation timestamp.
    """
    body: dict = {"task": task}
    if profile is not None:
        body["profile"] = profile
    if max_retries is not None:
        body["max_retries"] = max_retries
    if source is not None:
        body["source"] = source
    return await _request("POST", "/jobs", json=body)


@mcp.tool
async def list_jobs(
    status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List agent jobs with optional filtering and pagination.

    Returns jobs sorted by creation time (newest first) with a total count.

    Args:
        status: Comma-separated status filter — e.g. "RUNNING,PENDING".
            Valid values: PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED.
        limit: Results per page (default 20, max 100).
        offset: Pagination offset (default 0).

    Returns a list of job records and the total matching count.
    """
    params: dict = {}
    if status is not None:
        params["status"] = status
    if limit is not None:
        params["limit"] = str(limit)
    if offset is not None:
        params["offset"] = str(offset)
    return await _request("GET", "/jobs", params=params)


@mcp.tool
async def get_job(job_id: str) -> dict:
    """Get a single agent job with full details and attempt history.

    Returns the complete job record including task, status, profile,
    retry config, and all execution attempts with their output and
    exit codes.

    Args:
        job_id: The job ID (26-character ULID returned by submit_job).
    """
    return await _request("GET", f"/jobs/{job_id}")


@mcp.tool
async def cancel_job(job_id: str) -> dict:
    """Cancel a pending or running agent job.

    Only jobs in PENDING or RUNNING status can be cancelled.
    Returns 409 Conflict if the job is already in a terminal state
    (SUCCEEDED, FAILED, or CANCELLED).

    Args:
        job_id: The job ID to cancel.
    """
    return await _request("POST", f"/jobs/{job_id}/cancel")


@mcp.tool
async def get_job_output(job_id: str) -> dict:
    """Get the output from a job's latest execution attempt.

    Returns the last 32KB of stdout/stderr from the most recent attempt.
    For full output, check pod logs via SigNoz.

    The truncated field indicates whether the output was trimmed to fit
    the 32KB KV store limit.

    Args:
        job_id: The job ID to get output for.
    """
    return await _request("GET", f"/jobs/{job_id}/output")


def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
