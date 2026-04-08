"""Tests for EmbeddingClient.embed_batch() -- batch embedding support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


def _mock_client_with_response(fake_response):
    """Set up a patched httpx.AsyncClient that returns the given response."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post.return_value = fake_response
    return mock_client


def _make_response(data: list[dict]) -> MagicMock:
    """Build a fake httpx response with the given data items."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"data": data}
    return resp


class TestEmbedBatch:
    @pytest.mark.asyncio
    async def test_returns_vectors_for_multiple_texts(self, client):
        """embed_batch() returns one vector per input text."""
        fake_response = _make_response(
            [
                {"index": 0, "embedding": [0.1] * 1024},
                {"index": 1, "embedding": [0.2] * 1024},
            ]
        )

        with patch("shared.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = _mock_client_with_response(fake_response)
            mock_cls.return_value = mock_http

            result = await client.embed_batch(["hello", "world"])

        assert len(result) == 2
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_sends_array_input(self, client):
        """embed_batch() sends input as an array in the request payload."""
        fake_response = _make_response(
            [
                {"index": 0, "embedding": [0.0] * 1024},
            ]
        )

        with patch("shared.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = _mock_client_with_response(fake_response)
            mock_cls.return_value = mock_http

            await client.embed_batch(["test"])

        call_kwargs = mock_http.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["input"] == ["test"]
        assert payload["model"] == "voyage-4-nano"

    @pytest.mark.asyncio
    async def test_model_arg_overrides_default_in_request_body(self):
        """Constructor's `model` kwarg appears in the POST body instead of the default."""
        custom_client = EmbeddingClient(
            base_url="http://fake:8080",
            model="custom-model-v9",
        )
        fake_response = _make_response(
            [
                {"index": 0, "embedding": [0.0] * 1024},
            ]
        )

        with patch("shared.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = _mock_client_with_response(fake_response)
            mock_cls.return_value = mock_http

            await custom_client.embed_batch(["hi"])

        payload = mock_http.post.call_args[1]["json"]
        assert payload["model"] == "custom-model-v9"

    @pytest.mark.asyncio
    async def test_sorts_by_index(self, client):
        """embed_batch() returns vectors sorted by the API response index field."""
        fake_response = _make_response(
            [
                {"index": 1, "embedding": [0.2] * 1024},
                {"index": 0, "embedding": [0.1] * 1024},
            ]
        )

        with patch("shared.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = _mock_client_with_response(fake_response)
            mock_cls.return_value = mock_http

            result = await client.embed_batch(["first", "second"])

        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_embed_delegates_to_embed_batch(self, client):
        """embed() delegates to embed_batch() with a single-element list."""
        expected_vector = [0.5] * 1024

        with patch.object(client, "embed_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = [expected_vector]

            result = await client.embed("test text")

        mock_batch.assert_called_once_with(["test text"])
        assert result == expected_vector
