"""Tests for three remaining embedding.py coverage gaps.

Covers:
- ConnectTimeout retry-then-succeed cycle (gap: only ConnectError was tested)
- EMBED_RETRY_MAX_DELAY (30s) cap on exponential backoff (gap: cap was never asserted)
- httpx.Timeout passed to AsyncClient with correct EMBED_CONNECT_TIMEOUT / EMBED_READ_TIMEOUT
  values (gap: timeout values were never verified)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.embedding import (
    EMBED_CONNECT_TIMEOUT,
    EMBED_READ_TIMEOUT,
    EmbeddingClient,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as embedding_retry_test.py)
# ---------------------------------------------------------------------------


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
    resp.json.return_value = {"data": [{"embedding": embedding or [0.1] * 1024}]}
    return resp


# ---------------------------------------------------------------------------
# Gap 6: ConnectTimeout is retried (not just ConnectError)
# ---------------------------------------------------------------------------


class TestConnectTimeoutRetry:
    @pytest.mark.asyncio
    async def test_retries_on_connect_timeout_then_succeeds(self):
        """embed() retries on ConnectTimeout and returns when the server comes back."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    httpx.ConnectTimeout("Connect timed out"),
                    httpx.ConnectTimeout("Connect timed out"),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_connect_timeout_delays_follow_backoff(self):
        """Retry delays after ConnectTimeout follow exponential backoff: 2s, 4s."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = _make_mock_http_client(
                side_effect=[
                    httpx.ConnectTimeout("timed out"),
                    httpx.ConnectTimeout("timed out"),
                    _ok_response(),
                ]
            )
            mock_cls.return_value = mock_http
            await client.embed("hello world")

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == pytest.approx(2.0)
        assert delays[1] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_raises_connect_timeout_after_all_retries(self):
        """embed() re-raises ConnectTimeout after exhausting the timeout budget."""
        client = EmbeddingClient(base_url="http://fake:8080")

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock),
            patch("chat.embedding.EMBED_RETRY_TIMEOUT", 5.0),
        ):
            mock_http = _make_mock_http_client(
                side_effect=httpx.ConnectTimeout("never connects"),
            )
            mock_cls.return_value = mock_http

            with pytest.raises(httpx.ConnectTimeout):
                await client.embed("will fail")


# ---------------------------------------------------------------------------
# Gap 7: EMBED_RETRY_MAX_DELAY (30s) cap on exponential delay
# ---------------------------------------------------------------------------


class TestRetryMaxDelayCap:
    @pytest.mark.asyncio
    async def test_delay_is_capped_at_max_delay(self):
        """Retry delay at attempt 4 is capped at EMBED_RETRY_MAX_DELAY (30s), not 32s."""
        client = EmbeddingClient(base_url="http://fake:8080")

        # attempts 0–4 fail (sleep 2, 4, 8, 16, 30), attempt 5 succeeds
        side_effects = [httpx.ConnectError("down")] * 5 + [_ok_response()]

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            # Raise total deadline high so we don't terminate early
            patch("chat.embedding.EMBED_RETRY_TIMEOUT", 1000.0),
        ):
            mock_http = _make_mock_http_client(side_effect=side_effects)
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # attempt 0: min(2*1, 30) = 2
        assert delays[0] == pytest.approx(2.0)
        # attempt 1: min(2*2, 30) = 4
        assert delays[1] == pytest.approx(4.0)
        # attempt 2: min(2*4, 30) = 8
        assert delays[2] == pytest.approx(8.0)
        # attempt 3: min(2*8, 30) = 16
        assert delays[3] == pytest.approx(16.0)
        # attempt 4: min(2*16, 30) = min(32, 30) = 30  ← cap kicks in
        assert delays[4] == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_delay_stays_capped_past_attempt_4(self):
        """Subsequent retries after the cap is hit also use the capped value (30s)."""
        client = EmbeddingClient(base_url="http://fake:8080")

        # attempts 0–5 fail, attempt 6 succeeds
        side_effects = [httpx.ConnectError("down")] * 6 + [_ok_response()]

        with (
            patch("chat.embedding.httpx.AsyncClient") as mock_cls,
            patch("chat.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("chat.embedding.EMBED_RETRY_TIMEOUT", 1000.0),
        ):
            mock_http = _make_mock_http_client(side_effect=side_effects)
            mock_cls.return_value = mock_http
            result = await client.embed("hello world")

        assert len(result) == 1024
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # Both attempt 4 and attempt 5 should be capped at 30
        assert delays[4] == pytest.approx(30.0)
        assert delays[5] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Gap 8: Correct timeout values passed to httpx.AsyncClient
# ---------------------------------------------------------------------------


class TestEmbedTimeoutConfiguration:
    @pytest.mark.asyncio
    async def test_embed_passes_correct_timeout_to_async_client(self):
        """embed() passes httpx.Timeout with EMBED_READ_TIMEOUT and EMBED_CONNECT_TIMEOUT to AsyncClient."""
        client = EmbeddingClient(base_url="http://fake:8080")

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": [{"embedding": [0.0] * 1024}]}

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post.return_value = fake_response
            mock_cls.return_value = mock_http

            await client.embed("test text")

        # Verify timeout was passed to AsyncClient constructor
        call_kwargs = mock_cls.call_args
        timeout_arg = (
            call_kwargs.kwargs.get("timeout")
            if call_kwargs.kwargs
            else call_kwargs[1].get("timeout")
        )
        assert timeout_arg is not None, "timeout should be passed to httpx.AsyncClient"
        assert isinstance(timeout_arg, httpx.Timeout)

    @pytest.mark.asyncio
    async def test_embed_timeout_read_matches_constant(self):
        """embed() configures the AsyncClient read timeout to EMBED_READ_TIMEOUT."""
        client = EmbeddingClient(base_url="http://fake:8080")

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": [{"embedding": [0.0] * 1024}]}

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post.return_value = fake_response
            mock_cls.return_value = mock_http

            await client.embed("test text")

        call_kwargs = mock_cls.call_args
        timeout_arg = (
            call_kwargs.kwargs.get("timeout")
            if call_kwargs.kwargs
            else call_kwargs[1].get("timeout")
        )
        assert timeout_arg.read == pytest.approx(EMBED_READ_TIMEOUT)

    @pytest.mark.asyncio
    async def test_embed_timeout_connect_matches_constant(self):
        """embed() configures the AsyncClient connect timeout to EMBED_CONNECT_TIMEOUT."""
        client = EmbeddingClient(base_url="http://fake:8080")

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": [{"embedding": [0.0] * 1024}]}

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post.return_value = fake_response
            mock_cls.return_value = mock_http

            await client.embed("test text")

        call_kwargs = mock_cls.call_args
        timeout_arg = (
            call_kwargs.kwargs.get("timeout")
            if call_kwargs.kwargs
            else call_kwargs[1].get("timeout")
        )
        assert timeout_arg.connect == pytest.approx(EMBED_CONNECT_TIMEOUT)
