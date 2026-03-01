# BuildBuddy MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python MCP server wrapping the BuildBuddy REST API, packaged as a dual-arch OCI image.

**Architecture:** Single-file FastMCP server with Pydantic BaseSettings config and async httpx client. Six tools (5 read-only + 1 workflow trigger) map 1:1 to BuildBuddy API endpoints.

**Tech Stack:** FastMCP v3, httpx, pydantic-settings, Bazel (py3_image)

---

### Task 1: Add fastmcp dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add fastmcp to pyproject.toml**

Add `"fastmcp>=3.0.0"` to the `dependencies` list in `pyproject.toml`. Place it after the `fastapi` entry to keep alphabetical grouping.

**Step 2: Regenerate lockfile**

Run: `format`

This runs all formatters and regenerates `requirements/all.txt` via `uv pip compile`.

**Step 3: Verify fastmcp is in the lockfile**

Run: `grep fastmcp requirements/all.txt`

Expected: A pinned fastmcp entry (e.g., `fastmcp==3.0.2`)

**Step 4: Commit**

```bash
git add pyproject.toml requirements/
git commit -m "deps: add fastmcp for BuildBuddy MCP server"
```

---

### Task 2: Create service directory structure

**Files:**
- Create: `services/buildbuddy_mcp/__init__.py`
- Create: `services/buildbuddy_mcp/app/__init__.py`
- Create: `services/buildbuddy_mcp/app/main.py` (empty placeholder)
- Create: `services/buildbuddy_mcp/tests/__init__.py`

**Step 1: Create directories and empty files**

```bash
mkdir -p services/buildbuddy_mcp/app services/buildbuddy_mcp/tests
touch services/buildbuddy_mcp/__init__.py
touch services/buildbuddy_mcp/app/__init__.py
touch services/buildbuddy_mcp/tests/__init__.py
```

**Step 2: Create main.py with Settings and empty FastMCP server**

Create `services/buildbuddy_mcp/app/main.py`:

```python
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


def main():
    settings = Settings()
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
```

**Step 3: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: scaffold buildbuddy-mcp service directory"
```

---

### Task 3: Write tests for get_invocation tool

**Files:**
- Create: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write tests**

Create `services/buildbuddy_mcp/tests/main_test.py`:

```python
"""Tests for BuildBuddy MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("BUILDBUDDY_API_KEY", "test-key")
    monkeypatch.setenv("BUILDBUDDY_URL", "https://test.buildbuddy.io")


@pytest.fixture
def mock_response():
    """Create a mock httpx response."""

    def _make(json_data, status_code=200):
        resp = httpx.Response(status_code, json=json_data, request=httpx.Request("POST", "https://test"))
        return resp

    return _make


class TestGetInvocation:
    @pytest.mark.asyncio
    async def test_by_invocation_id(self, mock_response):
        expected = {"invocation": [{"id": {"invocation_id": "abc-123"}, "success": True}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_invocation

            result = await get_invocation(invocation_id="abc-123")
        assert result["invocation"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_by_commit_sha(self, mock_response):
        expected = {"invocation": [{"id": {"invocation_id": "abc-123"}, "commit_sha": "deadbeef"}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_invocation

            result = await get_invocation(commit_sha="deadbeef")
        assert result["invocation"][0]["commit_sha"] == "deadbeef"
```

**Step 2: Run tests to verify they fail**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_invocation` and `_post` don't exist yet.

---

### Task 4: Implement get_invocation tool and HTTP client

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`

**Step 1: Add the HTTP client helper and get_invocation tool**

Update `services/buildbuddy_mcp/app/main.py` — add after the `mcp = FastMCP("BuildBuddy")` line:

```python
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
```

**Step 2: Run tests to verify they pass**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: PASS

**Step 3: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: add get_invocation tool with HTTP client"
```

---

### Task 5: Write tests for get_log tool

**Files:**
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Add test class for get_log**

Append to `main_test.py`:

```python
class TestGetLog:
    @pytest.mark.asyncio
    async def test_returns_log_contents(self, mock_response):
        expected = {"log": {"contents": "Building //...\nERROR: compilation failed"}}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_log

            result = await get_log(invocation_id="abc-123")
        assert "ERROR" in result["log"]["contents"]
```

**Step 2: Run test to verify it fails**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_log` not defined.

---

### Task 6: Implement get_log tool

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`

**Step 1: Add get_log tool**

Append to `main.py`:

```python
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
```

**Step 2: Run tests**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: PASS

**Step 3: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: add get_log tool"
```

---

### Task 7: Write tests for get_target tool

**Files:**
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Add test class**

```python
class TestGetTarget:
    @pytest.mark.asyncio
    async def test_returns_targets(self, mock_response):
        expected = {"target": [{"label": "//pkg:test", "status": "PASSED"}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_target

            result = await get_target(invocation_id="abc-123")
        assert result["target"][0]["label"] == "//pkg:test"
```

**Step 2: Run test to verify it fails**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL

---

### Task 8: Implement get_target tool

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`

**Step 1: Add get_target tool**

```python
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
```

**Step 2: Run tests**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: PASS

**Step 3: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: add get_target tool"
```

---

### Task 9: Write tests for get_action and get_file tools

**Files:**
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Add test classes**

```python
class TestGetAction:
    @pytest.mark.asyncio
    async def test_returns_actions(self, mock_response):
        expected = {"action": [{"target_label": "//pkg:test", "shard": 0, "run": 1, "attempt": 1}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_action

            result = await get_action(invocation_id="abc-123")
        assert result["action"][0]["target_label"] == "//pkg:test"


class TestGetFile:
    @pytest.mark.asyncio
    async def test_returns_file_data(self, mock_response):
        expected = {"data": "file contents here"}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_file

            result = await get_file(uri="bytestream://example/blobs/sha256/abc/123")
        assert result["data"] == "file contents here"
```

**Step 2: Run test to verify it fails**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL

---

### Task 10: Implement get_action and get_file tools

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`

**Step 1: Add get_action tool**

```python
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
```

**Step 2: Add get_file tool**

```python
@mcp.tool
async def get_file(uri: str) -> dict:
    """Download a file by its bytestream URI.

    Use URIs from get_action file references. Supports ZSTD-compressed
    variants (append /compressed-blobs/zstd/ to URI).
    """
    return await _post("/GetFile", {"uri": uri})
```

**Step 3: Run tests**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: PASS

**Step 4: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: add get_action and get_file tools"
```

---

### Task 11: Write test for execute_workflow tool

**Files:**
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Add test class**

```python
class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_triggers_workflow(self, mock_response):
        expected = {"action_statuses": [{"action_name": "Test and push", "invocation_id": "new-inv-123"}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import execute_workflow

            result = await execute_workflow(
                repo_url="https://github.com/jomcgi/homelab",
                branch="main",
            )
        assert result["action_statuses"][0]["action_name"] == "Test and push"
```

**Step 2: Run test to verify it fails**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL

---

### Task 12: Implement execute_workflow tool

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`

**Step 1: Add execute_workflow tool**

```python
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
```

**Step 2: Run tests**

Run: `bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: PASS

**Step 3: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "feat: add execute_workflow tool"
```

---

### Task 13: Add BUILD files

**Files:**
- Create: `services/buildbuddy_mcp/app/BUILD`
- Create: `services/buildbuddy_mcp/tests/BUILD`
- Create: `services/buildbuddy_mcp/BUILD`

**Step 1: Run gazelle to generate initial BUILD files**

Run: `bazel run gazelle`

This auto-generates BUILD files from Python imports. Verify the output matches expectations.

**Step 2: Create the py3_image in `services/buildbuddy_mcp/BUILD`**

If gazelle doesn't create the image target, manually add it. The BUILD file should contain:

```python
load("//tools/oci:py3_image.bzl", "py3_image")

py3_image(
    name = "image",
    binary = "//services/buildbuddy_mcp/app:main",
    repository = "ghcr.io/jomcgi/homelab/services/buildbuddy-mcp",
)
```

Gazelle may generate a `py_library` for the `__init__.py` — keep that, add the `py3_image` alongside it.

**Step 3: Verify the app BUILD file**

`services/buildbuddy_mcp/app/BUILD` should contain (gazelle should generate this):

```python
load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_library")

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

py_binary(
    name = "main",
    srcs = ["main.py"],
    visibility = ["//:__subpackages__"],
    deps = [
        ":app",
        "@pip//fastmcp",
        "@pip//httpx",
        "@pip//pydantic_settings",
    ],
)
```

**Step 4: Verify the tests BUILD file**

`services/buildbuddy_mcp/tests/BUILD` should contain:

```python
load("//tools/pytest:defs.bzl", "py_test")

# gazelle:resolve py services.buildbuddy_mcp.app.main //services/buildbuddy_mcp/app:app

py_test(
    name = "main_test",
    srcs = ["main_test.py"],
    deps = [
        "//services/buildbuddy_mcp/app:app",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

Note: The `gazelle:resolve` comment may be needed to help gazelle resolve the internal import. Check gazelle output.

**Step 5: Build and test everything**

Run: `bazel test //services/buildbuddy_mcp/...`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add services/buildbuddy_mcp/
git commit -m "build: add BUILD files for buildbuddy-mcp service"
```

---

### Task 14: Build the container image

**Step 1: Build the image**

Run: `bazel build //services/buildbuddy_mcp:image`

Expected: Builds successfully, creating a multi-platform OCI image index.

**Step 2: Run format to ensure everything is clean**

Run: `format`

This ensures BUILD files are formatted and the images/BUILD push_all target includes the new image.

**Step 3: Verify image push target was added to images/BUILD**

Run: `grep buildbuddy images/BUILD`

Expected: `"//services/buildbuddy_mcp:image.push"` appears in the `push_all` multirun.

**Step 4: Run full test suite**

Run: `bazel test //...`

Expected: All tests PASS, no regressions.

**Step 5: Commit any format changes**

```bash
git add images/BUILD services/buildbuddy_mcp/
git commit -m "build: add buildbuddy-mcp container image"
```
