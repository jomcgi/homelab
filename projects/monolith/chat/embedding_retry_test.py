"""Tests for EmbeddingClient retry behavior with exponential backoff.

The embedding service (voyage-4-nano via llama.cpp) can be transiently
unavailable during model reloads. The client should retry with
exponential backoff on transient errors, matching the VisionClient's
retry strategy.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.embedding import EmbeddingClient


def _make_mock_http_client(response=None, side_effect=None):
    """Build an async-context-manager mock for httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if side_effect is not None:
        mock_client.post.side_effect = side_effect
    else:
        mock_client.post.return_value = response
    return mock_client


def _ok_response(embedding=None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "data": [{"index": 0, "embedding": embedding or [0.1] * 1024}]
    }
    return resp


def _server_error_response(status_code: int = 503) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Service Unavailable",
        request=MagicMock(),
        response=resp,
    )
    return resp


class TestEmbeddingClientRetry:
    @pytest.mark.asyncio
    async def test_retries_on_connect_error_then_succeeds(self):
        """embed() retries on ConnectError and returns when the server comes back."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    httpx.ConnectError("Connection refused"),
                    httpx.ConnectError("Connection refused"),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_server_error_then_succeeds(self):
        """embed() retries on 5xx status and returns when the server recovers."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    _server_error_response(503),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_on_400(self):
        """embed() does NOT retry on 400 Bad Request — it's a client error, not transient."""
        client = EmbeddingClient(base_url="http://fake:8080")

        resp_400 = MagicMock()
        resp_400.status_code = 400
        resp_400.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=resp_400
        )

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(side_effect=[resp_400])
            mock_cls.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.embed("hello world")

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retries_on_read_timeout_then_succeeds(self):
        """embed() retries on ReadTimeout."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    httpx.ReadTimeout("Read timed out"),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Retry delays follow exponential backoff: 2s, 4s, 8s, ..."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    httpx.ConnectError("down"),
                    httpx.ConnectError("down"),
                    httpx.ConnectError("down"),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            await client.embed("hello world")

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(2.0)
        assert delays[1] == pytest.approx(4.0)
        assert delays[2] == pytest.approx(8.0)

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self):
        """embed() raises the last exception after exhausting retries."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock),
            # Speed up: set a short total timeout
            patch("chat.embedding.EMBED_RETRY_TIMEOUT", 5.0),
        ):
            mock_http = _make_mock_http_client(
                side_effect=httpx.ConnectError("Connection refused"),
            )
            mock_cls.return_value = mock_http

            with pytest.raises(httpx.ConnectError):
                await client.embed("hello world")
