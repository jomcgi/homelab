# BuildBuddy MCP Server v2 — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the BuildBuddy MCP server with missing API parameters, context-reducing composite tools, robust error handling, and proto conformance testing.

**Motivation:** Evaluation of the v1 server revealed: `get_file` is completely broken (base64 decode issue), unfiltered `get_target`/`get_action` dump 250-400KB into context, the #1 use case (diagnosing CI failures) requires 5 sequential tool calls, and several API parameters aren't exposed.

---

## Architecture

**Approach C: Primitives + Composites** — two-file structure.

```
services/buildbuddy_mcp/
├── app/
│   ├── main.py          # FastMCP server, Settings, HTTP client, primitive API tools
│   ├── composite.py     # Smart composite tools (diagnose_failure)
│   └── BUILD
├── tests/
│   ├── main_test.py              # Unit tests for primitive tools
│   ├── composite_test.py         # Unit tests for composite tools
│   ├── proto_conformance_test.py # External-tagged proto drift detection
│   └── BUILD
└── BUILD
```

`composite.py` imports the `mcp` instance from `main.py` and registers tools on it. Both files share the `_post` helper. `main.py` imports `composite` at startup to trigger tool registration.

---

## Primitive Tool Changes (main.py)

### Error handling — all tools

Wrap `_post` to return valid empty structures instead of triggering FastMCP output schema validation errors:

- Empty results → `{"target": []}`, `{"invocation": []}`, etc.
- API HTTP errors → `{"error": "BuildBuddy API error: <status> <message>"}`
- Not found → `{"error": "No results found for ..."}`

### get_invocation — add include flags

New parameters (top-level request fields, not selector fields):

| Parameter                   | Type   | Purpose                                    |
| --------------------------- | ------ | ------------------------------------------ |
| `include_child_invocations` | `bool` | Return child invocation IDs from workflows |
| `include_metadata`          | `bool` | Return build_metadata and workspace_status |
| `include_artifacts`         | `bool` | Return attached artifacts                  |

`include_child_invocations` is the key addition — enables navigating from workflow invocation to inner bazel invocations without commit_sha lookup.

### get_target — add server-side status filter

New parameter:

| Parameter | Type          | Purpose                                          |
| --------- | ------------- | ------------------------------------------------ |
| `status`  | `str \| None` | Client-side filter: PASSED, FAILED, BUILT, FLAKY |

The BuildBuddy API does not support status filtering. The MCP server fetches all targets (paginating if needed), filters to matching statuses, and returns the filtered list. Tool description must state this is client-side.

This is the single biggest context reduction — turns 258KB (1,075 targets) into ~500 bytes (2 failed targets) for the CI debugging use case.

### get_log — add errors_only mode

New parameter:

| Parameter     | Type   | Purpose                        |
| ------------- | ------ | ------------------------------ |
| `errors_only` | `bool` | Strip to error lines + context |

When `errors_only=True`:

1. Fetch all log pages (follow `next_page_token`)
2. Strip ANSI escape codes
3. Filter to lines matching: `ERROR`, `FAILED`, `TIMEOUT`, `FATAL`, `error:`, `failure:`
4. Include 3 lines of surrounding context per match
5. Always include the final summary line (`Executed X out of Y tests:...`)
6. Return as single string (no pagination — filtered output is small)

### get_file — fix base64 decode

The API returns `{"data": "<base64-encoded bytes>"}` (protobuf `bytes` → base64 in JSON). Fix:

1. Decode base64 `data` field
2. Attempt UTF-8 decode (test logs, test.xml are always text)
3. If UTF-8 fails, return `{"error": "Binary file, cannot display as text", "size_bytes": N}`
4. Return: `{"contents": "<decoded text>"}`

### execute_workflow — add missing params

New parameters:

| Parameter       | Type                     | Purpose                        |
| --------------- | ------------------------ | ------------------------------ |
| `env`           | `dict[str, str] \| None` | Environment variable overrides |
| `visibility`    | `str \| None`            | "PUBLIC" or private (default)  |
| `disable_retry` | `bool`                   | Disable automatic retry        |

### run — new tool

New tool mapping to BuildBuddy's `/Run` endpoint:

```python
async def run(
    repo_url: str,
    steps: list[str],              # ["bazel test //pkg:test", "bazel query 'deps(//...)'"]
    branch: str | None = None,
    commit_sha: str | None = None,
    env: dict[str, str] | None = None,
    timeout: str | None = None,    # "15m", "2h"
    wait_until: str = "COMPLETED", # QUEUED, STARTED, COMPLETED
) -> dict:
```

Each string in `steps` becomes `{"run": step}`. Covers:

- `bazel query` without local bazel
- `bazel test //specific:target` for reproducing failures
- Arbitrary remote command execution

---

## Composite Tool (composite.py)

### diagnose_failure — one-shot CI failure diagnosis

```python
async def diagnose_failure(
    invocation_id: str | None = None,
    commit_sha: str | None = None,
) -> dict:
```

Orchestrates the full failure investigation:

1. `get_invocation(include_child_invocations=True)` → find workflow + children
2. Identify the inner `bazel test` invocation (command=`test`)
3. `get_target(status="FAILED")` → get failed targets only
4. For each failed target: `get_action(target_label=...)` → get test log URIs
5. For each test log: `get_file(uri=...)` → decode contents
6. `get_log(errors_only=True)` → error summary from build log

Returns:

```json
{
  "invocation_id": "...",
  "status": "FAILED",
  "summary": "2 of 105 tests failed",
  "failed_targets": [
    {
      "label": "//pkg:test",
      "status": "FAILED",
      "timing": { "duration": "1.2s" },
      "test_log": "... decoded test.log contents ..."
    }
  ],
  "build_errors": "... filtered error lines from build log ..."
}
```

If invocation is successful, returns success summary instead. If called with `commit_sha`, picks the most recent workflow invocation.

---

## Proto Conformance Test

`proto_conformance_test.py` — tagged `external` (excluded from `bazel test //... --test_tag_filters=-external`).

### What it does

1. Fetches `target.proto`, `action.proto`, `file.proto` from `raw.githubusercontent.com/buildbuddy-io/buildbuddy/master/proto/api/v1/`
2. Parses proto files with regex to extract selector/request message field names
3. Uses `inspect.signature()` to get our tool function parameters
4. Asserts:
   - Every selector field in proto has a corresponding tool parameter
   - No unknown parameters exist (client-side additions like `status`, `errors_only` are allowlisted)
5. Reports proto fields we haven't adopted yet (informational, not failures)

### How to run

```bash
bazel test //services/buildbuddy_mcp/tests:proto_conformance_test
```

(Must explicitly target it — excluded from `//...` by tag.)

### BUILD configuration

```python
py_test(
    name = "proto_conformance_test",
    srcs = ["proto_conformance_test.py"],
    tags = ["external"],
    deps = [
        "//services/buildbuddy_mcp/app",
        "@pip//pytest",
        "@pip//httpx",
    ],
)
```

---

## Tool Summary

| Tool               | Type            | Change                                                                   |
| ------------------ | --------------- | ------------------------------------------------------------------------ |
| `get_invocation`   | Primitive       | Add `include_child_invocations`, `include_metadata`, `include_artifacts` |
| `get_log`          | Primitive       | Add `errors_only` mode                                                   |
| `get_target`       | Primitive       | Add client-side `status` filter                                          |
| `get_action`       | Primitive       | Improve docstrings only                                                  |
| `get_file`         | Primitive       | Fix base64 decode to UTF-8 text                                          |
| `execute_workflow` | Primitive       | Add `env`, `visibility`, `disable_retry`                                 |
| `run`              | Primitive (NEW) | Remote command execution via /Run endpoint                               |
| `diagnose_failure` | Composite (NEW) | One-shot CI failure diagnosis                                            |

## Non-goals

- No UI changes
- No deployment config changes (same image, same chart)
- No new dependencies (httpx already supports what we need)
