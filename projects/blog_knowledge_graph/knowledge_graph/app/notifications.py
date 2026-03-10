"""Slack webhook notifications."""

from __future__ import annotations

import logging

import httpx

from projects.blog_knowledge_graph.knowledge_graph.app.models import ScrapeResult

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    async def notify_batch(self, results: list[ScrapeResult]) -> None:
        """Send batch summary to Slack."""
        if not self._webhook_url:
            return
        new_count = sum(1 for r in results if r["is_new"])
        error_count = sum(1 for r in results if r["error"])
        text = (
            f"*Knowledge Graph Scrape Complete*\n"
            f"Total: {len(results)} | New: {new_count} | Errors: {error_count}"
        )
        if new_count > 0:
            new_items = [r for r in results if r["is_new"]][:10]
            titles = "\n".join(f"- {r['title']}" for r in new_items)
            text += f"\n\n*New content:*\n{titles}"
            if new_count > 10:
                text += f"\n... and {new_count - 10} more"

        await self._post(text)

    async def notify_single(self, result: ScrapeResult) -> None:
        """Send per-item notification."""
        if not self._webhook_url:
            return
        text = f"*New content scraped:* {result['title']}\n{result['url']}"
        await self._post(text)

    async def _post(self, text: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._webhook_url,
                    json={"text": text},
                    timeout=10.0,
                )
                response.raise_for_status()
        except Exception:
            logger.exception("Failed to send Slack notification")
