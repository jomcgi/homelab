"""Tests for Obsidian Vault MCP server tools."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import projects.obsidian_vault.vault_mcp.app.main as _mod
from projects.obsidian_vault.vault_mcp.app.main import (
    Settings,
    configure,
    list_notes,
    read_note,
    search_notes,
)


@pytest.fixture(autouse=True)
def _configure_vault(tmp_path):
    """Configure vault to use a temporary directory for each test."""
    configure(Settings(path=str(tmp_path)))


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
        (tmp_path / ".git").mkdir()
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
