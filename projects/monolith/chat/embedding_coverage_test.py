"""Additional coverage for EmbeddingClient -- HTTP errors and connection timeout."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


class TestEmbeddingClientErrors:
    @pytest.mark.asyncio
    async def test_raises_on_http_error(self, client):
        """embed() propagates HTTP errors raised by raise_for_status."""
        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=MagicMock(),
            response=MagicMock(),
        )

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.embed("test")

    @pytest.mark.asyncio
    async def test_raises_on_connection_timeout(self, client):
        """embed() propagates connection timeouts from httpx."""
        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.TimeoutException):
                await client.embed("slow query")

    @pytest.mark.asyncio
    async def test_raises_on_connect_error(self, client):
        """embed() propagates connection errors."""
        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                await client.embed("hello")


class TestEmbeddingClientBaseUrl:
    def test_uses_provided_base_url(self):
        """EmbeddingClient stores the provided base_url."""
        c = EmbeddingClient(base_url="http://custom:1234")
        assert c.base_url == "http://custom:1234"

    def test_falls_back_to_env_var(self):
        """EmbeddingClient uses the EMBEDDING_URL module constant when no base_url given."""
        with patch("chat.embedding.EMBEDDING_URL", "http://env-embed:9999"):
            c = EmbeddingClient()
        assert c.base_url == "http://env-embed:9999"
