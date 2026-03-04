# Semgrep App Upload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Best-effort upload of semgrep scan results to the Semgrep App platform after each Bazel test action, without affecting hermeticity, cacheability, or pass/fail behavior.

**Architecture:** A Python upload script (`py_binary` with httpx) is called from the existing wrapper scripts after the scan completes. Upload is gated on `SEMGREP_APP_TOKEN` being set and wrapped in `|| true`. Both source file and manifest scan wrappers get the same modification.

**Tech Stack:** Python 3.13 (hermetic via `@rules_python`), httpx 0.28.1 (`@pip//httpx`), Bazel `sh_test` + `py_binary`

**Design doc:** `docs/plans/2026-03-03-semgrep-app-upload-design.md`

---

### Task 1: Create the upload script

**Files:**
- Create: `tools/semgrep/upload.py`

**Step 1: Write `upload.py`**

```python
"""Best-effort upload of semgrep scan results to Semgrep App.

Called from semgrep-test.sh / semgrep-manifest-test.sh after the scan completes.
Always exits 0 — upload failures must never affect the Bazel test result.

Usage: upload.py <results-json-path> <scan-exit-code>

Environment:
    SEMGREP_APP_TOKEN  — required; skips upload silently if unset
    SEMGREP_APP_URL    — optional; defaults to https://semgrep.dev
    SEMGREP_REPO       — optional; auto-detected from git remote
"""

import json
import subprocess
import sys
import uuid

import httpx

TIMEOUT = 10


def _git(cmd: str) -> str:
    """Run a git command, return stdout or empty string on failure."""
    try:
        return subprocess.run(
            ["git"] + cmd.split(),
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _detect_repo() -> str:
    """Detect repository name from env or git remote."""
    import os

    repo = os.environ.get("SEMGREP_REPO")
    if repo:
        return repo

    # Try git remote URL → extract org/repo
    remote = _git("remote get-url origin")
    if remote:
        # Handle both SSH and HTTPS URLs
        # git@github.com:org/repo.git → org/repo
        # https://github.com/org/repo.git → org/repo
        remote = remote.rstrip(".git")
        if ":" in remote and "@" in remote:
            return remote.split(":")[-1]
        parts = remote.split("/")
        if len(parts) >= 2:
            return "/".join(parts[-2:])

    return "unknown/unknown"


def _detect_commit() -> str:
    """Detect git commit from env or git."""
    import os

    return (
        os.environ.get("GITHUB_SHA")
        or os.environ.get("GIT_COMMIT")
        or _git("rev-parse HEAD")
        or "unknown"
    )


def _detect_branch() -> str:
    """Detect git branch from env or git."""
    import os

    return (
        os.environ.get("GITHUB_REF_NAME")
        or os.environ.get("GIT_BRANCH")
        or _git("rev-parse --abbrev-ref HEAD")
        or "unknown"
    )


def _detect_semgrep_version() -> str:
    """Read semgrep version from the results JSON or fall back to hardcoded."""
    return "1.153.1"


def main() -> None:
    import os

    token = os.environ.get("SEMGREP_APP_TOKEN")
    if not token:
        return

    if len(sys.argv) < 3:
        print("upload.py: expected <results-path> <exit-code>", file=sys.stderr)
        return

    results_path = sys.argv[1]
    scan_exit_code = int(sys.argv[2])
    base_url = os.environ.get("SEMGREP_APP_URL", "https://semgrep.dev").rstrip("/")

    try:
        with open(results_path) as f:
            results = json.load(f)
    except Exception as e:
        print(f"upload.py: failed to read results: {e}", file=sys.stderr)
        return

    repo = _detect_repo()
    commit = _detect_commit()
    branch = _detect_branch()
    version = _detect_semgrep_version()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            # Step 1: Register scan
            scan_response = client.post(
                f"{base_url}/api/cli/scans",
                headers=headers,
                json={
                    "scan_metadata": {
                        "cli_version": version,
                        "unique_id": str(uuid.uuid4()),
                        "requested_products": ["sast"],
                        "dry_run": False,
                    },
                    "project_metadata": {
                        "semgrep_version": version,
                        "repository": repo,
                        "repo_url": f"https://github.com/{repo}",
                        "branch": branch,
                        "commit": commit,
                        "is_full_scan": True,
                    },
                },
            )
            scan_response.raise_for_status()
            scan_id = scan_response.json()["info"]["id"]

            # Step 2: Upload findings
            client.post(
                f"{base_url}/api/agent/scans/{scan_id}/results",
                headers=headers,
                json=results,
            ).raise_for_status()

            # Step 3: Mark scan complete
            client.post(
                f"{base_url}/api/agent/scans/{scan_id}/complete",
                headers=headers,
                json={"exit_code": scan_exit_code},
            ).raise_for_status()

            print(f"upload.py: uploaded to {base_url} (scan {scan_id})", file=sys.stderr)

    except Exception as e:
        print(f"upload.py: upload failed (non-fatal): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**Step 2: Verify the file exists and has no syntax errors**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && python3 -c "import ast; ast.parse(open('tools/semgrep/upload.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add tools/semgrep/upload.py
git commit -m "feat(semgrep): add best-effort upload script for Semgrep App"
```

---

### Task 2: Add py_binary target to BUILD

**Files:**
- Modify: `tools/semgrep/BUILD`

**Step 1: Add the `py_binary` target**

Add to end of `tools/semgrep/BUILD`:

```python
load("@rules_python//python:py_binary.bzl", "py_binary")

py_binary(
    name = "upload",
    srcs = ["upload.py"],
    deps = ["@pip//httpx"],
    visibility = ["//visibility:public"],
)
```

**Step 2: Verify the target resolves**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel query //tools/semgrep:upload`
Expected: `//tools/semgrep:upload`

**Step 3: Verify it builds**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel build //tools/semgrep:upload`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add tools/semgrep/BUILD
git commit -m "build(semgrep): add py_binary target for upload script"
```

---

### Task 3: Wire upload into Bazel rules

**Files:**
- Modify: `rules_semgrep/test.bzl:33-36` (semgrep_test data list)
- Modify: `rules_semgrep/test.bzl:95-100` (semgrep_manifest_test data list)

**Step 1: Add upload to `semgrep_test` data and env**

In `semgrep_test`, change the `data` list (line 33-36) to include the upload binary:

```python
    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
        "//tools/semgrep:upload",
    ] + rules + srcs
```

And add the env var after the existing env setup (after line 24):

```python
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"
```

**Step 2: Add upload to `semgrep_manifest_test` data and env**

In `semgrep_manifest_test`, change the `data` list (line 95-100) to include the upload binary:

```python
    data = [
        "//tools/semgrep",
        "//tools/semgrep:pysemgrep",
        "//tools/semgrep:upload",
        "@multitool//tools/helm",
        chart_files,
    ] + rules + values_files
```

And add the env var after the existing env setup (after line 89):

```python
    env["UPLOAD_SCRIPT"] = "$(rootpath //tools/semgrep:upload)"
```

**Step 3: Verify rules load**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel query //semgrep_rules:python_rules_test`
Expected: `//semgrep_rules:python_rules_test`

**Step 4: Commit**

```bash
git add rules_semgrep/test.bzl
git commit -m "build(semgrep): wire upload script into test rules"
```

---

### Task 4: Modify semgrep-test.sh to call upload

**Files:**
- Modify: `rules_semgrep/semgrep-test.sh:9-11` (env docs)
- Modify: `rules_semgrep/semgrep-test.sh:99-108` (scan invocation)

**Step 1: Update the env documentation header**

Add `UPLOAD_SCRIPT` to the env docs at the top of the file (after line 11):

```bash
#      UPLOAD_SCRIPT          — path to upload binary; uploads results to Semgrep App
```

**Step 2: Replace the scan invocation block**

Replace lines 99-108 (the `else` branch of the test mode check) with:

```bash
else
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
		echo ""
		echo "FAILED: Semgrep found violations"
	fi
	exit "$SCAN_EXIT"
fi
```

**Step 3: Verify tests still pass without SEMGREP_APP_TOKEN**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //semgrep_rules:python_rules_test`
Expected: PASSED

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //:__init___semgrep_test`
Expected: PASSED (this uses the normal scan path, not test mode)

**Step 4: Commit**

```bash
git add rules_semgrep/semgrep-test.sh
git commit -m "feat(semgrep): add best-effort upload to source scan wrapper"
```

---

### Task 5: Modify semgrep-manifest-test.sh to call upload

**Files:**
- Modify: `rules_semgrep/semgrep-manifest-test.sh:9-10` (env docs)
- Modify: `rules_semgrep/semgrep-manifest-test.sh:100-107` (scan invocation)

**Step 1: Update the env documentation header**

Add `UPLOAD_SCRIPT` to the env docs (after line 10):

```bash
#      UPLOAD_SCRIPT          — path to upload binary; uploads results to Semgrep App
```

**Step 2: Replace the scan invocation block**

Replace lines 100-107 with:

```bash
SCAN_EXIT=0
"$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore \
	--json --output "$TEST_TMPDIR/results.json" \
	"$MANIFESTS" || SCAN_EXIT=$?

# Best-effort upload (never affects exit code)
if [[ -n "${SEMGREP_APP_TOKEN:-}" && -n "${UPLOAD_SCRIPT:-}" ]]; then
	"$UPLOAD_SCRIPT" "$TEST_TMPDIR/results.json" "$SCAN_EXIT" 2>&1 || true
fi

if [[ "$SCAN_EXIT" -eq 0 ]]; then
	echo "PASSED: No semgrep findings in rendered manifests"
else
	echo ""
	echo "FAILED: Semgrep found violations in rendered manifests"
fi
exit "$SCAN_EXIT"
```

**Step 3: Verify a manifest test still passes**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test $(bazel query 'attr(tags, semgrep, //overlays/...)' 2>/dev/null | head -1)`
Expected: PASSED (picks the first manifest semgrep test)

**Step 4: Commit**

```bash
git add rules_semgrep/semgrep-manifest-test.sh
git commit -m "feat(semgrep): add best-effort upload to manifest scan wrapper"
```

---

### Task 6: Run full test suite and verify

**Files:** None (verification only)

**Step 1: Run all semgrep tests**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //... --test_tag_filters=semgrep`
Expected: All tests pass. No upload attempts (SEMGREP_APP_TOKEN not set).

**Step 2: Run full test suite**

Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //... --test_tag_filters=-external`
Expected: All tests pass, no regressions.

**Step 3: Verify caching works**

Run the same test twice:
Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //:__init___semgrep_test`
Run: `cd /tmp/claude-worktrees/semgrep-app-upload && bazel test //:__init___semgrep_test`
Expected: Second run shows `(cached)` in output.
