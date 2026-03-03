# BuildBuddy MCP Server v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the BuildBuddy MCP server with robust error handling, missing API parameters, context-reducing filters, a composite `diagnose_failure` tool, a new `run` tool, and proto conformance tests.

**Architecture:** Approach C (primitives + composites). `main.py` holds the FastMCP server, HTTP client, and all primitive API tools. `composite.py` holds smart composite tools that orchestrate multiple primitives. Both register on the same `mcp` instance. Tests split across `main_test.py`, `composite_test.py`, and `proto_conformance_test.py`.

**Tech Stack:** FastMCP v3, httpx, pydantic-settings, Bazel (py3_image)

**Worktree:** `/tmp/claude-worktrees/buildbuddy-mcp-v2` on branch `feat/buildbuddy-mcp-v2`

---

### Task 1: Robust error handling in _post

The foundation — make `_post` return valid structures on HTTP errors instead of raising exceptions that trigger FastMCP output schema validation failures.

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py:35-39`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing test**

Add to `services/buildbuddy_mcp/tests/main_test.py`, at the end of the file:

```python
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_returns_error_dict(self):
        with patch(
            "services.buildbuddy_mcp.app.main._client",
        ) as mock_client:
            mock_resp = AsyncMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_resp.is_success = False
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await get_invocation(invocation_id="nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_response_returns_error_dict(self):
        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await get_invocation(invocation_id="abc-123")
        assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `_post` currently raises on HTTP errors instead of returning an error dict.

**Step 3: Implement error handling in _post**

Replace the `_post` function in `services/buildbuddy_mcp/app/main.py` (lines 35-39) with:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS (existing tests still pass because they mock `_post` directly; the new test exercises the real `_post` with a mocked client).

**Step 5: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "fix(buildbuddy-mcp): return error dicts instead of raising on API failures"
```

---

### Task 2: Add include flags to get_invocation

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py:42-61`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing test**

Add to `TestGetInvocation` in `main_test.py`:

```python
    @pytest.mark.asyncio
    async def test_include_child_invocations(self):
        expected = {
            "invocation": [
                {
                    "id": {"invocation_id": "workflow-1"},
                    "child_invocations": [
                        {"invocation_id": "child-1"},
                        {"invocation_id": "child-2"},
                    ],
                }
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            result = await get_invocation(
                invocation_id="workflow-1",
                include_child_invocations=True,
            )
        # Verify the include flag was passed as a top-level request field
        call_body = mock_post.call_args[0][1]
        assert call_body["include_child_invocations"] is True
        assert len(result["invocation"][0]["child_invocations"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_invocation` doesn't accept `include_child_invocations` parameter.

**Step 3: Update get_invocation**

Replace the `get_invocation` function in `main.py` with:

```python
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
```

**Step 4: Update existing test import**

The test file imports `get_invocation` at the top. Make sure the import still works (it should — same function, new optional params).

**Step 5: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 6: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add include_child_invocations/metadata/artifacts to get_invocation"
```

---

### Task 3: Fix get_file base64 decode

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py:135-142`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing tests**

Replace `TestGetFile` in `main_test.py` with:

```python
class TestGetFile:
    @pytest.mark.asyncio
    async def test_decodes_base64_text(self):
        import base64

        text = "PASS: //pkg:test\nRan 1 test in 0.5s"
        b64 = base64.b64encode(text.encode()).decode()

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"data": b64},
        ):
            result = await get_file(uri="bytestream://example/blobs/abc/123")
        assert result["contents"] == text

    @pytest.mark.asyncio
    async def test_binary_file_returns_error(self):
        import base64

        binary_data = bytes(range(256))
        b64 = base64.b64encode(binary_data).decode()

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"data": b64},
        ):
            result = await get_file(uri="bytestream://example/blobs/abc/256")
        assert "error" in result
        assert result["size_bytes"] == 256
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_file` currently returns the raw dict without decoding.

**Step 3: Update get_file with base64 decode**

Replace `get_file` in `main.py` with:

```python
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
```

**Step 4: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "fix(buildbuddy-mcp): decode base64 file data to UTF-8 text"
```

---

### Task 4: Add server-side status filter to get_target

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py:80-103`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing tests**

Add to `TestGetTarget` in `main_test.py`:

```python
    @pytest.mark.asyncio
    async def test_status_filter_returns_only_matching(self):
        api_response = {
            "target": [
                {"label": "//pkg:build", "status": "BUILT"},
                {"label": "//pkg:test_a", "status": "PASSED"},
                {"label": "//pkg:test_b", "status": "FAILED"},
                {"label": "//pkg:test_c", "status": "FAILED"},
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_target(invocation_id="abc-123", status="FAILED")
        assert len(result["target"]) == 2
        assert all(t["status"] == "FAILED" for t in result["target"])

    @pytest.mark.asyncio
    async def test_status_filter_with_pagination(self):
        page1 = {
            "target": [{"label": "//a:t", "status": "PASSED"}],
            "next_page_token": "page2",
        }
        page2 = {
            "target": [{"label": "//b:t", "status": "FAILED"}],
        }

        call_count = 0

        async def mock_post(endpoint, body):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await get_target(invocation_id="abc-123", status="FAILED")
        assert len(result["target"]) == 1
        assert result["target"][0]["label"] == "//b:t"
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_target` doesn't accept `status` parameter.

**Step 3: Update get_target with status filter**

Replace `get_target` in `main.py` with:

```python
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
```

**Step 4: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add client-side status filter to get_target"
```

---

### Task 5: Add errors_only mode to get_log

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py:64-77`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing tests**

Add to `TestGetLog` in `main_test.py`:

```python
    @pytest.mark.asyncio
    async def test_errors_only_filters_to_error_lines(self):
        log_text = (
            "Loading: 0 packages loaded\n"
            "Analyzing: target //pkg:test\n"
            "INFO: Build completed\n"
            "FAIL: //pkg:test (see logs)\n"
            "ERROR: Build failed\n"
            "INFO: Streaming results\n"
            "Executed 1 out of 5 tests: 4 pass, 1 fails.\n"
        )
        api_response = {"log": {"contents": log_text}}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "FAIL:" in contents
        assert "ERROR:" in contents
        assert "Executed 1 out of 5 tests" in contents
        # Non-error lines should be excluded
        assert "Loading: 0 packages loaded" not in contents

    @pytest.mark.asyncio
    async def test_errors_only_paginates(self):
        page1 = {
            "log": {"contents": "INFO: ok\nERROR: bad\n"},
            "next_page_token": "p2",
        }
        page2 = {
            "log": {"contents": "FAIL: //test\nExecuted 1 out of 2 tests: 1 fails.\n"},
        }

        call_count = 0

        async def mock_post(endpoint, body):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "ERROR: bad" in contents
        assert "FAIL: //test" in contents

    @pytest.mark.asyncio
    async def test_errors_only_strips_ansi(self):
        log_text = "\x1b[31mERROR:\x1b[0m Build failed\n"
        api_response = {"log": {"contents": log_text}}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "\x1b[" not in contents
        assert "ERROR:" in contents
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `get_log` doesn't accept `errors_only` parameter.

**Step 3: Update get_log with errors_only mode**

Replace `get_log` in `main.py` with:

```python
import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ERROR_RE = re.compile(
    r"(ERROR|FAIL|FAILED|TIMEOUT|FATAL|error:|failure:)", re.IGNORECASE
)
_SUMMARY_RE = re.compile(r"Executed \d+ out of \d+ tests?:")


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

    context_radius = 3
    matched_indices: set[int] = set()
    summary_line = None

    for i, line in enumerate(lines):
        if _ERROR_RE.search(line):
            for j in range(max(0, i - context_radius), min(len(lines), i + context_radius + 1)):
                matched_indices.add(j)
        if _SUMMARY_RE.search(line):
            summary_line = line

    filtered = [lines[i] for i in sorted(matched_indices)]
    if summary_line and summary_line not in filtered:
        filtered.append(summary_line)

    return {"log": {"contents": "\n".join(filtered)}}
```

**Important:** The `import re` and the compiled regexes (`_ANSI_RE`, `_ERROR_RE`, `_SUMMARY_RE`) should go near the top of `main.py`, after the existing imports (around line 6). The `get_log` function body references them.

**Step 4: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add errors_only mode to get_log"
```

---

### Task 6: Add missing params to execute_workflow

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py` (execute_workflow function)
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing test**

Add to `TestExecuteWorkflow` in `main_test.py`:

```python
    @pytest.mark.asyncio
    async def test_passes_env_and_visibility(self):
        expected = {
            "action_statuses": [
                {"action_name": "Test", "invocation_id": "inv-1"}
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            await execute_workflow(
                repo_url="https://github.com/jomcgi/homelab",
                branch="main",
                env={"FOO": "bar"},
                visibility="PUBLIC",
                disable_retry=True,
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["env"] == {"FOO": "bar"}
        assert call_body["visibility"] == "PUBLIC"
        assert call_body["disable_retry"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `execute_workflow` doesn't accept `env`, `visibility`, `disable_retry`.

**Step 3: Update execute_workflow**

Replace `execute_workflow` in `main.py` with:

```python
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
```

**Step 4: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 5: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add env, visibility, disable_retry to execute_workflow"
```

---

### Task 7: Add run tool

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py`
- Modify: `services/buildbuddy_mcp/tests/main_test.py`

**Step 1: Write the failing test**

Add to `main_test.py`, import `run` at the top (add it to the existing import block from `services.buildbuddy_mcp.app.main`), and add a new test class at the end:

```python
class TestRun:
    @pytest.mark.asyncio
    async def test_sends_steps_as_run_dicts(self):
        expected = {"invocation_id": "run-inv-1"}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            result = await run(
                repo_url="https://github.com/jomcgi/homelab",
                steps=["bazel test //pkg:test", "echo done"],
                branch="main",
                timeout="15m",
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["steps"] == [
            {"run": "bazel test //pkg:test"},
            {"run": "echo done"},
        ]
        assert call_body["repo"] == "https://github.com/jomcgi/homelab"
        assert call_body["branch"] == "main"
        assert call_body["timeout"] == "15m"
        assert result["invocation_id"] == "run-inv-1"

    @pytest.mark.asyncio
    async def test_passes_env_and_wait_until(self):
        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"invocation_id": "x"},
        ) as mock_post:
            await run(
                repo_url="https://github.com/jomcgi/homelab",
                steps=["echo hi"],
                env={"KEY": "val"},
                wait_until="STARTED",
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["env"] == {"KEY": "val"}
        assert call_body["wait_until"] == "STARTED"
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: FAIL — `run` function doesn't exist.

**Step 3: Implement run tool**

Add to `main.py`, before the `main()` function:

```python
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
```

**Step 4: Update imports in test file**

Add `run` to the import block at the top of `main_test.py`:

```python
from services.buildbuddy_mcp.app.main import (
    Settings,
    configure,
    execute_workflow,
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    run,
)
```

**Step 5: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:main_test`

Expected: ALL PASS

**Step 6: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add run tool for remote command execution"
```

---

### Task 8: Improve get_action docstring

Minimal change — just improve the docstring to document `configuration_id` and the `action_id` gotcha.

**Files:**
- Modify: `services/buildbuddy_mcp/app/main.py` (get_action docstring)

**Step 1: Update the docstring**

Replace the `get_action` docstring in `main.py` with:

```python
    """Get actions for a target in an invocation.

    Returns action details including test shard, run, and attempt info,
    plus file references (test logs, outputs) with bytestream URIs.

    Use target_label or target_id to scope results to a single target.
    action_id alone returns all targets sharing that ID — always combine
    with target_id for a single result.
    configuration_id is a bazel configuration hash, useful for precise lookups.
    """
```

**Step 2: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "docs(buildbuddy-mcp): improve get_action docstring with usage guidance"
```

---

### Task 9: Create composite.py with diagnose_failure

**Files:**
- Create: `services/buildbuddy_mcp/app/composite.py`
- Create: `services/buildbuddy_mcp/tests/composite_test.py`
- Modify: `services/buildbuddy_mcp/app/main.py` (add import of composite at bottom)

**Step 1: Write the failing test**

Create `services/buildbuddy_mcp/tests/composite_test.py`:

```python
"""Tests for BuildBuddy MCP composite tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.buildbuddy_mcp.app.main import Settings, configure


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(api_key="test-key", url="https://test.buildbuddy.io"))


class TestDiagnoseFailure:
    @pytest.mark.asyncio
    async def test_returns_failed_targets_with_logs(self):
        import base64

        from services.buildbuddy_mcp.app.composite import diagnose_failure

        test_log_b64 = base64.b64encode(b"FAIL: assertion error").decode()

        async def mock_post(endpoint, body):
            if endpoint == "/GetInvocation":
                return {
                    "invocation": [
                        {
                            "id": {"invocation_id": "wf-1"},
                            "command": "workflow run",
                            "success": False,
                            "child_invocations": [
                                {"invocation_id": "test-inv-1"},
                            ],
                        }
                    ]
                }
            if endpoint == "/GetTarget":
                return {
                    "target": [
                        {"label": "//pkg:test", "status": "FAILED", "timing": {"duration": "1.2s"}},
                    ]
                }
            if endpoint == "/GetAction":
                return {
                    "action": [
                        {
                            "target_label": "//pkg:test",
                            "file": [
                                {"name": "test.log", "uri": "bytestream://x/blobs/abc/100"},
                            ],
                        }
                    ]
                }
            if endpoint == "/GetFile":
                return {"data": test_log_b64}
            if endpoint == "/GetLog":
                return {"log": {"contents": "ERROR: //pkg:test failed\nExecuted 1 out of 1 tests: 0 pass, 1 fails.\n"}}
            return {}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await diagnose_failure(invocation_id="wf-1")

        assert result["status"] == "FAILED"
        assert len(result["failed_targets"]) == 1
        assert result["failed_targets"][0]["label"] == "//pkg:test"
        assert "assertion error" in result["failed_targets"][0]["test_log"]
        assert "build_errors" in result

    @pytest.mark.asyncio
    async def test_returns_success_when_no_failures(self):
        from services.buildbuddy_mcp.app.composite import diagnose_failure

        async def mock_post(endpoint, body):
            if endpoint == "/GetInvocation":
                return {
                    "invocation": [
                        {
                            "id": {"invocation_id": "wf-1"},
                            "command": "workflow run",
                            "success": True,
                            "child_invocations": [
                                {"invocation_id": "test-inv-1"},
                            ],
                        }
                    ]
                }
            if endpoint == "/GetTarget":
                return {
                    "target": [
                        {"label": "//pkg:test", "status": "PASSED"},
                    ]
                }
            if endpoint == "/GetLog":
                return {"log": {"contents": "Executed 1 out of 1 tests: 1 pass.\n"}}
            return {}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await diagnose_failure(invocation_id="wf-1")

        assert result["status"] == "SUCCESS"
        assert result["failed_targets"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:composite_test`

Expected: FAIL — `composite.py` doesn't exist.

**Step 3: Create composite.py**

Create `services/buildbuddy_mcp/app/composite.py`:

```python
"""Composite BuildBuddy MCP tools that orchestrate multiple API calls."""

from __future__ import annotations

from services.buildbuddy_mcp.app.main import (
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    mcp,
)


def _find_test_invocation(invocations: list[dict]) -> dict | None:
    """Find the inner bazel test invocation from a list of invocations."""
    for inv in invocations:
        if inv.get("command") == "test":
            return inv
    return None


@mcp.tool
async def diagnose_failure(
    invocation_id: str | None = None,
    commit_sha: str | None = None,
) -> dict:
    """One-shot CI failure diagnosis.

    Given a workflow invocation ID or commit SHA, finds failed tests,
    retrieves their test logs, and extracts error lines from the build
    log. Returns everything needed to understand a CI failure in a
    single tool call.
    """
    # Step 1: Get the invocation with child invocations
    inv_result = await get_invocation(
        invocation_id=invocation_id,
        commit_sha=commit_sha,
        include_child_invocations=True,
    )
    if "error" in inv_result:
        return inv_result
    invocations = inv_result.get("invocation", [])
    if not invocations:
        return {"error": "No invocation found"}

    # Find the workflow invocation and its children
    workflow_inv = invocations[0]
    child_ids = [
        c.get("invocation_id") or c.get("invocationId")
        for c in workflow_inv.get("child_invocations", workflow_inv.get("childInvocations", []))
    ]

    # Step 2: Find the inner test invocation
    test_inv_id = None
    if child_ids:
        for child_id in child_ids:
            child_result = await get_invocation(invocation_id=child_id)
            if "error" not in child_result:
                for inv in child_result.get("invocation", []):
                    if inv.get("command") == "test":
                        test_inv_id = inv["id"].get("invocation_id") or inv["id"].get("invocationId")
                        break
            if test_inv_id:
                break

    target_inv_id = test_inv_id or (workflow_inv["id"].get("invocation_id") or workflow_inv["id"].get("invocationId"))

    # Step 3: Get failed targets
    target_result = await get_target(invocation_id=target_inv_id, status="FAILED")
    failed_targets = target_result.get("target", [])

    # Step 4: For each failed target, get test logs
    enriched_targets = []
    for target in failed_targets:
        target_label = target.get("label", "")
        entry = {
            "label": target_label,
            "status": target.get("status"),
            "timing": target.get("timing"),
            "test_log": None,
        }

        action_result = await get_action(
            invocation_id=target_inv_id,
            target_label=target_label,
        )
        for action in action_result.get("action", []):
            for f in action.get("file", []):
                if f.get("name") == "test.log" and f.get("uri"):
                    file_result = await get_file(uri=f["uri"])
                    if "contents" in file_result:
                        entry["test_log"] = file_result["contents"]
                    break
            if entry["test_log"]:
                break

        enriched_targets.append(entry)

    # Step 5: Get error lines from build log
    log_result = await get_log(invocation_id=target_inv_id, errors_only=True)
    build_errors = log_result.get("log", {}).get("contents", "")

    total_targets = target_result.get("_total_before_filter", len(failed_targets))
    status = "FAILED" if failed_targets else "SUCCESS"
    summary = (
        f"{len(failed_targets)} of {total_targets} targets failed"
        if failed_targets
        else "All targets passed"
    )

    return {
        "invocation_id": target_inv_id,
        "status": status,
        "summary": summary,
        "failed_targets": enriched_targets,
        "build_errors": build_errors,
    }
```

**Step 4: Import composite from main.py**

Add at the very end of `main.py`, just before the `main()` function:

```python
import services.buildbuddy_mcp.app.composite as _composite  # noqa: F401, E402
```

This triggers composite tool registration on the shared `mcp` instance.

**Step 5: Run tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:composite_test`

Expected: ALL PASS. Also verify the full suite still passes:

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/...`

**Step 6: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "feat(buildbuddy-mcp): add diagnose_failure composite tool"
```

---

### Task 10: Create proto conformance test

**Files:**
- Create: `services/buildbuddy_mcp/tests/proto_conformance_test.py`

**Step 1: Write the test**

Create `services/buildbuddy_mcp/tests/proto_conformance_test.py`:

```python
"""Proto conformance tests — validates our tool parameters match BuildBuddy's API.

Tagged 'external' because it fetches proto files from GitHub at test time.
Run manually: bazel test //services/buildbuddy_mcp/tests:proto_conformance_test
Excluded from CI via --test_tag_filters=-external.
"""

from __future__ import annotations

import inspect
import re

import httpx
import pytest

from services.buildbuddy_mcp.app.main import (
    execute_workflow,
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    run,
)

PROTO_BASE = "https://raw.githubusercontent.com/buildbuddy-io/buildbuddy/master/proto/api/v1"

# Parameters we add client-side that don't exist in the proto
CLIENT_SIDE_PARAMS = {
    "get_target": {"status"},
    "get_log": {"errors_only"},
    "get_invocation": {"include_child_invocations", "include_metadata", "include_artifacts"},
    "execute_workflow": {"run_async", "env", "visibility", "disable_retry"},
    "run": {"repo_url", "steps", "env", "timeout", "wait_until"},
}

# Map our function params to proto field names (when they differ)
PARAM_TO_PROTO = {
    "run_async": "async",
    "repo_url": "repo_url",
}


def _fetch_proto(filename: str) -> str:
    """Fetch a proto file from BuildBuddy's GitHub repo."""
    resp = httpx.get(f"{PROTO_BASE}/{filename}", timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_selector_fields(proto_text: str, message_name: str) -> set[str]:
    """Extract field names from a protobuf message definition."""
    pattern = rf"message {message_name}\s*\{{([^}}]+)\}}"
    match = re.search(pattern, proto_text, re.DOTALL)
    if not match:
        return set()
    body = match.group(1)
    # Match field definitions: type name = N;
    fields = re.findall(r"(?:repeated\s+)?\w+\s+(\w+)\s*=\s*\d+", body)
    return set(fields)


def _get_tool_params(func) -> set[str]:
    """Get parameter names from a tool function, excluding 'self'."""
    sig = inspect.signature(func)
    return {p for p in sig.parameters if p != "self"}


def _snake_to_proto(name: str) -> str:
    """Our params are already snake_case matching proto convention."""
    return PARAM_TO_PROTO.get(name, name)


class TestTargetProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("target.proto")

    def test_selector_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "TargetSelector")
        our_params = _get_tool_params(get_target)
        client_side = CLIENT_SIDE_PARAMS.get("get_target", set())

        # Every proto selector field should be a parameter on our tool
        for field in proto_fields:
            assert field in our_params or field in {"invocation_id"}, (
                f"Proto field '{field}' in TargetSelector not exposed in get_target. "
                f"Our params: {our_params}"
            )

        # Every non-client-side param should map to a proto field or standard param
        standard = {"page_token", "invocation_id"}
        for param in our_params - client_side - standard:
            proto_name = _snake_to_proto(param)
            assert proto_name in proto_fields, (
                f"Tool param '{param}' not in TargetSelector proto. "
                f"Proto fields: {proto_fields}. "
                f"If this is intentional, add to CLIENT_SIDE_PARAMS."
            )


class TestActionProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("action.proto")

    def test_selector_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "ActionSelector")
        our_params = _get_tool_params(get_action)
        client_side = CLIENT_SIDE_PARAMS.get("get_action", set())

        for field in proto_fields:
            assert field in our_params or field in {"invocation_id"}, (
                f"Proto field '{field}' in ActionSelector not exposed in get_action. "
                f"Our params: {our_params}"
            )

        standard = {"page_token", "invocation_id"}
        for param in our_params - client_side - standard:
            proto_name = _snake_to_proto(param)
            assert proto_name in proto_fields, (
                f"Tool param '{param}' not in ActionSelector proto. "
                f"Proto fields: {proto_fields}"
            )


class TestFileProtoConformance:
    @pytest.fixture(autouse=True)
    def _fetch(self):
        self.proto = _fetch_proto("file.proto")

    def test_request_fields_covered(self):
        proto_fields = _parse_selector_fields(self.proto, "GetFileRequest")
        our_params = _get_tool_params(get_file)
        client_side = CLIENT_SIDE_PARAMS.get("get_file", set())

        for field in proto_fields:
            assert field in our_params, (
                f"Proto field '{field}' in GetFileRequest not exposed in get_file. "
                f"Our params: {our_params}"
            )


class TestNewProtoFields:
    """Informational: report any new proto fields we haven't adopted."""

    def test_report_unadopted_target_fields(self):
        proto = _fetch_proto("target.proto")
        target_fields = _parse_selector_fields(proto, "Target")
        known_fields = {"id", "label", "status", "timing", "rule_type", "tag", "language"}
        new_fields = target_fields - known_fields
        if new_fields:
            pytest.skip(f"New Target proto fields detected (not a failure): {new_fields}")

    def test_report_unadopted_action_fields(self):
        proto = _fetch_proto("action.proto")
        action_fields = _parse_selector_fields(proto, "Action")
        known_fields = {"id", "file", "target_label", "shard", "run", "attempt"}
        new_fields = action_fields - known_fields
        if new_fields:
            pytest.skip(f"New Action proto fields detected (not a failure): {new_fields}")
```

**Step 2: Run the test**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:proto_conformance_test`

Expected: PASS (or skip for informational tests). This test hits GitHub so it needs network access.

**Step 3: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/
git commit -m "test(buildbuddy-mcp): add proto conformance test for API drift detection"
```

---

### Task 11: Update BUILD files and run gazelle

**Files:**
- Modify: `services/buildbuddy_mcp/app/BUILD`
- Modify: `services/buildbuddy_mcp/tests/BUILD`

**Step 1: Run gazelle to regenerate BUILD files**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel run gazelle`

This will pick up the new `composite.py` and test files. Check the output.

**Step 2: Verify app/BUILD includes composite.py**

Read `services/buildbuddy_mcp/app/BUILD`. The `app` library should now include both `main.py` and `composite.py` in its `srcs`. If gazelle created a separate target for composite, that's fine — ensure the `main` binary still depends on it.

**Step 3: Verify tests/BUILD includes new test targets**

Read `services/buildbuddy_mcp/tests/BUILD`. It should have three test targets:
- `main_test` — existing, no tags
- `composite_test` — new, no tags
- `proto_conformance_test` — new, with `tags = ["external"]`

If gazelle didn't add the `external` tag, manually add it:

```python
py_test(
    name = "proto_conformance_test",
    srcs = ["proto_conformance_test.py"],
    tags = ["external"],
    deps = [
        "//services/buildbuddy_mcp/app",
        "@pip//httpx",
        "@pip//pytest",
    ],
)
```

**Step 4: Add gazelle resolve hints if needed**

If gazelle can't resolve the composite import, add a resolve hint to `tests/BUILD`:

```python
# gazelle:resolve py services.buildbuddy_mcp.app.composite //services/buildbuddy_mcp/app:app
```

**Step 5: Run all tests**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/... --test_tag_filters=-external`

Expected: ALL PASS (excluding the external-tagged proto conformance test).

**Step 6: Run format**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && format`

This ensures BUILD files are formatted and any lock files are updated.

**Step 7: Commit**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git add services/buildbuddy_mcp/ images/BUILD
git commit -m "build(buildbuddy-mcp): update BUILD files for v2 tools and tests"
```

---

### Task 12: Full verification and push

**Step 1: Run full test suite**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //... --test_tag_filters=-external`

Expected: ALL PASS, no regressions.

**Step 2: Run proto conformance test separately**

Run: `cd /tmp/claude-worktrees/buildbuddy-mcp-v2 && bazel test //services/buildbuddy_mcp/tests:proto_conformance_test`

Expected: PASS (may skip informational tests about new fields).

**Step 3: Push and create PR**

```bash
cd /tmp/claude-worktrees/buildbuddy-mcp-v2
git push -u origin feat/buildbuddy-mcp-v2
gh pr create --title "feat(buildbuddy-mcp): v2 — error handling, context reduction, run tool, proto conformance" --body "$(cat <<'EOF'
## Summary

- **Fix get_file** — decode base64 API response to UTF-8 text (was completely broken)
- **Add client-side status filter to get_target** — `status="FAILED"` reduces 258KB→500B for CI debugging
- **Add errors_only mode to get_log** — strips to error lines with context
- **Add include_child_invocations to get_invocation** — navigate workflow→inner bazel invocations
- **Add run tool** — remote command execution via /Run endpoint (bazel query, test repro)
- **Add diagnose_failure composite tool** — one-shot CI failure diagnosis (replaces 5 sequential calls)
- **Add env/visibility/disable_retry to execute_workflow**
- **Robust error handling** — return error dicts instead of triggering schema validation failures
- **Proto conformance test** — external-tagged test that fetches BuildBuddy protos from GitHub and validates our tool params match

## Test plan

- [ ] `bazel test //services/buildbuddy_mcp/... --test_tag_filters=-external` passes
- [ ] `bazel test //services/buildbuddy_mcp/tests:proto_conformance_test` passes
- [ ] Full suite `bazel test //... --test_tag_filters=-external` passes
- [ ] CI passes (Format check + Test and push)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
