"""Tests for vault reconciler."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from projects.obsidian_vault.vault_mcp.app.reconciler import VaultReconciler


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


@pytest.fixture
def vault_dir(tmp_path):
    (tmp_path / "note1.md").write_text("# Note 1\n\nContent of note 1.")
    (tmp_path / "note2.md").write_text("# Note 2\n\nContent of note 2.")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "config.md").write_text("ignored")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ignored")
    return tmp_path


@pytest.fixture
def mock_qdrant():
    qdrant = AsyncMock()
    qdrant.get_indexed_sources.return_value = {}
    qdrant.ensure_collection = AsyncMock()
    qdrant.upsert_chunks = AsyncMock()
    qdrant.delete_by_source_url = AsyncMock()
    return qdrant


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.dimension = 768
    embedder.embed.return_value = [[0.1] * 768]
    return embedder


class TestWalkVault:
    def test_finds_markdown_files(self, vault_dir, mock_qdrant, mock_embedder):
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://note1.md" in files
        assert "vault://note2.md" in files

    def test_excludes_dotfile_dirs(self, vault_dir, mock_qdrant, mock_embedder):
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        source_urls = list(files.keys())
        assert not any(".obsidian" in u for u in source_urls)
        assert not any(".git" in u for u in source_urls)

    def test_includes_archive(self, vault_dir, mock_qdrant, mock_embedder):
        (vault_dir / "_archive").mkdir()
        (vault_dir / "_archive" / "old.md").write_text("# Archived")
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://_archive/old.md" in files


class TestReconcile:
    async def test_embeds_new_files(self, vault_dir, mock_qdrant, mock_embedder):
        mock_qdrant.get_indexed_sources.return_value = {}
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert mock_qdrant.upsert_chunks.call_count == 2
        assert mock_qdrant.delete_by_source_url.call_count == 0

    async def test_skips_unchanged_files(self, vault_dir, mock_qdrant, mock_embedder):
        content1 = (vault_dir / "note1.md").read_text()
        content2 = (vault_dir / "note2.md").read_text()
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note1.md": _hash(content1),
            "vault://note2.md": _hash(content2),
        }
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert mock_qdrant.upsert_chunks.call_count == 0
        assert mock_qdrant.delete_by_source_url.call_count == 0

    async def test_re_embeds_changed_files(self, vault_dir, mock_qdrant, mock_embedder):
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note1.md": "stale_hash",
            "vault://note2.md": _hash((vault_dir / "note2.md").read_text()),
        }
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        mock_qdrant.delete_by_source_url.assert_called_once_with("vault://note1.md")
        assert mock_qdrant.upsert_chunks.call_count == 1

    async def test_deletes_removed_files(self, vault_dir, mock_qdrant, mock_embedder):
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note1.md": _hash((vault_dir / "note1.md").read_text()),
            "vault://note2.md": _hash((vault_dir / "note2.md").read_text()),
            "vault://deleted.md": "some_hash",
        }
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        mock_qdrant.delete_by_source_url.assert_called_once_with("vault://deleted.md")
        assert mock_qdrant.upsert_chunks.call_count == 0

    async def test_empty_vault(self, tmp_path, mock_qdrant, mock_embedder):
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert mock_qdrant.upsert_chunks.call_count == 0
