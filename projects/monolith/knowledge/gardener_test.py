"""Tests for the knowledge gardener."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from knowledge.gardener import Gardener, GardenStats


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


class TestDiscoverRawFiles:
    def test_finds_md_files_outside_processed_and_deleted(self, tmp_path):
        _write(tmp_path, "inbox/new-note.md", "---\ntitle: New\n---\nBody.")
        _write(tmp_path, "_processed/existing.md", "---\nid: e\ntitle: E\n---\nBody.")
        _write(
            tmp_path,
            "_deleted_with_ttl/old.md",
            "---\nttl: 2026-01-01T00:00:00Z\n---\nBody.",
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1
        assert raw[0].name == "new-note.md"

    def test_ignores_non_md_files(self, tmp_path):
        _write(tmp_path, "inbox/image.png", "not markdown")
        _write(tmp_path, "inbox/note.md", "---\ntitle: Note\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1

    def test_ignores_dotfiles_and_dot_directories(self, tmp_path):
        _write(tmp_path, ".obsidian/config.md", "config")
        _write(tmp_path, "inbox/.hidden.md", "hidden")
        _write(tmp_path, "inbox/visible.md", "---\ntitle: V\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        raw = gardener._discover_raw_files()
        assert len(raw) == 1


class TestTtlCleanup:
    def test_deletes_expired_files(self, tmp_path):
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/old.md", f'---\nttl: "{expired}"\n---\nBody.'
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 1
        assert not (tmp_path / "_deleted_with_ttl" / "old.md").exists()

    def test_keeps_non_expired_files(self, tmp_path):
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        _write(
            tmp_path, "_deleted_with_ttl/recent.md", f'---\nttl: "{future}"\n---\nBody.'
        )
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
        assert (tmp_path / "_deleted_with_ttl" / "recent.md").exists()

    def test_handles_missing_ttl_frontmatter(self, tmp_path):
        _write(tmp_path, "_deleted_with_ttl/no-ttl.md", "---\ntitle: Oops\n---\nBody.")
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        # No ttl = don't delete (conservative)
        assert cleaned == 0

    def test_handles_empty_deleted_dir(self, tmp_path):
        gardener = Gardener(
            vault_root=tmp_path, anthropic_client=None, store=None, embed_client=None
        )
        cleaned = gardener._cleanup_ttl()
        assert cleaned == 0
