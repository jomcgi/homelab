# Semgrep App Upload — Design

## Problem

Semgrep scans run hermetically inside Bazel with local rules and the Pro engine.
Scan results are only visible in Bazel test output — there is no integration with
the Semgrep App platform for centralized visibility, trend tracking, or triage.

## Goal

Best-effort upload of scan results to Semgrep App after each scan, without
affecting hermeticity, cacheability, or test pass/fail behavior.

## Constraints

- Upload must never fail the Bazel action
- Upload must only fire on cache misses (actual scan executions)
- Pro engine runs fully offline
- No new pip dependencies (httpx 0.28.1 already in requirements)
- Both source file scans and manifest scans get upload support
- Test mode (`SEMGREP_TEST_MODE=1`) does not upload

## Design

### Upload Script (`tools/semgrep/upload.py`)

A `py_binary` target using httpx to implement the 3-step Semgrep App API flow:

1. **Register scan** — `POST /api/cli/scans` with repo/branch/commit metadata
2. **Upload findings** — `POST /api/agent/scans/{id}/results` with JSON output
3. **Mark complete** — `POST /api/agent/scans/{id}/complete` with exit code

**Inputs:**

- `argv[1]`: path to semgrep JSON results file
- `argv[2]`: scan exit code (0 = clean, non-zero = findings)

**Environment:**

| Variable            | Required        | Default               | Source                      |
| ------------------- | --------------- | --------------------- | --------------------------- |
| `SEMGREP_APP_TOKEN` | Yes (to upload) | —                     | Secret from CI or local env |
| `SEMGREP_APP_URL`   | No              | `https://semgrep.dev` | Override for self-hosted    |
| `SEMGREP_REPO`      | No              | Auto-detected         | `git remote get-url origin` |

Git commit and branch are auto-detected via `git rev-parse` commands. Since
tests run with `no-sandbox`, git is available. CI environments also provide
these via standard env vars (`GITHUB_SHA`, `GIT_BRANCH`, etc.).

**Error handling:** Every HTTP call wrapped in try/except. Failures log a
warning to stderr and the script always exits 0. The wrapper script also
applies `|| true` as defense in depth.

**Timeout:** 10-second timeout on all HTTP calls via `httpx.Client(timeout=10)`.

### Bazel Rule Changes (`rules_semgrep/test.bzl`)

Both `semgrep_test` and `semgrep_manifest_test` macros updated:

- Add `//tools/semgrep:upload` to `data` deps
- Add `UPLOAD_SCRIPT` env var pointing to the upload binary via `$(rootpath)`
- No new user-facing parameters — upload is controlled entirely by
  `SEMGREP_APP_TOKEN` at runtime

### BUILD Changes (`tools/semgrep/BUILD`)

New target:

```python
py_binary(
    name = "upload",
    srcs = ["upload.py"],
    deps = ["@pip//httpx"],
    visibility = ["//visibility:public"],
)
```

### Wrapper Script Changes

Both `semgrep-test.sh` and `semgrep-manifest-test.sh` modified at the scan
invocation. The pattern is identical for both:

**Before:**

```bash
if "$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore "$SCAN_DIR"; then
    echo "PASSED: No semgrep findings"
    exit 0
else
    echo "FAILED: Semgrep found violations"
    exit 1
fi
```

**After:**

```bash
SCAN_EXIT=0
"$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore \
    --json --output "$TEST_TMPDIR/results.json" \
    "$SCAN_DIR" || SCAN_EXIT=$?

# Best-effort upload (never affects exit code)
if [[ -n "${SEMGREP_APP_TOKEN:-}" && -n "${UPLOAD_SCRIPT:-}" ]]; then
    "$UPLOAD_SCRIPT" "$TEST_TMPDIR/results.json" "$SCAN_EXIT" 2>&1 || true
fi

if [[ "$SCAN_EXIT" -eq 0 ]]; then
    echo "PASSED: No semgrep findings"
else
    echo "FAILED: Semgrep found violations"
fi
exit "$SCAN_EXIT"
```

Test mode (`SEMGREP_TEST_MODE=1`) is unchanged — rule validation does not upload.

## Files Changed

| File                                     | Change                                      |
| ---------------------------------------- | ------------------------------------------- |
| `tools/semgrep/upload.py`                | New — upload script                         |
| `tools/semgrep/BUILD`                    | Add `py_binary` for upload                  |
| `rules_semgrep/test.bzl`                 | Add upload to data/env in both macros       |
| `rules_semgrep/semgrep-test.sh`          | Capture exit code, output JSON, call upload |
| `rules_semgrep/semgrep-manifest-test.sh` | Same pattern as above                       |

## Cache Behavior

No change to cache semantics. The upload is a side effect inside the test
action. On cache hits, the action is skipped entirely — no upload fires.
On cache misses, the scan runs and upload is attempted. The `--json --output`
flag does not affect the exit code or declared outputs.

## Testing

- Run `bazel test //...` without `SEMGREP_APP_TOKEN` — behavior identical to today
- Run with `SEMGREP_APP_TOKEN` set — verify upload succeeds in Semgrep App
- Run with `SEMGREP_APP_TOKEN` set but network blocked — verify test still passes
- Run same test twice — verify second run is cached (no upload)
