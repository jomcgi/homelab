"""Tests for vault reconciler."""

from __future__ import annotations

import hashlib
import re
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

    def test_hash_values_are_sha256_hex(self, vault_dir, mock_qdrant, mock_embedder):
        """_walk_vault produces 64-character lowercase hex SHA-256 digests."""
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
        for source_url, content_hash in files.items():
            assert sha256_pattern.match(content_hash), (
                f"Hash for {source_url!r} is not a 64-char hex string: {content_hash!r}"
            )

    def test_source_urls_use_vault_scheme(self, vault_dir, mock_qdrant, mock_embedder):
        """All source URLs returned by _walk_vault use the vault:// scheme."""
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        for key in files:
            assert key.startswith("vault://"), f"Key {key!r} missing vault:// prefix"


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

    async def test_delete_called_before_upsert_for_changed_file(
        self, vault_dir, mock_qdrant, mock_embedder
    ):
        """For a changed file, delete must be called before upsert."""
        call_order: list[str] = []

        async def track_delete(*a, **kw):
            call_order.append("delete")

        async def track_upsert(*a, **kw):
            call_order.append("upsert")

        mock_qdrant.delete_by_source_url.side_effect = track_delete
        mock_qdrant.upsert_chunks.side_effect = track_upsert
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note1.md": "stale_hash",
        }
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert "delete" in call_order
        assert "upsert" in call_order
        assert call_order.index("delete") < call_order.index("upsert")

    async def test_run_handles_mixed_new_changed_deleted(
        self, vault_dir, mock_qdrant, mock_embedder
    ):
        """run() processes new, changed, and deleted files in one cycle."""
        note1_hash = _hash((vault_dir / "note1.md").read_text())
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note1.md": note1_hash,  # unchanged
            "vault://note2.md": "stale_hash",  # changed
            "vault://ghost.md": "old_hash",  # deleted (not on disk)
        }
        reconciler = VaultReconciler(
            vault_path=str(vault_dir), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        # note2 changed → delete + upsert; ghost deleted → delete only; note1 unchanged
        assert mock_qdrant.delete_by_source_url.call_count == 2
        assert mock_qdrant.upsert_chunks.call_count == 1
