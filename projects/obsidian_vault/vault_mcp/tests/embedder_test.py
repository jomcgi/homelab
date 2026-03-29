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
