"""Tests for Obsidian Vault MCP server tools."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    _git_commit,
    _validate_path,
    configure,
    delete_note,
    edit_note,
    get_history,
    list_notes,
    read_note,
    restore_note,
    search_notes,
    write_note,
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


class TestSettings:
    def test_default_path(self):
        s = Settings()
        assert s.path == "/vault"

    def test_default_port(self):
        s = Settings()
        assert s.port == 8000

    def test_custom_values(self):
        s = Settings(path="/my/vault", port=9090)
        assert s.path == "/my/vault"
        assert s.port == 9090

    def test_env_prefix(self):
        assert Settings.model_config["env_prefix"] == "VAULT_"

    def test_path_from_env_var(self, monkeypatch):
        monkeypatch.setenv("VAULT_PATH", "/from-env")
        monkeypatch.delenv("VAULT_PORT", raising=False)
        s = Settings()
        assert s.path == "/from-env"


class TestListNotes:
    async def test_lists_markdown_files(self, tmp_path):
        (tmp_path / "note1.md").write_text("# Note 1")
        (tmp_path / "note2.md").write_text("# Note 2")
        (tmp_path / "not-a-note.txt").write_text("ignored")
        result = await list_notes()
        assert sorted(result["notes"]) == ["note1.md", "note2.md"]

    async def test_lists_nested_files(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "2026-03-21.md").write_text("# Today")
        (tmp_path / "root.md").write_text("# Root")
        result = await list_notes()
        assert sorted(result["notes"]) == ["daily/2026-03-21.md", "root.md"]

    async def test_filter_by_folder(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "today.md").write_text("# Today")
        (tmp_path / "projects").mkdir()
        (tmp_path / "projects" / "homelab.md").write_text("# Homelab")
        result = await list_notes(folder="daily")
        assert result["notes"] == ["daily/today.md"]

    async def test_filter_by_pattern(self, tmp_path):
        (tmp_path / "note-a.md").write_text("a")
        (tmp_path / "note-b.md").write_text("b")
        (tmp_path / "other.md").write_text("c")
        result = await list_notes(pattern="note-*")
        assert sorted(result["notes"]) == ["note-a.md", "note-b.md"]

    async def test_empty_vault(self, tmp_path):
        result = await list_notes()
        assert result["notes"] == []

    async def test_ignores_dotfiles_and_git(self, tmp_path):
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / ".git" / "config.md").write_text("git stuff")
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "config.md").write_text("obsidian config")
        (tmp_path / "real.md").write_text("# Real note")
        result = await list_notes()
        assert result["notes"] == ["real.md"]


class TestReadNote:
    async def test_reads_content(self, tmp_path):
        (tmp_path / "hello.md").write_text("# Hello\n\nWorld")
        result = await read_note(path="hello.md")
        assert result["content"] == "# Hello\n\nWorld"
        assert result["path"] == "hello.md"

    async def test_reads_nested_note(self, tmp_path):
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "today.md").write_text("# Today")
        result = await read_note(path="daily/today.md")
        assert result["content"] == "# Today"

    async def test_not_found(self, tmp_path):
        result = await read_note(path="missing.md")
        assert "error" in result

    async def test_rejects_path_traversal(self, tmp_path):
        result = await read_note(path="../../../etc/passwd")
        assert "error" in result

    async def test_rejects_absolute_path(self, tmp_path):
        result = await read_note(path="/etc/passwd")
        assert "error" in result


class TestSearchNotes:
    async def test_finds_matching_content(self, tmp_path):
        (tmp_path / "a.md").write_text("# Homelab\n\nKubernetes cluster")
        (tmp_path / "b.md").write_text("# Recipes\n\nChocolate cake")
        result = await search_notes(query="kubernetes")
        assert len(result["matches"]) == 1
        assert result["matches"][0]["path"] == "a.md"

    async def test_case_insensitive(self, tmp_path):
        (tmp_path / "a.md").write_text("KUBERNETES is great")
        result = await search_notes(query="kubernetes")
        assert len(result["matches"]) == 1

    async def test_no_matches(self, tmp_path):
        (tmp_path / "a.md").write_text("# Nothing relevant")
        result = await search_notes(query="zyxwvu")
        assert result["matches"] == []

    async def test_returns_matching_lines(self, tmp_path):
        (tmp_path / "a.md").write_text("line1\nfound here\nline3")
        result = await search_notes(query="found")
        assert "found here" in result["matches"][0]["lines"][0]

    async def test_ignores_dotfiles(self, tmp_path):
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "config.md").write_text("query match")
        (tmp_path / "real.md").write_text("query match")
        result = await search_notes(query="query match")
        assert len(result["matches"]) == 1
        assert result["matches"][0]["path"] == "real.md"


class TestWriteNote:
    async def test_creates_new_note(self, tmp_path):
        result = await write_note(
            path="new.md", content="# New Note", reason="created for testing"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "new.md").read_text() == "# New Note"

    async def test_creates_parent_dirs(self, tmp_path):
        result = await write_note(
            path="daily/2026-03-21.md", content="# Today", reason="daily note"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "daily" / "2026-03-21.md").exists()

    async def test_overwrites_existing(self, tmp_path):
        (tmp_path / "existing.md").write_text("old content")
        subprocess.run(["git", "add", "existing.md"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True
        )
        result = await write_note(
            path="existing.md", content="new content", reason="updated"
        )
        assert result["status"] == "ok"
        assert (tmp_path / "existing.md").read_text() == "new content"

    async def test_commits_with_reason(self, tmp_path):
        await write_note(path="a.md", content="# A", reason="test reason")
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "mcp(write_note)" in log.stdout
        assert "test reason" in log.stdout

    async def test_rejects_path_traversal(self, tmp_path):
        result = await write_note(path="../escape.md", content="bad", reason="nope")
        assert "error" in result

    async def test_reason_required(self, tmp_path):
        """Reason is a required parameter — empty string is rejected."""
        result = await write_note(path="a.md", content="# A", reason="")
        assert "error" in result


class TestEditNote:
    async def test_replaces_section(self, tmp_path):
        (tmp_path / "note.md").write_text("# Title\n\nOld paragraph\n\n## End")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await edit_note(
            path="note.md",
            old_text="Old paragraph",
            new_text="New paragraph",
            reason="updated paragraph",
        )
        assert result["status"] == "ok"
        assert "New paragraph" in (tmp_path / "note.md").read_text()
        assert "Old paragraph" not in (tmp_path / "note.md").read_text()

    async def test_old_text_not_found(self, tmp_path):
        (tmp_path / "note.md").write_text("# Title\n\nContent")
        result = await edit_note(
            path="note.md",
            old_text="nonexistent text",
            new_text="replacement",
            reason="fix",
        )
        assert "error" in result

    async def test_note_not_found(self, tmp_path):
        result = await edit_note(
            path="missing.md",
            old_text="a",
            new_text="b",
            reason="fix",
        )
        assert "error" in result

    async def test_commits_with_reason(self, tmp_path):
        (tmp_path / "note.md").write_text("# Old")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        await edit_note(
            path="note.md", old_text="# Old", new_text="# New", reason="rename"
        )
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "mcp(edit_note)" in log.stdout
        assert "rename" in log.stdout


class TestDeleteNote:
    async def test_moves_to_archive(self, tmp_path):
        (tmp_path / "doomed.md").write_text("# Doomed")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await delete_note(path="doomed.md", reason="no longer needed")
        assert result["status"] == "ok"
        assert not (tmp_path / "doomed.md").exists()
        assert (tmp_path / "_archive" / "doomed.md").exists()
        assert (tmp_path / "_archive" / "doomed.md").read_text() == "# Doomed"

    async def test_preserves_nested_path_in_archive(self, tmp_path):
        (tmp_path / "projects").mkdir()
        (tmp_path / "projects" / "old.md").write_text("# Old")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        await delete_note(path="projects/old.md", reason="archived")
        assert (tmp_path / "_archive" / "projects" / "old.md").exists()

    async def test_not_found(self, tmp_path):
        result = await delete_note(path="missing.md", reason="cleanup")
        assert "error" in result

    async def test_commits_with_reason(self, tmp_path):
        (tmp_path / "note.md").write_text("# Note")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        await delete_note(path="note.md", reason="test delete")
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "mcp(delete_note)" in log.stdout
        assert "test delete" in log.stdout


class TestGetHistory:
    async def test_returns_commits_for_file(self, tmp_path):
        (tmp_path / "note.md").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "first"], cwd=tmp_path, capture_output=True
        )
        (tmp_path / "note.md").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "second"], cwd=tmp_path, capture_output=True
        )
        result = await get_history(path="note.md")
        assert len(result["commits"]) == 2
        assert "second" in result["commits"][0]["message"]

    async def test_returns_all_commits_when_no_path(self, tmp_path):
        (tmp_path / "a.md").write_text("a")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add a"], cwd=tmp_path, capture_output=True
        )
        (tmp_path / "b.md").write_text("b")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True
        )
        result = await get_history()
        assert len(result["commits"]) == 2

    async def test_limit_parameter(self, tmp_path):
        for i in range(5):
            (tmp_path / f"note{i}.md").write_text(f"v{i}")
            subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"commit {i}"],
                cwd=tmp_path,
                capture_output=True,
            )
        result = await get_history(limit=3)
        assert len(result["commits"]) == 3


class TestRestoreNote:
    async def test_restores_from_commit(self, tmp_path):
        (tmp_path / "note.md").write_text("original")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=tmp_path, capture_output=True)
        v1_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (tmp_path / "note.md").write_text("modified")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=tmp_path, capture_output=True)
        result = await restore_note(path="note.md", commit=v1_hash)
        assert result["status"] == "ok"
        assert (tmp_path / "note.md").read_text() == "original"

    async def test_invalid_commit(self, tmp_path):
        (tmp_path / "note.md").write_text("content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await restore_note(path="note.md", commit="0000000000")
        assert "error" in result

    async def test_rejects_path_traversal(self, tmp_path):
        result = await restore_note(path="../escape.md", commit="abc123")
        assert "error" in result

    async def test_rejects_absolute_path(self, tmp_path):
        result = await restore_note(path="/etc/passwd", commit="abc123")
        assert "error" in result


class TestEditNoteValidation:
    async def test_reason_required(self, tmp_path):
        """Empty reason is rejected before any path or content checks."""
        (tmp_path / "note.md").write_text("# Title")
        result = await edit_note(
            path="note.md", old_text="# Title", new_text="# New", reason=""
        )
        assert "error" in result

    async def test_rejects_path_traversal(self, tmp_path):
        result = await edit_note(
            path="../escape.md", old_text="a", new_text="b", reason="fix"
        )
        assert "error" in result


class TestDeleteNoteValidation:
    async def test_reason_required(self, tmp_path):
        """Empty reason is rejected before any file operations."""
        (tmp_path / "note.md").write_text("# Doomed")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True
        )
        result = await delete_note(path="note.md", reason="")
        assert "error" in result

    async def test_rejects_path_traversal(self, tmp_path):
        result = await delete_note(path="../escape.md", reason="cleanup")
        assert "error" in result


class TestListNotesNonexistentFolder:
    async def test_nonexistent_folder_returns_empty(self, tmp_path):
        """A folder= that doesn't exist should return an empty notes list."""
        result = await list_notes(folder="nonexistent")
        assert result == {"notes": []}


class TestGetHistoryCalledProcessError:
    async def test_returns_empty_commits_on_git_failure(self, tmp_path):
        """The CalledProcessError branch returns {'commits': []} instead of raising."""
        with patch.object(
            _mod, "_git", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            result = await get_history(path="some/path.md")
        assert result == {"commits": []}

    async def test_returns_empty_commits_on_git_failure_no_path(self, tmp_path):
        """CalledProcessError for whole-vault history also returns {'commits': []}."""
        with patch.object(
            _mod, "_git", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            result = await get_history()
        assert result == {"commits": []}


class TestValidatePathSymlinkEscape:
    def test_symlink_pointing_outside_vault_is_rejected(
        self, tmp_path, tmp_path_factory
    ):
        """A symlink inside the vault that points outside it must be rejected."""
        outside = tmp_path_factory.mktemp("outside")
        (outside / "secret.md").write_text("secret")
        # Create a symlink inside the vault pointing to the outside dir
        link = tmp_path / "evil_link.md"
        link.symlink_to(outside / "secret.md")
        # After resolution the target is outside the vault — _validate_path must return None
        result = _validate_path("evil_link.md")
        assert result is None


class TestListNotesDualFilter:
    async def test_folder_and_pattern_combined(self, tmp_path):
        """Both folder= and pattern= must be satisfied simultaneously."""
        (tmp_path / "daily").mkdir()
        (tmp_path / "daily" / "note-2026-03-21.md").write_text("# Daily note")
        (tmp_path / "daily" / "summary.md").write_text("# Summary")
        (tmp_path / "projects").mkdir()
        (tmp_path / "projects" / "note-homelab.md").write_text("# Homelab")
        result = await list_notes(folder="daily", pattern="note-*")
        assert result["notes"] == ["daily/note-2026-03-21.md"]


class TestGitCommitMultiFile:
    def test_stages_all_files_in_list(self, tmp_path):
        """_git_commit must call git add for every file in the list, not just one."""
        with patch.object(_mod, "_git") as mock_git:
            _git_commit(["file-a.md", "file-b.md", "file-c.md"], "multi-file commit")

        add_calls = [c for c in mock_git.call_args_list if c.args[0] == "add"]
        staged_files = [c.args[1] for c in add_calls]
        assert staged_files == ["file-a.md", "file-b.md", "file-c.md"]
        commit_calls = [c for c in mock_git.call_args_list if c.args[0] == "commit"]
        assert len(commit_calls) == 1


class TestMain:
    def test_main_wires_settings_configure_and_uvicorn(self):
        """main() should instantiate Settings, call configure(), build http_app, and run uvicorn."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.path = "/tmp/test-vault"
        mock_settings.port = 8000
        mock_app = MagicMock()

        with (
            patch.object(
                _mod, "Settings", return_value=mock_settings
            ) as mock_settings_cls,
            patch.object(_mod, "configure") as mock_configure,
            patch.object(_mod.mcp, "http_app", return_value=mock_app),
            patch("uvicorn.run") as mock_uvicorn_run,
        ):
            _mod.main()

        mock_settings_cls.assert_called_once_with()
        mock_configure.assert_called_once_with(mock_settings)
        mock_app.add_route.assert_called_once()
        assert mock_app.add_route.call_args[0][0] == "/healthz"
        mock_uvicorn_run.assert_called_once_with(
            mock_app, host="0.0.0.0", port=mock_settings.port
        )
