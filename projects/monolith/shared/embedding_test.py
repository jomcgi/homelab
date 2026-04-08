"""Tests for the embedding client (calls voyage-4-nano via llama.cpp)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


class TestEmbeddingClient:
    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, client):
        """embed() returns a list of floats from the API response."""
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": [{"index": 0, "embedding": [0.1] * 1024}]
        }

        with patch("shared.embedding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            result = await client.embed("hello world")

        assert len(result) == 1024
        assert result[0] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_embed_sends_correct_payload(self, client):
        """embed() sends the text to /v1/embeddings with the right model."""
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": [{"index": 0, "embedding": [0.0] * 1024}],
        }

        with patch("shared.embedding.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_client_cls.return_value = mock_client

            await client.embed("test input")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "/v1/embeddings" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["input"] == ["test input"]
