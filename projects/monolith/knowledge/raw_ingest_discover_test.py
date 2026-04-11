"""Direct unit tests for raw_ingest._discover_vault_root_drops().

_discover_vault_root_drops() walks the vault root and returns a sorted list
of .md file Paths that live outside managed directories (_raw, _processed,
.obsidian, .trash).  All tests use pytest's tmp_path fixture for filesystem
isolation — no database is needed.

Coverage:
- discovers .md files at the vault root (top-level)
- discovers .md files in user-created subdirectories
- ignores non-.md files (at root and in subdirs)
- ignores files inside excluded top-level directories (_raw, _processed,
  .obsidian, .trash)
- ignores top-level dotfiles (files/dirs whose names start with '.')
- ignores .md files that live within a dotfile directory inside a subdir
- returns an empty list when the vault root does not exist
- returns an empty list when the vault root exists but has no .md drops
- result is always sorted
"""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.raw_ingest import _discover_vault_root_drops


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write(path: Path, content: str = "# test") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Vault root does not exist / is empty
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsNonExistent:
    def test_returns_empty_list_when_vault_root_does_not_exist(self, tmp_path):
        """Non-existent vault root returns [] without raising."""
        result = _discover_vault_root_drops(tmp_path / "no-such-dir")
        assert result == []

    def test_returns_empty_list_when_vault_root_is_empty(self, tmp_path):
        """An empty but existing vault root returns []."""
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_returns_empty_list_when_no_md_files_present(self, tmp_path):
        """Only non-.md files present → still returns []."""
        _write(tmp_path / "readme.txt", "text file")
        _write(tmp_path / "image.png", "binary")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Discovers .md files
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsFindsMarkdown:
    def test_discovers_md_file_at_vault_root(self, tmp_path):
        """A .md file directly inside vault_root is discovered."""
        _write(tmp_path / "note.md", "---\ntitle: Note\n---\nBody.")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 1
        assert result[0].name == "note.md"

    def test_discovers_multiple_md_files_at_vault_root(self, tmp_path):
        _write(tmp_path / "a.md", "A")
        _write(tmp_path / "b.md", "B")
        _write(tmp_path / "c.md", "C")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 3

    def test_discovers_md_file_in_user_subdirectory(self, tmp_path):
        """A .md file inside a user-created subdirectory is discovered."""
        _write(tmp_path / "inbox" / "idea.md", "---\ntitle: Idea\n---\nContent.")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 1
        assert result[0].name == "idea.md"

    def test_discovers_md_files_in_nested_subdirectory(self, tmp_path):
        """Deeply nested .md files inside user dirs are discovered."""
        _write(tmp_path / "projects" / "alpha" / "plan.md", "plan")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 1
        assert result[0].name == "plan.md"

    def test_discovers_md_files_across_multiple_subdirs(self, tmp_path):
        _write(tmp_path / "inbox" / "note1.md", "1")
        _write(tmp_path / "drafts" / "note2.md", "2")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Ignores non-.md files
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsIgnoresNonMarkdown:
    def test_ignores_txt_file_at_vault_root(self, tmp_path):
        _write(tmp_path / "notes.txt")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_png_file_at_vault_root(self, tmp_path):
        _write(tmp_path / "image.png")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_non_md_files_in_subdirectory(self, tmp_path):
        _write(tmp_path / "inbox" / "attachment.pdf")
        _write(tmp_path / "inbox" / "note.md", "content")
        result = _discover_vault_root_drops(tmp_path)
        # Only the .md file should be returned
        assert len(result) == 1
        assert result[0].name == "note.md"

    def test_ignores_file_with_md_in_name_but_wrong_extension(self, tmp_path):
        """A file named 'notes.md.bak' is not .md and must be ignored."""
        _write(tmp_path / "notes.md.bak")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Ignores excluded top-level directories
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsExcludesManaged:
    def test_ignores_raw_directory(self, tmp_path):
        """Files under _raw/ are already managed and must not be re-discovered."""
        _write(tmp_path / "_raw" / "2026" / "04" / "09" / "abc-note.md", "raw")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_processed_directory(self, tmp_path):
        """Files under _processed/ must not be re-discovered."""
        _write(tmp_path / "_processed" / "atoms" / "atom.md", "atom")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_obsidian_directory(self, tmp_path):
        """The .obsidian config directory must be excluded."""
        _write(tmp_path / ".obsidian" / "config.md", "obsidian config")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_trash_directory(self, tmp_path):
        """The .trash directory must be excluded."""
        _write(tmp_path / ".trash" / "deleted.md", "deleted")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_discovers_user_dirs_alongside_excluded_dirs(self, tmp_path):
        """Non-excluded dirs alongside managed dirs are still crawled."""
        _write(tmp_path / "_raw" / "2026" / "04" / "09" / "old.md", "raw")
        _write(tmp_path / "inbox" / "new.md", "new content")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 1
        assert result[0].name == "new.md"


# ---------------------------------------------------------------------------
# Ignores dotfiles
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsIgnoresDotfiles:
    def test_ignores_dotfile_at_vault_root(self, tmp_path):
        """.hidden.md at vault root is a dotfile and must be skipped."""
        _write(tmp_path / ".hidden.md", "secret")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_dot_directory_at_vault_root(self, tmp_path):
        """A directory whose name starts with '.' is skipped entirely."""
        _write(tmp_path / ".obsidian" / "template.md", "template")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_md_inside_hidden_subdir_within_user_dir(self, tmp_path):
        """inbox/.hidden/note.md has a dotfile component and must be skipped."""
        _write(tmp_path / "inbox" / ".hidden" / "note.md", "hidden note")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_ignores_dotfile_md_in_subdirectory(self, tmp_path):
        """inbox/.hidden.md has a dotfile name component and must be skipped."""
        _write(tmp_path / "inbox" / ".hidden.md", "hidden")
        result = _discover_vault_root_drops(tmp_path)
        assert result == []

    def test_visible_md_alongside_dotfile_is_returned(self, tmp_path):
        """Only the visible .md file is returned when a dotfile sits nearby."""
        _write(tmp_path / "inbox" / ".skip.md", "skip")
        _write(tmp_path / "inbox" / "keep.md", "keep")
        result = _discover_vault_root_drops(tmp_path)
        assert len(result) == 1
        assert result[0].name == "keep.md"


# ---------------------------------------------------------------------------
# Return order
# ---------------------------------------------------------------------------


class TestDiscoverVaultRootDropsSorted:
    def test_result_is_sorted(self, tmp_path):
        """_discover_vault_root_drops() returns paths in sorted order."""
        _write(tmp_path / "z-note.md", "z")
        _write(tmp_path / "a-note.md", "a")
        _write(tmp_path / "m-note.md", "m")
        result = _discover_vault_root_drops(tmp_path)
        assert result == sorted(result)

    def test_result_is_list(self, tmp_path):
        """Return type is a list (not a generator or other iterable)."""
        _write(tmp_path / "note.md", "content")
        result = _discover_vault_root_drops(tmp_path)
        assert isinstance(result, list)

    def test_result_contains_path_objects(self, tmp_path):
        """Each element is a pathlib.Path."""
        _write(tmp_path / "note.md", "content")
        result = _discover_vault_root_drops(tmp_path)
        assert all(isinstance(p, Path) for p in result)

    def test_paths_are_absolute(self, tmp_path):
        """Returned paths are absolute (not relative)."""
        _write(tmp_path / "note.md", "content")
        result = _discover_vault_root_drops(tmp_path)
        assert all(p.is_absolute() for p in result)
