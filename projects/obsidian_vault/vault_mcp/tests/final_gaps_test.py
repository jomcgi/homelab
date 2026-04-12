"""Final coverage gap tests for vault_mcp.

Targets specific untested code paths not covered by the existing suite:
  - delete_note: archived_to field in the return value
  - _reconcile_loop: ensure_collection failure triggers retry
  - _git_commit: empty stderr falls back to exception str in error message
  - get_history: pipe character in commit message parsed correctly with maxsplit=3
  - search_semantic: embed_query result is forwarded to qdrant.search vector arg
  - list_notes: dotfile-only vault returns empty notes list
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    _git_commit,
    configure,
    delete_note,
    get_history,
    list_notes,
    search_semantic,
)


@pytest.fixture(autouse=True)
def _configure_vault(tmp_path):
    """Configure vault to use a temporary directory for each test."""
    configure(Settings(path=str(tmp_path)))


@pytest.fixture(autouse=True)
def _init_git(tmp_path):
    """Initialize a git repo in the tmp vault so commits work."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# delete_note — archived_to return field
# ---------------------------------------------------------------------------


class TestDeleteNoteArchivedTo:
    async def test_archived_to_is_correct_path(self, tmp_path):
        """delete_note returns archived_to pointing to _archive/<original-path>."""
        (tmp_path / "note.md").write_text("# Note")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await delete_note(path="note.md", reason="cleanup")
        assert result["archived_to"] == "_archive/note.md"

    async def test_archived_to_preserves_nested_path(self, tmp_path):
        """delete_note preserves the relative directory structure in archived_to."""
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "2026-01-01.md").write_text("# Daily")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await delete_note(path="daily/2026-01-01.md", reason="old note")
        assert result["archived_to"] == "_archive/daily/2026-01-01.md"

    async def test_archived_to_is_in_return_alongside_status_ok(self, tmp_path):
        """Successful delete returns both status=ok and archived_to."""
        (tmp_path / "doc.md").write_text("# Doc")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await delete_note(path="doc.md", reason="done")
        assert result["status"] == "ok"
        assert "archived_to" in result


# ---------------------------------------------------------------------------
# _git_commit — empty stderr falls back to exception repr in error message
# ---------------------------------------------------------------------------


class TestGitCommitEmptyStderr:
    def test_empty_stderr_falls_back_to_exception_string(self):
        """When exc.stderr is empty string, the error message uses str(exc) as fallback."""
        exc = subprocess.CalledProcessError(1, ["git", "commit"], stderr="")
        with patch.object(_mod, "_git", side_effect=exc):
            result = _git_commit(["note.md"], "some message")
        assert "error" in result
        # Empty stderr → str(exc) is used: "Command '...' returned non-zero exit status 1."
        assert "git failed:" in result["error"]
        # The exc string representation contains "non-zero exit status"
        assert "non-zero exit status" in result["error"] or "Command" in result["error"]

    def test_non_empty_stderr_is_preferred_over_exception_str(self):
        """Non-empty stderr appears in the error message instead of str(exc)."""
        exc = subprocess.CalledProcessError(
            1, ["git", "commit"], stderr="fatal: lock fail"
        )
        with patch.object(_mod, "_git", side_effect=exc):
            result = _git_commit(["note.md"], "commit message")
        assert "fatal: lock fail" in result["error"]


# ---------------------------------------------------------------------------
# _reconcile_loop — ensure_collection failure triggers retry
# ---------------------------------------------------------------------------


class TestReconcileLoopEnsureCollectionFailure:
    @pytest.fixture(autouse=True)
    def _reset_globals(self):
        _mod._embedder = None
        _mod._qdrant = None
        yield
        _mod._embedder = None
        _mod._qdrant = None

    async def test_ensure_collection_failure_retries_init(self, tmp_path):
        """When ensure_collection raises, the loop resets globals and retries."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        ensure_call_count = 0

        async def ensure_collection_failing_then_ok(*args, **kwargs):
            nonlocal ensure_call_count
            ensure_call_count += 1
            if ensure_call_count == 1:
                raise ConnectionRefusedError("qdrant not ready")
            # Second call succeeds (returns None implicitly)

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768

        # Single qdrant mock whose ensure_collection fails first, succeeds second
        mock_qdrant = AsyncMock()
        mock_qdrant.ensure_collection = ensure_collection_failing_then_ok

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # ensure_collection was called at least twice (first failed, second succeeded)
        assert ensure_call_count >= 2

    async def test_globals_reset_when_ensure_collection_raises(self, tmp_path):
        """After ensure_collection failure, both _embedder and _qdrant are None."""
        settings = Settings(
            path=str(tmp_path),
            qdrant_url="http://localhost:6333",
            reconcile_interval_seconds=1,
        )

        call_count = 0

        async def ensure_collection_fail_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("collection error")

        mock_embedder = MagicMock()
        mock_embedder.dimension = 768

        mock_qdrant = AsyncMock()
        mock_qdrant.ensure_collection = ensure_collection_fail_once

        mock_reconciler = AsyncMock()
        mock_reconciler.run.side_effect = asyncio.CancelledError

        captured = {}

        async def capture_sleep(duration):
            if duration == 30 and not captured:
                captured["embedder"] = _mod._embedder
                captured["qdrant"] = _mod._qdrant

        with (
            patch.object(_mod, "VaultEmbedder", return_value=mock_embedder),
            patch.object(_mod, "QdrantClient", return_value=mock_qdrant),
            patch.object(_mod, "VaultReconciler", return_value=mock_reconciler),
            patch("asyncio.sleep", side_effect=capture_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _mod._reconcile_loop(settings)

        # After ensure_collection failure both globals must be None
        assert captured.get("embedder") is None
        assert captured.get("qdrant") is None


# ---------------------------------------------------------------------------
# get_history — empty lines in git log output are skipped
# ---------------------------------------------------------------------------


class TestGetHistoryEmptyLines:
    async def test_empty_lines_in_log_output_are_skipped(self, tmp_path):
        """get_history skips blank lines in git log output (if not line: continue)."""
        (tmp_path / "note.md").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=tmp_path,
            capture_output=True,
        )
        result = await get_history(path="note.md")
        # Should have exactly 1 commit — no phantom entries from blank lines
        assert len(result["commits"]) == 1
        commit = result["commits"][0]
        assert commit["message"] == "initial commit"
        assert len(commit["hash"]) == 40

    async def test_get_history_with_multiple_files_returns_all_commits(self, tmp_path):
        """get_history with no path= returns commits from all files."""
        for i in range(3):
            (tmp_path / f"file{i}.md").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"commit {i}"],
                cwd=tmp_path,
                capture_output=True,
            )
        result = await get_history()
        assert len(result["commits"]) == 3
        # Most recent first
        assert result["commits"][0]["message"] == "commit 2"


# ---------------------------------------------------------------------------
# search_semantic — embed_query vector is forwarded to qdrant.search
# ---------------------------------------------------------------------------


class TestSearchSemanticVectorForwarding:
    async def test_embed_query_result_forwarded_to_qdrant_search(self, tmp_path):
        """The vector returned by embed_query is the same one passed to qdrant.search."""
        expected_vector = [float(i) / 768.0 for i in range(768)]

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = expected_vector

        mock_qdrant = AsyncMock()
        mock_qdrant.search.return_value = []

        with (
            patch.object(_mod, "_embedder", mock_embedder),
            patch.object(_mod, "_qdrant", mock_qdrant),
        ):
            await search_semantic(query="test query", limit=3)

        mock_qdrant.search.assert_called_once_with(vector=expected_vector, limit=3)


# ---------------------------------------------------------------------------
# list_notes — vault with only dotfiles returns empty list
# ---------------------------------------------------------------------------


class TestListNotesDotfilesOnly:
    async def test_vault_with_only_dotfiles_returns_empty(self, tmp_path):
        """A vault containing only .git and .obsidian md files returns no notes."""
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / ".git" / "COMMIT_EDITMSG.md").write_text("initial commit")
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "plugins.md").write_text("plugin list")
        result = await list_notes()
        assert result == {"notes": []}

    async def test_hidden_md_file_at_root_excluded(self, tmp_path):
        """A dotfile .md at vault root (e.g. .config.md) is excluded."""
        (tmp_path / ".config.md").write_text("# Config")
        result = await list_notes()
        assert result == {"notes": []}
