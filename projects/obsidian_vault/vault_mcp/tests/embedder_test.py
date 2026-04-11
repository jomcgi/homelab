"""Tests for fastembed wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from projects.obsidian_vault.vault_mcp.app.embedder import VaultEmbedder


class TestVaultEmbedder:
    def test_embed_returns_vectors(self):
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.full(768, 0.1), np.full(768, 0.2)])
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        result = embedder.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 768

    def test_embed_query_returns_single_vector(self):
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.full(768, 0.1)])
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        result = embedder.embed_query("search query")
        assert len(result) == 768

    def test_dimension_is_768(self):
        mock_model = MagicMock()
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        assert embedder.dimension == 768

    def test_embed_batch_size_is_32(self):
        """EMBED_BATCH_SIZE class constant must be 32 for CPU safety."""
        mock_model = MagicMock()
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        assert embedder.EMBED_BATCH_SIZE == 32

    def test_embed_initialises_with_single_thread(self):
        """TextEmbedding must be initialised with threads=1 for CPU safety."""
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        _, kwargs = mock_cls.call_args
        assert kwargs.get("threads") == 1

    def test_embed_returns_python_lists(self):
        """embed() must return plain Python lists, not numpy arrays."""
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.full(768, 0.5)])
        with patch(
            "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding",
            return_value=mock_model,
        ):
            embedder = VaultEmbedder(model="test-model", cache_dir="/tmp/cache")
        result = embedder.embed(["text"])
        assert isinstance(result[0], list)
