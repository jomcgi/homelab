"""Extractor protocol and shared utilities."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx

from knowledge_graph.app.models import Document

logger = logging.getLogger(__name__)


@runtime_checkable
class Extractor(Protocol):
    def can_handle(self, url: str, source_type: str) -> bool: ...
    def extract(self, url: str, client: httpx.AsyncClient) -> list[Document]: ...


class RateLimiter:
    """Per-domain rate limiter."""

    def __init__(self, default_delay: float = 1.0):
        self._default_delay = default_delay
        self._last_request: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, url: str) -> None:
        domain = urlparse(url).netloc
        async with self._locks[domain]:
            elapsed = time.monotonic() - self._last_request[domain]
            if elapsed < self._default_delay:
                await asyncio.sleep(self._default_delay - elapsed)
            self._last_request[domain] = time.monotonic()


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> httpx.Response:
    """Fetch URL with exponential backoff on 429, 5xx, timeouts."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = await client.get(url, follow_redirects=True, timeout=30.0)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_attempts - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Retryable status %d for %s, waiting %.1fs (attempt %d/%d)",
                        response.status_code,
                        url,
                        delay,
                        attempt + 1,
                        max_attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            if attempt < max_attempts - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Network error for %s: %s, waiting %.1fs (attempt %d/%d)",
                    url,
                    e,
                    delay,
                    attempt + 1,
                    max_attempts,
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise RuntimeError(f"All {max_attempts} attempts failed for {url}") from last_exc
