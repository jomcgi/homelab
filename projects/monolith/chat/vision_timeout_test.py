"""Tests for VisionClient -- timeout/connect errors and env var fallback.

vision_errors_test.py covers HTTP status errors and malformed response shapes.
vision_test.py covers the happy path and base64 encoding.
This file covers the remaining gaps:
  - TimeoutException propagation
  - ConnectError propagation
  - VisionClient() fallback to LLAMA_CPP_URL env var when no base_url given
  - Payload fields: model, max_tokens, system prompt content
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.vision import VisionClient, VISION_SYSTEM_PROMPT


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


def _ok_response(content: str = "A nice image") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


# ---------------------------------------------------------------------------
# TimeoutException and ConnectError propagation
# ---------------------------------------------------------------------------


class TestVisionClientNetworkErrors:
    @pytest.mark.asyncio
    async def test_raises_timeout_exception(self):
        """describe() propagates httpx.TimeoutException when the request times out."""
        client = VisionClient(base_url="http://fake:8080")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(
                side_effect=httpx.TimeoutException("request timed out")
            )
            with pytest.raises(httpx.TimeoutException):
                await client.describe(b"\x89PNG", "image/png")

    @pytest.mark.asyncio
    async def test_raises_connect_error(self):
        """describe() propagates httpx.ConnectError when the server is unreachable."""
        client = VisionClient(base_url="http://fake:8080")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(
                side_effect=httpx.ConnectError("Connection refused")
            )
            with pytest.raises(httpx.ConnectError):
                await client.describe(b"\x89PNG", "image/png")


# ---------------------------------------------------------------------------
# Env var fallback (no base_url provided to constructor)
# ---------------------------------------------------------------------------


class TestVisionClientEnvFallback:
    def test_uses_llama_cpp_url_when_no_base_url(self):
        """VisionClient() with no base_url stores the LLAMA_CPP_URL module constant."""
        with patch("chat.vision.LLAMA_CPP_URL", "http://env-llama:8080"):
            client = VisionClient()
        assert client.base_url == "http://env-llama:8080"

    def test_provided_base_url_overrides_env(self):
        """An explicit base_url is used even when LLAMA_CPP_URL is set."""
        with patch("chat.vision.LLAMA_CPP_URL", "http://env-llama:8080"):
            client = VisionClient(base_url="http://explicit:9090")
        assert client.base_url == "http://explicit:9090"

    @pytest.mark.asyncio
    async def test_describe_uses_client_base_url_in_request(self):
        """describe() constructs the request URL from self.base_url."""
        client = VisionClient(base_url="http://myhost:1234")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(response=_ok_response())
            await client.describe(b"\x89PNG", "image/png")

        mock_http_client = mock_cls.return_value
        call_args = mock_http_client.post.call_args
        url = call_args[0][0]
        assert url == "http://myhost:1234/v1/chat/completions"


# ---------------------------------------------------------------------------
# Payload fields verification
# ---------------------------------------------------------------------------


class TestVisionClientPayload:
    @pytest.mark.asyncio
    async def test_payload_includes_correct_model(self):
        """describe() sends 'gemma-4-26b-a4b' as the model in the payload."""
        client = VisionClient(base_url="http://fake:8080")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(response=_ok_response())
            await client.describe(b"\x89PNG", "image/png")

        payload = mock_cls.return_value.post.call_args.kwargs.get("json")
        assert payload["model"] == "gemma-4-26b-a4b"

    @pytest.mark.asyncio
    async def test_payload_includes_max_tokens_256(self):
        """describe() sends max_tokens=256 in the payload."""
        client = VisionClient(base_url="http://fake:8080")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(response=_ok_response())
            await client.describe(b"\x89PNG", "image/png")

        payload = mock_cls.return_value.post.call_args.kwargs.get("json")
        assert payload["max_tokens"] == 256

    @pytest.mark.asyncio
    async def test_payload_system_prompt_matches_module_constant(self):
        """describe() uses the VISION_SYSTEM_PROMPT constant as the system message."""
        client = VisionClient(base_url="http://fake:8080")

        with patch("chat.vision.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_mock_http_client(response=_ok_response())
            await client.describe(b"\x89PNG", "image/png")

        payload = mock_cls.return_value.post.call_args.kwargs.get("json")
        messages = payload["messages"]
        system_messages = [m for m in messages if m["role"] == "system"]
        assert len(system_messages) == 1
        assert system_messages[0]["content"] == VISION_SYSTEM_PROMPT
