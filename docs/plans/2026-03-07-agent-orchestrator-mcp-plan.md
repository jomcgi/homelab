# Agent Orchestrator MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Python FastMCP server that wraps the agent orchestrator REST API as 5 MCP tools, deployable via the existing mcp-servers chart.

**Architecture:** A thin HTTP proxy — each MCP tool maps 1:1 to an agent orchestrator REST endpoint. Uses `httpx.AsyncClient` for async HTTP calls, returns dicts (error dicts on failure). Follows the exact pattern established by `services/todo_mcp/`.

**Tech Stack:** Python, FastMCP, httpx, pydantic-settings, pytest + pytest-asyncio

---

### Task 1: Create service skeleton

**Files:**
- Create: `services/agent_orchestrator_mcp/__init__.py`
- Create: `services/agent_orchestrator_mcp/app/__init__.py`
- Create: `services/agent_orchestrator_mcp/tests/__init__.py`

**Step 1: Create empty init files**

```python
# All three __init__.py files are empty
```

**Step 2: Commit**

```bash
git add services/agent_orchestrator_mcp/
git commit -m "feat(agent-orchestrator-mcp): add service skeleton"
```

---

### Task 2: Write tests for submit_job and list_jobs

**Files:**
- Create: `services/agent_orchestrator_mcp/tests/conftest.py`
- Create: `services/agent_orchestrator_mcp/tests/main_test.py`

**Step 1: Write conftest.py**

```python
"""Pytest configuration for Agent Orchestrator MCP tests."""

import pytest_asyncio  # noqa: F401 — registers the asyncio marker


def pytest_configure(config):
    """Set asyncio_mode to auto so @pytest.mark.asyncio is not needed."""
    config.option.asyncio_mode = "auto"
```

**Step 2: Write tests for submit_job and list_jobs**

Reference pattern: `services/todo_mcp/tests/main_test.py` — mock `_request` at module level.

```python
"""Tests for Agent Orchestrator MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.agent_orchestrator_mcp.app.main import (
    Settings,
    configure,
    submit_job,
    list_jobs,
)

_PATCH = "services.agent_orchestrator_mcp.app.main._request"


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://orchestrator.test:8080"))


class TestSubmitJob:
    async def test_submits_with_task_only(self):
        expected = {"id": "01ABC", "status": "PENDING", "created_at": "2026-03-07T00:00:00Z"}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await submit_job(task="Fix the auth bug")
        mock_req.assert_called_once_with("POST", "/jobs", json={"task": "Fix the auth bug"})
        assert result["id"] == "01ABC"
        assert result["status"] == "PENDING"

    async def test_submits_with_all_params(self):
        expected = {"id": "01ABC", "status": "PENDING", "created_at": "2026-03-07T00:00:00Z"}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await submit_job(
                task="Debug CI",
                profile="ci-debug",
                max_retries=3,
                source="github",
            )
        mock_req.assert_called_once_with(
            "POST",
            "/jobs",
            json={"task": "Debug CI", "profile": "ci-debug", "max_retries": 3, "source": "github"},
        )
        assert result["status"] == "PENDING"

    async def test_http_error_returns_error_dict(self):
        with patch(_PATCH, new_callable=AsyncMock, return_value={"error": "API error: 500"}):
            result = await submit_job(task="Fail")
        assert "error" in result


class TestListJobs:
    async def test_lists_without_filters(self):
        expected = {"jobs": [{"id": "01ABC"}], "total": 1}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs()
        mock_req.assert_called_once_with("GET", "/jobs", params={})
        assert result["total"] == 1

    async def test_lists_with_status_filter(self):
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(status="RUNNING,PENDING")
        mock_req.assert_called_once_with("GET", "/jobs", params={"status": "RUNNING,PENDING"})
        assert result["total"] == 0

    async def test_lists_with_pagination(self):
        expected = {"jobs": [], "total": 50}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(limit=10, offset=20)
        mock_req.assert_called_once_with("GET", "/jobs", params={"limit": "10", "offset": "20"})
        assert result["total"] == 50

    async def test_lists_with_all_params(self):
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(status="FAILED", limit=5, offset=0)
        mock_req.assert_called_once_with(
            "GET", "/jobs", params={"status": "FAILED", "limit": "5", "offset": "0"}
        )
```

**Step 3: Verify tests cannot run yet (no implementation)**

The tests reference `services.agent_orchestrator_mcp.app.main` which doesn't exist yet. This is expected — we'll implement in the next task.

---

### Task 3: Implement main.py with submit_job and list_jobs

**Files:**
- Create: `services/agent_orchestrator_mcp/app/main.py`

**Step 1: Write the full MCP server with submit_job and list_jobs**

Reference pattern: `services/todo_mcp/app/main.py`

```python
"""Agent Orchestrator MCP server."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRATOR_")

    url: str
    port: int = 8000


mcp = FastMCP("AgentOrchestrator")

_client: httpx.AsyncClient | None = None


def configure(settings: Settings) -> None:
    """Configure the HTTP client with the given settings."""
    global _client
    _client = httpx.AsyncClient(base_url=settings.url)


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
```

**Step 2: Create BUILD files so tests can run**

Create `services/agent_orchestrator_mcp/app/BUILD`:

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test", "semgrep_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

py_library(
    name = "app",
    srcs = [
        "__init__.py",
        "main.py",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)

semgrep_target_test(
    name = "main_semgrep_test",
    lockfiles = ["//requirements:all.txt"],
    rules = ["//semgrep_rules:python_rules"],
    sca_rules = ["//semgrep_rules:sca_python_rules"],
    target = ":main",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

Create `services/agent_orchestrator_mcp/tests/BUILD`:

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py services.agent_orchestrator_mcp.app.main //services/agent_orchestrator_mcp/app:app

py_library(
    name = "tests",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        ":conftest",
        "//services/agent_orchestrator_mcp/app",
        "@pip//pytest",
    ],
)

py_library(
    name = "conftest",
    testonly = True,
    srcs = ["conftest.py"],
    visibility = ["//:__subpackages__"],
    deps = ["@pip//pytest_asyncio"],
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "conftest_semgrep_test",
    srcs = ["conftest.py"],
    rules = ["//semgrep_rules:python_rules"],
)

semgrep_test(
    name = "main_test_semgrep_test",
    srcs = ["main_test.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

Create `services/agent_orchestrator_mcp/BUILD`:

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "agent_orchestrator_mcp",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "image",
    binary = "//services/agent_orchestrator_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/agent-orchestrator-mcp",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

**Step 3: Run tests**

Run: `bazel test //services/agent_orchestrator_mcp/tests:main_test`
Expected: PASS — all submit_job and list_jobs tests green.

**Step 4: Commit**

```bash
git add services/agent_orchestrator_mcp/
git commit -m "feat(agent-orchestrator-mcp): add submit_job and list_jobs tools"
```

---

### Task 4: Add tests and implementation for get_job, cancel_job, get_job_output

**Files:**
- Modify: `services/agent_orchestrator_mcp/tests/main_test.py`
- Modify: `services/agent_orchestrator_mcp/app/main.py`

**Step 1: Add tests to main_test.py**

Add imports for `get_job`, `cancel_job`, `get_job_output` to the import block.

```python
class TestGetJob:
    async def test_returns_job_record(self):
        expected = {
            "id": "01ABC",
            "task": "Fix bug",
            "status": "RUNNING",
            "attempts": [{"number": 1, "exit_code": None}],
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await get_job(job_id="01ABC")
        mock_req.assert_called_once_with("GET", "/jobs/01ABC")
        assert result["id"] == "01ABC"
        assert result["status"] == "RUNNING"

    async def test_not_found_returns_error(self):
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"error": "Orchestrator API error: 404"}
        ):
            result = await get_job(job_id="NONEXISTENT")
        assert "error" in result


class TestCancelJob:
    async def test_cancels_running_job(self):
        expected = {"id": "01ABC", "status": "CANCELLED"}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await cancel_job(job_id="01ABC")
        mock_req.assert_called_once_with("POST", "/jobs/01ABC/cancel")
        assert result["status"] == "CANCELLED"

    async def test_conflict_returns_error(self):
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"error": "Orchestrator API error: 409"}
        ):
            result = await cancel_job(job_id="01ABC")
        assert "error" in result


class TestGetJobOutput:
    async def test_returns_output(self):
        expected = {"attempt": 1, "exit_code": 0, "output": "Done!", "truncated": False}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await get_job_output(job_id="01ABC")
        mock_req.assert_called_once_with("GET", "/jobs/01ABC/output")
        assert result["output"] == "Done!"
        assert result["truncated"] is False

    async def test_no_output_returns_error(self):
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"error": "Orchestrator API error: 404"}
        ):
            result = await get_job_output(job_id="01ABC")
        assert "error" in result
```

**Step 2: Add implementations to main.py**

Append after `list_jobs`:

```python
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
```

Also add `main()` entrypoint at the bottom:

```python
def main():
    settings = Settings()
    configure(settings)
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
```

**Step 3: Run tests**

Run: `bazel test //services/agent_orchestrator_mcp/tests:main_test`
Expected: PASS — all tests green.

**Step 4: Commit**

```bash
git add services/agent_orchestrator_mcp/
git commit -m "feat(agent-orchestrator-mcp): add get_job, cancel_job, get_job_output tools"
```

---

### Task 5: Add deployment configuration

**Files:**
- Modify: `overlays/prod/mcp-servers/values.yaml`

**Step 1: Add server entry to values.yaml**

Append to the `servers` list (after the `todo-mcp` entry):

```yaml
- name: agent-orchestrator-mcp
  image:
    repository: ghcr.io/jomcgi/homelab/services/agent-orchestrator-mcp
    tag: "main"
  port: 8000
  podAnnotations:
    instrumentation.opentelemetry.io/inject-python: "python"
  env:
  - name: ORCHESTRATOR_URL
    value: "http://agent-orchestrator.agent-orchestrator.svc.cluster.local:8080"
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
    url: "http://agent-orchestrator-mcp.mcp-servers.svc.cluster.local:8000/health"
```

**Step 2: Verify rendering**

Run: `helm template mcp-servers charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml | grep -A5 "agent-orchestrator-mcp"`
Expected: Deployment, Service, Registration Job rendered for the new server.

**Step 3: Commit**

```bash
git add overlays/prod/mcp-servers/values.yaml
git commit -m "feat(agent-orchestrator-mcp): add deployment to mcp-servers chart"
```

---

### Task 6: Add tool permissions to settings.json

**Files:**
- Modify: `.claude/settings.json`

**Step 1: Add MCP tool allow entries**

Add these 5 entries to the `allow` array in `.claude/settings.json`, in the section with other `mcp__context-forge__` entries (and also the `mcp__claude_ai_Homelab__` equivalents):

```json
"mcp__context-forge__agent-orchestrator-mcp-submit-job",
"mcp__context-forge__agent-orchestrator-mcp-list-jobs",
"mcp__context-forge__agent-orchestrator-mcp-get-job",
"mcp__context-forge__agent-orchestrator-mcp-cancel-job",
"mcp__context-forge__agent-orchestrator-mcp-get-job-output",
"mcp__claude_ai_Homelab__agent-orchestrator-mcp-submit-job",
"mcp__claude_ai_Homelab__agent-orchestrator-mcp-list-jobs",
"mcp__claude_ai_Homelab__agent-orchestrator-mcp-get-job",
"mcp__claude_ai_Homelab__agent-orchestrator-mcp-cancel-job",
"mcp__claude_ai_Homelab__agent-orchestrator-mcp-get-job-output"
```

**Step 2: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(agent-orchestrator-mcp): whitelist MCP tools in settings"
```

---

### Task 7: Update CLAUDE.md cluster investigation table

**Files:**
- Modify: `.claude/CLAUDE.md`

**Step 1: Add agent orchestrator tools to the MCP tool table**

Add a new row to the "Cluster Investigation" MCP tools table:

```markdown
| **Agent jobs**   | `agent-orchestrator-mcp-submit-job`, `agent-orchestrator-mcp-list-jobs`, `agent-orchestrator-mcp-get-job` |
```

**Step 2: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: add agent orchestrator MCP tools to CLAUDE.md"
```

---

### Task 8: Run full test suite and format check

**Step 1: Run format to update BUILD files**

Run: `format` (in the worktree)
Expected: BUILD files formatted, no unexpected changes.

**Step 2: Run tests**

Run: `bazel test //services/agent_orchestrator_mcp/...`
Expected: All tests pass.

**Step 3: Commit any formatting changes**

```bash
git add -A
git commit -m "style: format BUILD files for agent-orchestrator-mcp"
```

---

### Task 9: Create PR

**Step 1: Push and create PR**

```bash
git push -u origin feat/agent-orchestrator-mcp
gh pr create --title "feat: add agent orchestrator MCP server" --body "$(cat <<'EOF'
## Summary
- Adds `agent-orchestrator-mcp` Python FastMCP service with 5 tools: submit_job, list_jobs, get_job, cancel_job, get_job_output
- Deploys via existing mcp-servers chart with STREAMABLEHTTP registration to Context Forge gateway
- Whitelists tools in .claude/settings.json for both context-forge and claude_ai_Homelab MCP namespaces

## Test plan
- [ ] `bazel test //services/agent_orchestrator_mcp/...` passes
- [ ] `helm template` renders deployment correctly
- [ ] CI passes (format check + test)
- [ ] After merge: verify pod starts in mcp-servers namespace
- [ ] After merge: verify tools appear in Context Forge gateway
- [ ] After merge: test submit_job and list_jobs from Claude Code chat

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: Enable auto-merge**

```bash
gh pr merge --auto --rebase
```

**Step 3: Poll until merged**

```bash
gh pr view <number> --json state,mergeStateStatus
```
