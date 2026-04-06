"""Tests for reconciler race condition — file deleted between walk and embed."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.obsidian_vault.vault_mcp.app.reconciler import VaultReconciler


@pytest.fixture
def mock_qdrant():
    q = AsyncMock()
    q.get_indexed_sources.return_value = {}
    q.upsert_chunks = AsyncMock()
    q.delete_by_source_url = AsyncMock()
    return q


@pytest.fixture
def mock_embedder():
    e = MagicMock()
    e.embed.return_value = [[0.1] * 768]
    return e


class TestReconcilerFileNotFoundRace:
    """Tests for the race condition where a file disappears between walk and embed."""

    async def test_file_deleted_after_walk_raises_file_not_found(
        self, tmp_path: Path, mock_qdrant, mock_embedder
    ):
        """Simulates a file that is found during _walk_vault but deleted before
        the embed loop reads it. The reconciler should propagate FileNotFoundError."""
        # Patch _walk_vault to return a source_url for a non-existent file
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )

        # Simulate: walk finds the file with some hash, but it doesn't exist on disk
        with patch.object(reconciler, "_walk_vault", return_value={"vault://ghost.md": "abc123"}):
            with pytest.raises(FileNotFoundError):
                await reconciler.run()

        # embed should NOT have been called (FileNotFoundError during read)
        mock_embedder.embed.assert_not_called()
        mock_qdrant.upsert_chunks.assert_not_called()

    async def test_file_created_and_deleted_race_propagates(
        self, tmp_path: Path, mock_qdrant, mock_embedder
    ):
        """Creates a real file, lets _walk_vault find it, then deletes it before
        the embed loop executes. run() should raise FileNotFoundError."""
        note = tmp_path / "fleeting.md"
        note.write_text("# Fleeting\n\nSome content here.\n")

        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )

        # Let walk run normally, then delete the file before embed
        on_disk = reconciler._walk_vault()
        assert len(on_disk) == 1

        # Delete the file to simulate race condition
        note.unlink()

        # Now run() with patched walk to use the stale on_disk result
        with patch.object(reconciler, "_walk_vault", return_value=on_disk):
            with pytest.raises(FileNotFoundError):
                await reconciler.run()


class TestReconcilerEmptyChunksSkip:
    """Tests for the empty-chunks skip path in run()."""

    async def test_file_with_no_content_skips_embed_and_upsert(
        self, tmp_path: Path, mock_qdrant, mock_embedder
    ):
        """A file that yields no chunks (whitespace-only) must NOT call
        embedder.embed() or qdrant.upsert_chunks()."""
        (tmp_path / "empty.md").write_text("   \n\n\t  \n")

        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()

        mock_embedder.embed.assert_not_called()
        mock_qdrant.upsert_chunks.assert_not_called()

    async def test_reconciler_logs_unchanged_count_when_all_skip(
        self, tmp_path: Path, mock_qdrant, mock_embedder
    ):
        """When all files produce empty chunks, to_embed count is nonzero but
        no embed actually happens. run() should complete without error."""
        (tmp_path / "whitespace.md").write_text("\n\n\n")

        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        # Should not raise
        await reconciler.run()


class TestReconcilerDeleteAndReembed:
    """Tests for re-embedding when a file's hash changes."""

    async def test_changed_file_queued_for_delete_and_embed(
        self, tmp_path: Path, mock_qdrant, mock_embedder
    ):
        """When an indexed file has a different hash from disk, it should be
        added to both to_delete and to_embed."""
        note = tmp_path / "changed.md"
        note.write_text("# Changed\n\nNew content.\n")

        # Qdrant reports an old hash
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://changed.md": "old_hash_value_that_differs"
        }

        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()

        # delete_by_source_url should have been called (because hash changed)
        mock_qdrant.delete_by_source_url.assert_called_once_with("vault://changed.md")
        # upsert_chunks should have been called (re-embed)
        mock_qdrant.upsert_chunks.assert_called_once()
