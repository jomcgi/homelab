"""Embedding client -- calls voyage-4-nano via llama.cpp /v1/embeddings."""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "")

# Retry configuration — generous enough to survive a model reload.
EMBED_MAX_RETRIES = 12
EMBED_RETRY_BASE_DELAY = 2.0  # seconds
EMBED_RETRY_MAX_DELAY = 30.0  # cap per-retry wait
EMBED_RETRY_TIMEOUT = 300.0  # 5 min total deadline

EMBED_CONNECT_TIMEOUT = 5.0
EMBED_READ_TIMEOUT = 30.0


def _is_retryable(exc: Exception) -> bool:
    """Return True for transient errors worth retrying."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return True
    if isinstance(exc, httpx.ReadTimeout):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


class EmbeddingClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or EMBEDDING_URL

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, returning a 1024-dim vector.

        Retries with exponential backoff on transient errors (connection
        failures, timeouts, 5xx) for up to 5 minutes so the bot can
        survive a llama-server restart / model reload.
        """
        timeout = httpx.Timeout(EMBED_READ_TIMEOUT, connect=EMBED_CONNECT_TIMEOUT)
        elapsed = 0.0
        last_exc: Exception | None = None

        for attempt in range(EMBED_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/embeddings",
                        json={"input": text, "model": "voyage-4-nano"},
                    )
                    resp.raise_for_status()
                    try:
                        return resp.json()["data"][0]["embedding"]
                    except (KeyError, IndexError) as e:
                        raise ValueError(
                            f"unexpected embedding response shape: {e}"
                        ) from e
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc):
                    raise

                delay = min(
                    EMBED_RETRY_BASE_DELAY * (2**attempt),
                    EMBED_RETRY_MAX_DELAY,
                )
                elapsed += delay
                if elapsed > EMBED_RETRY_TIMEOUT:
                    break

                logger.warning(
                    "Embedding call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    EMBED_MAX_RETRIES,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]
