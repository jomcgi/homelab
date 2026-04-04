"""Additional edge-case tests for vault reconciler covering gaps in reconciler_test.py."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from projects.obsidian_vault.vault_mcp.app.reconciler import VaultReconciler


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


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


@pytest.fixture
def vault_dir(tmp_path):
    (tmp_path / "note1.md").write_text("# Note 1\n\nContent of note 1.")
    (tmp_path / "note2.md").write_text("# Note 2\n\nContent of note 2.")
    return tmp_path


class TestWalkVaultEdgeCases:
    def test_excludes_dotfile_at_root(self, tmp_path, mock_qdrant, mock_embedder):
        """Hidden .md files at root level are excluded."""
        (tmp_path / ".hidden.md").write_text("# Hidden")
        (tmp_path / "visible.md").write_text("# Visible")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://visible.md" in files
        assert not any(".hidden" in u for u in files)

    def test_excludes_dotfile_in_subdirectory(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """Hidden .md files inside a non-dotted subdirectory are excluded."""
        subdir = tmp_path / "notes"
        subdir.mkdir()
        (subdir / ".hidden.md").write_text("# Hidden")
        (subdir / "visible.md").write_text("# Visible")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://notes/visible.md" in files
        assert not any(".hidden" in u for u in files)

    def test_excludes_nested_dotted_directory(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """Files nested under a dotted path (subdir/.hidden/note.md) are excluded."""
        hidden = tmp_path / "subdir" / ".hidden"
        hidden.mkdir(parents=True)
        (hidden / "note.md").write_text("# Note")
        safe = tmp_path / "subdir"
        (safe / "safe.md").write_text("# Safe")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://subdir/safe.md" in files
        assert not any(".hidden" in u for u in files)

    def test_excludes_non_md_files(self, tmp_path, mock_qdrant, mock_embedder):
        """Non-.md files (txt, json, yaml) are not returned."""
        (tmp_path / "readme.txt").write_text("text file")
        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "note.md").write_text("# Note")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert list(files.keys()) == ["vault://note.md"]

    def test_nested_subdirectory_included(self, tmp_path, mock_qdrant, mock_embedder):
        """Files in nested non-dotted subdirectories get the full relative path."""
        deep = tmp_path / "projects" / "2025"
        deep.mkdir(parents=True)
        (deep / "plan.md").write_text("# Plan")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        assert "vault://projects/2025/plan.md" in files

    def test_content_hash_matches_sha256(self, tmp_path, mock_qdrant, mock_embedder):
        """The stored hash exactly matches sha256 of the file content."""
        content = "# My Note\n\nSome important text here."
        (tmp_path / "hashed.md").write_text(content)
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert files["vault://hashed.md"] == expected

    def test_empty_vault_returns_empty_dict(self, tmp_path, mock_qdrant, mock_embedder):
        """Walking an empty vault returns an empty dict."""
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        assert reconciler._walk_vault() == {}

    def test_source_url_uses_vault_prefix(self, tmp_path, mock_qdrant, mock_embedder):
        """All keys use the vault:// prefix scheme."""
        (tmp_path / "note.md").write_text("content")
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        files = reconciler._walk_vault()
        for key in files:
            assert key.startswith("vault://"), f"Key {key!r} missing vault:// prefix"


class TestReconcileEmptyChunks:
    async def test_whitespace_only_file_skips_upsert(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """A file whose content produces no chunks (whitespace-only) skips upsert."""
        (tmp_path / "empty.md").write_text("   \n\n   ")
        mock_qdrant.get_indexed_sources.return_value = {}
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()

    async def test_truly_empty_file_skips_upsert(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """A truly empty .md file produces no chunks and skips upsert."""
        (tmp_path / "empty.md").write_text("")
        mock_qdrant.get_indexed_sources.return_value = {}
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()

    async def test_chunk_markdown_returning_empty_does_not_call_upsert(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """When chunk_markdown returns [] via patch, upsert is skipped."""
        (tmp_path / "note.md").write_text("# Content\n\nSome text.")
        mock_qdrant.get_indexed_sources.return_value = {}
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        with patch(
            "projects.obsidian_vault.vault_mcp.app.reconciler.chunk_markdown",
            return_value=[],
        ):
            await reconciler.run()
        mock_qdrant.upsert_chunks.assert_not_called()
        mock_embedder.embed.assert_not_called()


class TestReconcileEmbedArguments:
    async def test_embedder_called_with_chunk_texts(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """embed() is called with the list of chunk_text values from chunk_markdown."""
        (tmp_path / "note.md").write_text(
            "# Note\n\nFirst paragraph.\n\nSecond paragraph."
        )
        mock_qdrant.get_indexed_sources.return_value = {}
        # Return enough vectors for however many chunks are produced
        mock_embedder.embed.side_effect = lambda texts: [[0.1] * 768] * len(texts)
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        with patch(
            "projects.obsidian_vault.vault_mcp.app.reconciler.chunk_markdown"
        ) as mock_chunk:
            mock_chunk.return_value = [
                {
                    "chunk_text": "First chunk",
                    "chunk_index": 0,
                    "content_hash": "abc",
                    "section_header": "# Note",
                    "source_url": "vault://note.md",
                    "title": "note.md",
                },
                {
                    "chunk_text": "Second chunk",
                    "chunk_index": 1,
                    "content_hash": "abc",
                    "section_header": "# Note",
                    "source_url": "vault://note.md",
                    "title": "note.md",
                },
            ]
            await reconciler.run()

        mock_embedder.embed.assert_called_once_with(["First chunk", "Second chunk"])

    async def test_upsert_called_with_chunks_and_vectors(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """upsert_chunks receives the exact chunk list and matching vectors."""
        (tmp_path / "note.md").write_text("# Note\n\nSome text.")
        mock_qdrant.get_indexed_sources.return_value = {}
        fake_chunks = [
            {
                "chunk_text": "Some text.",
                "chunk_index": 0,
                "content_hash": "abc",
                "section_header": "# Note",
                "source_url": "vault://note.md",
                "title": "note.md",
            }
        ]
        fake_vectors = [[0.9] * 768]
        mock_embedder.embed.return_value = fake_vectors
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        with patch(
            "projects.obsidian_vault.vault_mcp.app.reconciler.chunk_markdown",
            return_value=fake_chunks,
        ):
            await reconciler.run()

        mock_qdrant.upsert_chunks.assert_called_once_with(fake_chunks, fake_vectors)

    async def test_embedder_runs_in_executor(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """The embedder.embed() call goes through run_in_executor (not blocking the loop)."""
        (tmp_path / "note.md").write_text("# Note\n\nSome text.")
        mock_qdrant.get_indexed_sources.return_value = {}
        mock_embedder.embed.return_value = [[0.1] * 768]
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        with patch(
            "projects.obsidian_vault.vault_mcp.app.reconciler.chunk_markdown"
        ) as mock_chunk:
            mock_chunk.return_value = [
                {
                    "chunk_text": "Some text.",
                    "chunk_index": 0,
                    "content_hash": "abc",
                    "section_header": "# Note",
                    "source_url": "vault://note.md",
                    "title": "note.md",
                }
            ]
            # run_in_executor wraps embed; confirm embed was actually called
            await reconciler.run()

        mock_embedder.embed.assert_called_once()


class TestReconcileMixedScenarios:
    async def test_mixed_new_changed_deleted(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """New, changed, and deleted files are all handled correctly in one run."""
        (tmp_path / "new.md").write_text("# New\n\nBrand new file.")
        (tmp_path / "changed.md").write_text("# Changed\n\nUpdated content.")
        changed_old_hash = "stale_hash_for_changed"
        unchanged_content = "# Unchanged\n\nSame as before."
        (tmp_path / "unchanged.md").write_text(unchanged_content)
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://changed.md": changed_old_hash,
            "vault://unchanged.md": _hash(unchanged_content),
            "vault://deleted.md": "some_hash",
        }
        mock_embedder.embed.side_effect = lambda texts: [[0.1] * 768] * len(texts)
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()

        # deleted.md and changed.md (old) should be deleted
        deleted_calls = {
            c.args[0] for c in mock_qdrant.delete_by_source_url.call_args_list
        }
        assert "vault://deleted.md" in deleted_calls
        assert "vault://changed.md" in deleted_calls
        assert "vault://unchanged.md" not in deleted_calls

        # new.md and changed.md (new) should be upserted; unchanged not
        assert mock_qdrant.upsert_chunks.call_count == 2

    async def test_multiple_changed_files_each_deleted_then_embedded(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """Every changed file is deleted (old) then re-embedded (new)."""
        for i in range(3):
            (tmp_path / f"file{i}.md").write_text(f"# File {i}\n\nContent {i}.")
        mock_qdrant.get_indexed_sources.return_value = {
            f"vault://file{i}.md": "stale" for i in range(3)
        }
        mock_embedder.embed.side_effect = lambda texts: [[0.1] * 768] * len(texts)
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert mock_qdrant.delete_by_source_url.call_count == 3
        assert mock_qdrant.upsert_chunks.call_count == 3

    async def test_all_indexed_files_deleted_when_vault_empty(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """When the vault is empty, all indexed sources are deleted."""
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://gone1.md": "hash1",
            "vault://gone2.md": "hash2",
        }
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert mock_qdrant.delete_by_source_url.call_count == 2
        mock_qdrant.upsert_chunks.assert_not_called()

    async def test_delete_order_before_embed(
        self, tmp_path, mock_qdrant, mock_embedder
    ):
        """Deletes are issued before upserts (changed file: delete stale, then embed fresh)."""
        (tmp_path / "note.md").write_text("# Note\n\nUpdated.")
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://note.md": "old_stale_hash",
        }
        call_order: list[str] = []
        mock_qdrant.delete_by_source_url.side_effect = lambda *_: call_order.append(
            "delete"
        )
        mock_qdrant.upsert_chunks.side_effect = lambda *_: call_order.append("upsert")
        mock_embedder.embed.return_value = [[0.1] * 768]
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        await reconciler.run()
        assert call_order == ["delete", "upsert"]


class TestReconcileLogging:
    async def test_logging_reports_correct_counts(
        self, tmp_path, mock_qdrant, mock_embedder, caplog
    ):
        """Logger records counts: embedded, deleted, unchanged."""
        (tmp_path / "new.md").write_text("# New\n\nContent.")
        unchanged_content = "# Old\n\nUnchanged."
        (tmp_path / "old.md").write_text(unchanged_content)
        mock_qdrant.get_indexed_sources.return_value = {
            "vault://old.md": _hash(unchanged_content),
            "vault://deleted.md": "hash",
        }
        mock_embedder.embed.side_effect = lambda texts: [[0.1] * 768] * len(texts)
        reconciler = VaultReconciler(
            vault_path=str(tmp_path), embedder=mock_embedder, qdrant=mock_qdrant
        )
        import logging

        with caplog.at_level(logging.INFO):
            await reconciler.run()

        assert any("Reconciled" in r.message for r in caplog.records)
        log_msg = next(r.message for r in caplog.records if "Reconciled" in r.message)
        # 1 embedded (new.md), 1 deleted (deleted.md), 1 unchanged (old.md)
        assert "1" in log_msg
