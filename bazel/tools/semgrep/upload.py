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
import logging
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
    """Return the semgrep engine version from the environment or a fallback.

    The SEMGREP_ENGINE_VERSION env var is set by the test runner from the actual
    semgrep-core binary's -version output. Falls back to a static version if
    the env var is not set (e.g., when invoked outside the test runner).
    """
    import os

    return os.environ.get("SEMGREP_ENGINE_VERSION", "1.153.1")


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
        logging.warning("upload.py: failed to read results: %s", e)
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

            print(
                f"upload.py: uploaded to {base_url} (scan {scan_id})", file=sys.stderr
            )

    except Exception as e:
        logging.warning("upload.py: upload failed (non-fatal): %s", e)
        print(f"upload.py: upload failed (non-fatal): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
