"""Tests for EmbeddingClient.embed() -- null / None embedding in API response.

When the API returns ``{"data": [{"embedding": null}]}``, the ``embed()`` method
returns ``None`` to the caller because the key exists (no KeyError) and its value
is JSON null → Python None.  This test documents that silent-None behaviour and
also covers the case where ``data`` is an empty list (should raise ValueError).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


def _mock_client_returning(json_data: dict):
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = json_data
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post.return_value = fake_response
    return mock_client


class TestEmbedNullResponse:
    @pytest.mark.asyncio
    async def test_returns_none_when_embedding_value_is_null(self, client):
        """embed() returns None when the API sends {'embedding': null}.

        The JSON null maps to Python None; because the key exists no KeyError
        is raised — None passes through silently.  Callers must guard against
        None return values.
        """
        mock_client = _mock_client_returning(
            {"data": [{"index": 0, "embedding": None}]}
        )

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            result = await client.embed("some text")

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_data_list(self, client):
        """embed() raises ValueError when 'data' is an empty list (IndexError path)."""
        mock_client = _mock_client_returning({"data": []})

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(ValueError, match="unexpected embedding response shape"):
                await client.embed("some text")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_embedding_key(self, client):
        """embed() raises ValueError when the 'embedding' key is absent from the first item."""
        mock_client = _mock_client_returning(
            {"data": [{"index": 0, "model": "voyage-4-nano"}]}
        )

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(ValueError, match="unexpected embedding response shape"):
                await client.embed("some text")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_data_key(self, client):
        """embed() raises ValueError when the top-level 'data' key is absent."""
        mock_client = _mock_client_returning({"object": "list"})

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            with pytest.raises(ValueError, match="unexpected embedding response shape"):
                await client.embed("some text")

    @pytest.mark.asyncio
    async def test_returns_valid_vector_when_response_is_well_formed(self, client):
        """embed() returns the embedding list when the response is well-formed."""
        mock_client = _mock_client_returning(
            {"data": [{"index": 0, "embedding": [0.5] * 1024}]}
        )

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client
            result = await client.embed("hello")

        assert len(result) == 1024
        assert result[0] == pytest.approx(0.5)
