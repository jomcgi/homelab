"""Tests for the three Pydantic AI tools used by the research agent."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from knowledge.research_tools import (
    MAX_FETCH_BYTES,
    WEB_FETCH_TIMEOUT_SECS,
    WebFetchResult,
    web_fetch,
)


@pytest.mark.asyncio
async def test_web_fetch_returns_body_and_content_hash():
    """web_fetch returns (url, body, content_hash, fetched_at)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>hello world</p></body></html>",
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/foo")

    assert isinstance(result, WebFetchResult)
    assert result.url == "https://example.com/foo"
    assert "hello world" in result.body
    assert result.content_hash.startswith("sha256:")
    assert result.fetched_at.endswith("Z")


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_text_content_types():
    """Binary/PDF/etc bodies are not synthesizable; return a clear empty result."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/foo.pdf")

    assert result.body == ""
    assert result.skipped_reason == "non-text content-type: application/pdf"


@pytest.mark.asyncio
async def test_web_fetch_truncates_at_max_bytes():
    """Bodies larger than MAX_FETCH_BYTES are truncated, not rejected."""
    big_body = "x" * (MAX_FETCH_BYTES * 2)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text=big_body
        )

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/big")

    assert len(result.body) == MAX_FETCH_BYTES
    assert result.truncated is True


@pytest.mark.asyncio
async def test_web_fetch_handles_timeout():
    """A timeout returns a result with empty body and a skipped_reason."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/slow")

    assert result.body == ""
    assert "timed out" in (result.skipped_reason or "").lower()


@pytest.mark.asyncio
async def test_web_fetch_handles_non_200():
    """Non-200 responses produce a skipped_reason rather than raising."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    with patch("knowledge.research_tools._build_client") as build:
        build.return_value = httpx.AsyncClient(
            transport=transport, timeout=WEB_FETCH_TIMEOUT_SECS
        )
        result = await web_fetch("https://example.com/missing")

    assert result.body == ""
    assert "404" in (result.skipped_reason or "")
