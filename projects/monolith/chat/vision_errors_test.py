"""Tests for vision client error paths -- bad response shapes and HTTP errors."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.vision import VisionClient


@pytest.fixture
def client():
    return VisionClient(base_url="http://fake:8080")


def _make_mock_http_client(response):
    """Helper to build the async-context-manager mock for httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post.return_value = response
    return mock_client


class TestVisionClientErrorPaths:
    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_choices_key(self, client):
        """describe() raises ValueError when 'choices' key is absent from response."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"result": "no choices here"}

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            with pytest.raises(ValueError, match="unexpected vision response shape"):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_choices(self, client):
        """describe() raises ValueError when 'choices' list is empty."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"choices": []}

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            with pytest.raises(ValueError, match="unexpected vision response shape"):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_message_key(self, client):
        """describe() raises ValueError when 'message' key is absent from choices[0]."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"choices": [{"no_message": True}]}

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            with pytest.raises(ValueError, match="unexpected vision response shape"):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_missing_content_key(self, client):
        """describe() raises ValueError when 'content' key is absent from message."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "choices": [{"message": {"role": "assistant"}}]
        }

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            with pytest.raises(ValueError, match="unexpected vision response shape"):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_propagates_http_error_from_raise_for_status(self, client):
        """describe() propagates HTTPStatusError raised by raise_for_status()."""
        error_resp = MagicMock()
        error_resp.status_code = 400  # 4xx is not retryable
        fake_response = MagicMock()
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=error_resp,
        )

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            with pytest.raises(httpx.HTTPStatusError):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_raise_for_status_called_before_json_parse(self, client):
        """describe() calls raise_for_status() on the response before parsing JSON."""
        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(fake_response)
            await client.describe(b"\x89PNG", "image/png")

        fake_response.raise_for_status.assert_called_once()
