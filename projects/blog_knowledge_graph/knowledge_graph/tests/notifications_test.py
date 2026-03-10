"""Tests for Slack notifications."""

from unittest.mock import AsyncMock, patch

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.models import ScrapeResult
from projects.blog_knowledge_graph.knowledge_graph.app.notifications import (
    SlackNotifier,
)


class TestSlackNotifier:
    @pytest.mark.asyncio
    async def test_batch_notify_sends_webhook(self):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.notifications.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.post.return_value = mock_response

            notifier = SlackNotifier("https://hooks.slack.com/test")
            results = [
                ScrapeResult(
                    url="https://example.com/1",
                    content_hash="h1",
                    is_new=True,
                    title="New Post",
                    error=None,
                ),
                ScrapeResult(
                    url="https://example.com/2",
                    content_hash="h2",
                    is_new=False,
                    title="Old Post",
                    error=None,
                ),
            ]
            await notifier.notify_batch(results)

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "Total: 2" in payload["text"]
            assert "New: 1" in payload["text"]

    @pytest.mark.asyncio
    async def test_batch_notify_noop_without_webhook(self):
        notifier = SlackNotifier("")
        # Should not raise
        await notifier.notify_batch([])

    @pytest.mark.asyncio
    async def test_single_notify(self):
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.notifications.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.post.return_value = mock_response

            notifier = SlackNotifier("https://hooks.slack.com/test")
            result = ScrapeResult(
                url="https://example.com/new",
                content_hash="h1",
                is_new=True,
                title="Brand New",
                error=None,
            )
            await notifier.notify_single(result)
            mock_client.post.assert_called_once()
