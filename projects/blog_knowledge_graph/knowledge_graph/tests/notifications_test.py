"""Tests for Slack notifications."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.models import ScrapeResult
from projects.blog_knowledge_graph.knowledge_graph.app.notifications import (
    SlackNotifier,
)

_NOTIF_PATH = (
    "projects.blog_knowledge_graph.knowledge_graph.app.notifications.httpx.AsyncClient"
)


class TestSlackNotifier:
    @pytest.mark.asyncio
    async def test_batch_notify_sends_webhook(self):
        with patch(_NOTIF_PATH) as mock_client_cls:
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
        with patch(_NOTIF_PATH) as mock_client_cls:
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


class TestSlackNotifierBatchContent:
    """Tests for batch notification message content and edge cases."""

    @pytest.mark.asyncio
    async def test_batch_with_no_new_items_has_no_new_content_section(self):
        """When no items are new, the 'New content' block is absent."""
        with patch(_NOTIF_PATH) as mock_client_cls:
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
                    url="https://example.com/old",
                    content_hash="h1",
                    is_new=False,
                    title="Old Post",
                    error=None,
                ),
            ]
            await notifier.notify_batch(results)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "New content:" not in payload["text"]
        assert "New: 0" in payload["text"]

    @pytest.mark.asyncio
    async def test_batch_with_more_than_10_new_items_truncates(self):
        """When > 10 new items, only 10 titles are listed plus '... and N more'."""
        with patch(_NOTIF_PATH) as mock_client_cls:
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
                    url=f"https://example.com/{i}",
                    content_hash=f"h{i}",
                    is_new=True,
                    title=f"Post {i}",
                    error=None,
                )
                for i in range(13)
            ]
            await notifier.notify_batch(results)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        text = payload["text"]
        assert "New: 13" in text
        # Only 10 titles should be listed
        listed = [line for line in text.split("\n") if line.startswith("- ")]
        assert len(listed) == 10
        # The overflow message must appear
        assert "and 3 more" in text

    @pytest.mark.asyncio
    async def test_batch_with_exactly_10_new_items_no_truncation(self):
        """Exactly 10 new items should list all without overflow message."""
        with patch(_NOTIF_PATH) as mock_client_cls:
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
                    url=f"https://example.com/{i}",
                    content_hash=f"h{i}",
                    is_new=True,
                    title=f"Post {i}",
                    error=None,
                )
                for i in range(10)
            ]
            await notifier.notify_batch(results)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        text = payload["text"]
        listed = [line for line in text.split("\n") if line.startswith("- ")]
        assert len(listed) == 10
        assert "more" not in text

    @pytest.mark.asyncio
    async def test_batch_includes_error_count(self):
        """Error count is reported correctly in batch summary."""
        with patch(_NOTIF_PATH) as mock_client_cls:
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
                    url="https://example.com/fail",
                    content_hash=None,
                    is_new=False,
                    title="",
                    error="Timeout",
                ),
                ScrapeResult(
                    url="https://example.com/ok",
                    content_hash="abc",
                    is_new=True,
                    title="OK Post",
                    error=None,
                ),
            ]
            await notifier.notify_batch(results)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        text = payload["text"]
        assert "Errors: 1" in text
        assert "Total: 2" in text


class TestSlackNotifierSingle:
    """Tests for single item notifications."""

    @pytest.mark.asyncio
    async def test_single_notify_noop_without_webhook(self):
        """notify_single with empty webhook_url does nothing."""
        notifier = SlackNotifier("")
        result = ScrapeResult(
            url="https://example.com/page",
            content_hash="hash",
            is_new=True,
            title="Test",
            error=None,
        )
        # Should not raise
        await notifier.notify_single(result)

    @pytest.mark.asyncio
    async def test_single_notify_includes_title_and_url(self):
        """notify_single message contains both title and URL."""
        with patch(_NOTIF_PATH) as mock_client_cls:
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
                url="https://example.com/new-article",
                content_hash="abc",
                is_new=True,
                title="My New Article",
                error=None,
            )
            await notifier.notify_single(result)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        text = payload["text"]
        assert "My New Article" in text
        assert "https://example.com/new-article" in text


class TestSlackNotifierErrorHandling:
    """Tests for error handling in the _post method."""

    @pytest.mark.asyncio
    async def test_post_exception_is_swallowed_and_logged(self, caplog):
        """Exceptions during HTTP post are caught and logged, not propagated."""
        with patch(_NOTIF_PATH) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = Exception("Network unreachable")

            notifier = SlackNotifier("https://hooks.slack.com/test")
            with caplog.at_level(logging.ERROR):
                # Should not raise
                await notifier._post("test message")

        assert any(
            "Failed to send Slack notification" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_batch_notify_does_not_raise_on_webhook_failure(self):
        """If Slack webhook fails, notify_batch swallows the error."""
        with patch(_NOTIF_PATH) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = Exception("Slack is down")

            notifier = SlackNotifier("https://hooks.slack.com/test")
            results = [
                ScrapeResult(
                    url="https://example.com",
                    content_hash="h1",
                    is_new=True,
                    title="Post",
                    error=None,
                )
            ]
            # Must not raise
            await notifier.notify_batch(results)

    @pytest.mark.asyncio
    async def test_post_sends_correct_webhook_url(self):
        """The POST request targets the configured webhook URL."""
        with patch(_NOTIF_PATH) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.post.return_value = mock_response

            webhook = "https://hooks.slack.com/services/ABC/DEF/GHI"
            notifier = SlackNotifier(webhook)
            await notifier._post("hello")

        url_called = mock_client.post.call_args.args[0]
        assert url_called == webhook

    @pytest.mark.asyncio
    async def test_post_sends_json_with_text_key(self):
        """The POST body is JSON with a 'text' key."""
        with patch(_NOTIF_PATH) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.post.return_value = mock_response

            notifier = SlackNotifier("https://hooks.slack.com/test")
            await notifier._post("custom message content")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["text"] == "custom message content"
