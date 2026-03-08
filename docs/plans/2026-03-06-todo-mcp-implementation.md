# Todo-Admin MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and deploy an MCP server that proxies the todo-admin REST API, letting Claude read/write tasks conversationally.

**Architecture:** Thin Python FastMCP HTTP proxy over `http://todo.todo.svc.cluster.local:8080`. Deployed via the shared `charts/mcp-servers` Helm chart, registered with Context Forge gateway. OTel auto-instrumented via pod annotation.

**Tech Stack:** Python, FastMCP, httpx, pydantic-settings, Bazel (aspect_rules_py)

**Design doc:** `docs/plans/2026-03-06-todo-mcp-design.md`

---

### Task 1: Scaffold service directory and BUILD files

**Files:**

- Create: `services/todo_mcp/__init__.py`
- Create: `services/todo_mcp/BUILD`
- Create: `services/todo_mcp/app/__init__.py`
- Create: `services/todo_mcp/app/BUILD`
- Create: `services/todo_mcp/tests/__init__.py`
- Create: `services/todo_mcp/tests/BUILD`

**Step 1: Create empty `__init__.py` files**

```python
# services/todo_mcp/__init__.py — empty
# services/todo_mcp/app/__init__.py — empty
# services/todo_mcp/tests/__init__.py — empty
```

**Step 2: Create `services/todo_mcp/BUILD`**

Follow `services/buildbuddy_mcp/BUILD` pattern:

```python
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/oci:py3_image.bzl", "py3_image")

py_library(
    name = "todo_mcp",
    srcs = ["__init__.py"],
    visibility = ["//:__subpackages__"],
)

py3_image(
    name = "image",
    binary = "//services/todo_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/todo-mcp",
)

semgrep_test(
    name = "__init___semgrep_test",
    srcs = ["__init__.py"],
    rules = ["//semgrep_rules:python_rules"],
)
```

**Step 3: Create `services/todo_mcp/app/BUILD`**

Follow `services/buildbuddy_mcp/app/BUILD` pattern:

```python
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("@aspect_rules_py//py/private/py_venv:defs.bzl", "py_venv_binary")
load("//rules_semgrep:defs.bzl", "semgrep_target_test")

py_venv_binary(
    name = "main",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
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
```

**Step 4: Create `services/todo_mcp/tests/BUILD`**

```python
load("@aspect_rules_py//py:defs.bzl", "py_library")
load("//rules_semgrep:defs.bzl", "semgrep_test")
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py services.todo_mcp.app.main //services/todo_mcp/app:app

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
        "//services/todo_mcp/app",
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

**Step 5: Commit**

```bash
git add services/todo_mcp/
git commit -m "feat(todo-mcp): scaffold service directory and BUILD files"
```

---

### Task 2: Write failing tests for all MCP tools

**Files:**

- Create: `services/todo_mcp/tests/conftest.py`
- Create: `services/todo_mcp/tests/main_test.py`

**Step 1: Write `services/todo_mcp/tests/conftest.py`**

Matches `buildbuddy_mcp/tests/conftest.py` exactly:

```python
"""Pytest configuration for Todo MCP tests."""

import pytest_asyncio  # noqa: F401 — registers the asyncio marker


def pytest_configure(config):
    """Set asyncio_mode to auto so @pytest.mark.asyncio is not needed."""
    config.option.asyncio_mode = "auto"
```

**Step 2: Write `services/todo_mcp/tests/main_test.py`**

Tests mock `_request` (the internal HTTP helper) and verify each tool calls the correct method/endpoint:

```python
"""Tests for Todo MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.todo_mcp.app.main import (
    Settings,
    configure,
    get_tasks,
    set_tasks,
    reset_daily,
    reset_weekly,
)


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://todo.test:8080"))


class TestGetTasks:
    async def test_returns_full_state(self):
        expected = {
            "weekly": {"task": "Ship feature", "done": False},
            "daily": [
                {"task": "Review PR", "done": True},
                {"task": "Write tests", "done": False},
                {"task": "", "done": False},
            ],
        }

        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_req:
            result = await get_tasks()
        mock_req.assert_called_once_with("GET", "/api/todo")
        assert result["weekly"]["task"] == "Ship feature"
        assert len(result["daily"]) == 3

    async def test_http_error_returns_error_dict(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"error": "Todo API error: 500 Internal Server Error"},
        ):
            result = await get_tasks()
        assert "error" in result


class TestSetTasks:
    async def test_sends_full_state(self):
        state = {
            "weekly": {"task": "Ship feature", "done": False},
            "daily": [
                {"task": "Review PR", "done": False},
                {"task": "Write tests", "done": False},
                {"task": "", "done": False},
            ],
        }

        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await set_tasks(
                weekly_task="Ship feature",
                weekly_done=False,
                daily_1_task="Review PR",
                daily_1_done=False,
                daily_2_task="Write tests",
                daily_2_done=False,
                daily_3_task="",
                daily_3_done=False,
            )
        mock_req.assert_called_once_with("PUT", "/api/todo", json=state)
        assert result["status"] == "ok"


class TestResetDaily:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_daily()
        mock_req.assert_called_once_with("POST", "/api/reset/daily")
        assert result["status"] == "ok"


class TestResetWeekly:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_weekly()
        mock_req.assert_called_once_with("POST", "/api/reset/weekly")
        assert result["status"] == "ok"
```

**Step 3: Run tests to verify they fail**

Run: `bazel test //services/todo_mcp/tests:main_test`
Expected: FAIL — `ImportError: cannot import name 'get_tasks' from 'services.todo_mcp.app.main'`

**Step 4: Commit**

```bash
git add services/todo_mcp/tests/
git commit -m "test(todo-mcp): add failing tests for all MCP tools"
```

---

### Task 3: Implement the MCP server

**Files:**

- Create: `services/todo_mcp/app/main.py`

**Step 1: Write `services/todo_mcp/app/main.py`**

```python
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
```

**Step 2: Run tests to verify they pass**

Run: `bazel test //services/todo_mcp/tests:main_test`
Expected: PASS — all 5 tests green

**Step 3: Run full service tests including semgrep**

Run: `bazel test //services/todo_mcp/...`
Expected: PASS — all tests (unit + semgrep) green

**Step 4: Commit**

```bash
git add services/todo_mcp/app/main.py
git commit -m "feat(todo-mcp): implement MCP server with get/set/reset tools"
```

---

### Task 4: Build the container image

**Step 1: Verify image builds**

Run: `bazel build //services/todo_mcp:image`
Expected: BUILD SUCCESS

**Step 2: Commit (if any BUILD file adjustments needed)**

```bash
git commit -m "build(todo-mcp): fix image build issues" # only if needed
```

---

### Task 5: Add deployment configuration

**Files:**

- Modify: `overlays/prod/mcp-servers/values.yaml` — add todo-mcp server entry

**Step 1: Add server entry to `overlays/prod/mcp-servers/values.yaml`**

Append to the `servers` array (after the `argocd-mcp` entry):

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

**Step 2: Render Helm templates to verify**

Run: `helm template mcp-servers charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml`

Verify the output includes:

- A Deployment for `todo-mcp`
- A Service for `todo-mcp` on port 8000
- A registration Job for `todo-mcp`
- An alert ConfigMap for `todo-mcp`
- An ImageUpdater resource for `todo-mcp`

**Step 3: Commit**

```bash
git add overlays/prod/mcp-servers/values.yaml
git commit -m "feat(todo-mcp): add deployment to mcp-servers overlay"
```

---

### Task 6: Run full CI validation and create PR

**Step 1: Run format check**

Run: `format`
Expected: No changes needed (or auto-fixes applied)

**Step 2: Run full test suite**

Run: `bazel test //services/todo_mcp/...`
Expected: All tests pass

**Step 3: Push and create PR**

```bash
git push -u origin feat/todo-mcp
gh pr create --title "feat(todo-mcp): add MCP server for todo-admin" --body "$(cat <<'EOF'
## Summary
- New MCP server in `services/todo_mcp/` that proxies the todo-admin REST API
- 4 tools: `get_tasks`, `set_tasks`, `reset_daily`, `reset_weekly`
- Deployed via shared `charts/mcp-servers` Helm chart with Context Forge registration
- OTel auto-instrumented via pod annotation

## Test plan
- [ ] `bazel test //services/todo_mcp/...` passes
- [ ] `helm template` renders correctly
- [ ] CI passes on PR
- [ ] After merge: verify todo-mcp appears in Context Forge gateway
- [ ] After merge: verify `get_tasks` returns current tasks via MCP

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
