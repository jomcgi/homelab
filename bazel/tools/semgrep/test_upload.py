"""Tests for the semgrep results upload script.

Covers _git, _detect_repo, _detect_commit, _detect_branch,
_detect_semgrep_version, and main() — including the 3-step HTTP flow.

All subprocess and HTTP calls are mocked; no real network or git
invocations occur during tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from bazel.tools.semgrep.upload import (
    _detect_branch,
    _detect_commit,
    _detect_repo,
    _detect_semgrep_version,
    _git,
    main,
)


# ---------------------------------------------------------------------------
# _git
# ---------------------------------------------------------------------------


class TestGit:
    def test_success_returns_stripped_stdout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="abc123\n")
            assert _git("rev-parse HEAD") == "abc123"

    def test_exception_returns_empty_string(self):
        with patch("subprocess.run", side_effect=Exception("git not found")):
            assert _git("rev-parse HEAD") == ""

    def test_timeout_returns_empty_string(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 5),
        ):
            assert _git("rev-parse HEAD") == ""

    def test_empty_stdout_returns_empty(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            assert _git("rev-parse HEAD") == ""

    def test_strips_trailing_whitespace(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="  main  \n")
            assert _git("rev-parse --abbrev-ref HEAD") == "main"

    def test_command_split_correctly(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            _git("remote get-url origin")
            args = mock_run.call_args[0][0]
            assert args[0] == "git"
            assert "remote" in args
            assert "get-url" in args
            assert "origin" in args


# ---------------------------------------------------------------------------
# _detect_repo
# ---------------------------------------------------------------------------


class TestDetectRepo:
    def test_env_var_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("SEMGREP_REPO", "myorg/myrepo")
        assert _detect_repo() == "myorg/myrepo"

    def test_ssh_remote_parsed(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_REPO", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "git@github.com:org/repo.git"
            assert _detect_repo() == "org/repo"

    def test_https_remote_parsed(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_REPO", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "https://github.com/org/repo.git"
            assert _detect_repo() == "org/repo"

    def test_no_remote_returns_unknown(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_REPO", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = ""
            assert _detect_repo() == "unknown/unknown"

    def test_ssh_git_suffix_stripped(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_REPO", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "git@github.com:org/myrepo.git"
            result = _detect_repo()
        assert result == "org/myrepo"

    def test_https_git_suffix_stripped(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_REPO", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "https://github.com/org/myrepo.git"
            result = _detect_repo()
        assert result == "org/myrepo"


# ---------------------------------------------------------------------------
# _detect_commit
# ---------------------------------------------------------------------------


class TestDetectCommit:
    def test_github_sha_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("GITHUB_SHA", "sha-abc123")
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        assert _detect_commit() == "sha-abc123"

    def test_git_commit_fallback(self, monkeypatch):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        monkeypatch.setenv("GIT_COMMIT", "commit-def456")
        assert _detect_commit() == "commit-def456"

    def test_git_command_fallback(self, monkeypatch):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "ghi789"
            assert _detect_commit() == "ghi789"

    def test_unknown_when_nothing_available(self, monkeypatch):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = ""
            assert _detect_commit() == "unknown"


# ---------------------------------------------------------------------------
# _detect_branch
# ---------------------------------------------------------------------------


class TestDetectBranch:
    def test_github_ref_name_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        assert _detect_branch() == "main"

    def test_git_branch_fallback(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
        monkeypatch.setenv("GIT_BRANCH", "feature/test")
        assert _detect_branch() == "feature/test"

    def test_git_command_fallback(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = "feat/my-feature"
            assert _detect_branch() == "feat/my-feature"

    def test_unknown_when_nothing_available(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        with patch("bazel.tools.semgrep.upload._git") as mock_git:
            mock_git.return_value = ""
            assert _detect_branch() == "unknown"


# ---------------------------------------------------------------------------
# _detect_semgrep_version
# ---------------------------------------------------------------------------


class TestDetectSemgrepVersion:
    def test_env_var_used(self, monkeypatch):
        monkeypatch.setenv("SEMGREP_ENGINE_VERSION", "2.0.0")
        assert _detect_semgrep_version() == "2.0.0"

    def test_default_fallback(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_ENGINE_VERSION", raising=False)
        # Default must be a non-empty version string
        result = _detect_semgrep_version()
        assert result
        assert "." in result  # Looks like a semver string


# ---------------------------------------------------------------------------
# main — happy path and error paths
# ---------------------------------------------------------------------------


def _make_mock_http_client(scan_id: str = "scan-42"):
    """Return a mock httpx.Client context manager with canned responses."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"info": {"id": scan_id}}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post = MagicMock(return_value=mock_response)
    return mock_client


class TestMain:
    def test_no_token_returns_silently(self, monkeypatch):
        monkeypatch.delenv("SEMGREP_APP_TOKEN", raising=False)
        # Should return without error or output
        main()

    def test_too_few_args_prints_error(self, monkeypatch, capsys):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        with patch.object(sys, "argv", ["upload.py"]):
            main()
        assert "expected" in capsys.readouterr().err

    def test_missing_results_file_prints_error(self, monkeypatch, capsys):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        with patch.object(sys, "argv", ["upload.py", "/nonexistent/file.json", "0"]):
            main()
        assert "failed to read" in capsys.readouterr().err

    def test_invalid_json_prints_error(self, monkeypatch, capsys):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{")
            path = f.name
        try:
            with patch.object(sys, "argv", ["upload.py", path, "0"]):
                main()
            assert "failed to read" in capsys.readouterr().err
        finally:
            os.unlink(path)

    def test_successful_upload_three_http_calls(self, monkeypatch, capsys):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "mytoken")
        monkeypatch.setenv("SEMGREP_APP_URL", "https://semgrep.example.com")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        monkeypatch.setenv("GITHUB_SHA", "abc123")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.setenv("SEMGREP_ENGINE_VERSION", "1.0.0")

        results = {"results": [], "errors": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(results, f)
            path = f.name

        try:
            mock_client = _make_mock_http_client("scan-42")
            with patch.object(sys, "argv", ["upload.py", path, "0"]):
                with patch("bazel.tools.semgrep.upload.httpx.Client", return_value=mock_client):
                    main()

            err = capsys.readouterr().err
            assert "scan-42" in err
            assert "https://semgrep.example.com" in err
            # Exactly 3 HTTP POST calls: register → findings → complete
            assert mock_client.post.call_count == 3
        finally:
            os.unlink(path)

    def test_successful_upload_posts_to_correct_endpoints(self, monkeypatch):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_APP_URL", "https://semgrep.example.com")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        monkeypatch.setenv("GITHUB_SHA", "abc")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.setenv("SEMGREP_ENGINE_VERSION", "1.0.0")

        results = {"results": [], "errors": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(results, f)
            path = f.name

        try:
            mock_client = _make_mock_http_client("s99")
            with patch.object(sys, "argv", ["upload.py", path, "0"]):
                with patch("bazel.tools.semgrep.upload.httpx.Client", return_value=mock_client):
                    main()

            urls = [c.args[0] for c in mock_client.post.call_args_list]
            assert any("/api/cli/scans" in u for u in urls)
            assert any("/api/agent/scans/s99/results" in u for u in urls)
            assert any("/api/agent/scans/s99/complete" in u for u in urls)
        finally:
            os.unlink(path)

    def test_complete_call_sends_exit_code(self, monkeypatch):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        monkeypatch.setenv("GITHUB_SHA", "abc")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.setenv("SEMGREP_ENGINE_VERSION", "1.0.0")

        results = {"results": [], "errors": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(results, f)
            path = f.name

        try:
            mock_client = _make_mock_http_client("scanX")
            with patch.object(sys, "argv", ["upload.py", path, "2"]):
                with patch("bazel.tools.semgrep.upload.httpx.Client", return_value=mock_client):
                    main()

            # Third call is the "complete" request
            complete_call = mock_client.post.call_args_list[2]
            assert complete_call.kwargs["json"]["exit_code"] == 2
        finally:
            os.unlink(path)

    def test_http_failure_is_nonfatal(self, monkeypatch, capsys):
        """Upload failures must never raise — always exits cleanly."""
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_REPO", "org/repo")
        monkeypatch.setenv("GITHUB_SHA", "abc")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")

        results = {"results": [], "errors": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(results, f)
            path = f.name

        try:
            with patch.object(sys, "argv", ["upload.py", path, "1"]):
                with patch(
                    "bazel.tools.semgrep.upload.httpx.Client",
                    side_effect=Exception("connection refused"),
                ):
                    main()  # Must not raise

            assert "non-fatal" in capsys.readouterr().err
        finally:
            os.unlink(path)

    def test_register_scan_includes_repo_metadata(self, monkeypatch):
        monkeypatch.setenv("SEMGREP_APP_TOKEN", "tok")
        monkeypatch.setenv("SEMGREP_REPO", "myorg/myrepo")
        monkeypatch.setenv("GITHUB_SHA", "deadbeef")
        monkeypatch.setenv("GITHUB_REF_NAME", "feat/branch")
        monkeypatch.setenv("SEMGREP_ENGINE_VERSION", "1.0.0")

        results = {"results": [], "errors": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(results, f)
            path = f.name

        try:
            mock_client = _make_mock_http_client("s1")
            with patch.object(sys, "argv", ["upload.py", path, "0"]):
                with patch("bazel.tools.semgrep.upload.httpx.Client", return_value=mock_client):
                    main()

            # First call is the register-scan POST
            register_call = mock_client.post.call_args_list[0]
            body = register_call.kwargs["json"]
            assert body["project_metadata"]["repository"] == "myorg/myrepo"
            assert body["project_metadata"]["commit"] == "deadbeef"
            assert body["project_metadata"]["branch"] == "feat/branch"
        finally:
            os.unlink(path)
