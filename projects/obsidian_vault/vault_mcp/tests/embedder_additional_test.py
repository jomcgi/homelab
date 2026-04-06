"""Additional tests for VaultEmbedder covering gaps in embedder_test.py."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from projects.obsidian_vault.vault_mcp.app.embedder import VaultEmbedder

_PATCH_TARGET = "projects.obsidian_vault.vault_mcp.app.embedder.TextEmbedding"


def _make_embedder(
    model: str = "test-model", cache_dir: str = "/tmp/cache"
) -> tuple[VaultEmbedder, MagicMock]:
    mock_model = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_model) as _:
        embedder = VaultEmbedder(model=model, cache_dir=cache_dir)
    return embedder, mock_model


class TestVaultEmbedderInit:
    def test_initialised_with_single_thread(self):
        """VaultEmbedder always initialises TextEmbedding with threads=1."""
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value = MagicMock()
            VaultEmbedder(model="some-model", cache_dir="/cache")
        _, kwargs = mock_cls.call_args
        assert kwargs.get("threads") == 1

    def test_model_name_forwarded(self):
        """The model_name kwarg passed to TextEmbedding matches the constructor arg."""
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value = MagicMock()
            VaultEmbedder(model="nomic-ai/nomic-embed-text-v1.5", cache_dir="/cache")
        _, kwargs = mock_cls.call_args
        assert kwargs.get("model_name") == "nomic-ai/nomic-embed-text-v1.5"

    def test_cache_dir_forwarded(self):
        """The cache_dir kwarg passed to TextEmbedding matches the constructor arg."""
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value = MagicMock()
            VaultEmbedder(model="test", cache_dir="/my/cache")
        _, kwargs = mock_cls.call_args
        assert kwargs.get("cache_dir") == "/my/cache"


class TestEmbedBatchSize:
    def test_batch_size_class_attribute_is_32(self):
        assert VaultEmbedder.EMBED_BATCH_SIZE == 32

    def test_embed_uses_batch_size_32(self):
        """embed() calls model.embed with batch_size=32."""
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.full(768, 0.1)])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        embedder.embed(["text"])
        mock_model.embed.assert_called_once_with(["text"], batch_size=32)


class TestEmbedEdgeCases:
    def test_embed_empty_list_returns_empty_list(self):
        """embed([]) returns [] without calling the model (empty iterator)."""
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed([])
        assert result == []

    def test_embed_returns_python_lists_not_numpy(self):
        """embed() converts numpy arrays to plain Python lists via .tolist()."""
        mock_model = MagicMock()
        arr = np.full(768, 0.5)
        mock_model.embed.return_value = iter([arr])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed(["text"])
        assert isinstance(result[0], list)
        assert not isinstance(result[0], np.ndarray)

    def test_embed_multiple_texts_returns_one_vector_per_text(self):
        """embed() returns exactly one vector per input text."""
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.full(768, float(i)) for i in range(4)])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed(["a", "b", "c", "d"])
        assert len(result) == 4

    def test_embed_vector_values_preserved(self):
        """Vector values from numpy array are correctly preserved in Python list."""
        mock_model = MagicMock()
        arr = np.array([0.1, 0.2, 0.3] + [0.0] * 765, dtype=float)
        mock_model.embed.return_value = iter([arr])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed(["text"])
        assert abs(result[0][0] - 0.1) < 1e-9
        assert abs(result[0][1] - 0.2) < 1e-9
        assert abs(result[0][2] - 0.3) < 1e-9


class TestEmbedQuery:
    def test_embed_query_calls_query_embed(self):
        """embed_query uses model.query_embed(), not model.embed()."""
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.full(768, 0.7)])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        embedder.embed_query("my query")
        mock_model.query_embed.assert_called_once_with("my query")
        mock_model.embed.assert_not_called()

    def test_embed_query_returns_python_list(self):
        """embed_query() converts the numpy result to a Python list."""
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.full(768, 0.3)])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed_query("query")
        assert isinstance(result, list)
        assert not isinstance(result, np.ndarray)

    def test_embed_query_returns_correct_length(self):
        """embed_query() returns a vector of length 768."""
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.full(768, 0.0)])
        with patch(_PATCH_TARGET, return_value=mock_model):
            embedder = VaultEmbedder(model="m", cache_dir="/c")
        result = embedder.embed_query("query")
        assert len(result) == 768


class TestDimension:
    def test_dimension_is_always_768(self):
        """dimension property always returns 768, regardless of model."""
        for model_name in ["model-a", "model-b", "nomic-ai/nomic-embed-text-v1.5"]:
            mock_model = MagicMock()
            with patch(_PATCH_TARGET, return_value=mock_model):
                embedder = VaultEmbedder(model=model_name, cache_dir="/c")
            assert embedder.dimension == 768, f"Expected 768 for model {model_name}"
