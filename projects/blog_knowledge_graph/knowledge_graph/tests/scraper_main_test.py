"""Tests for scraper FastAPI application."""

from __future__ import annotations

import ipaddress
from unittest.mock import MagicMock, patch

import pytest
import yaml

import projects.blog_knowledge_graph.knowledge_graph.app.scraper_main as scraper_module
from projects.blog_knowledge_graph.knowledge_graph.app.scraper_main import (
    _load_sources,
    _validate_url,
    app,
)


class TestLoadSources:
    def test_valid_sources(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(
            yaml.dump(
                {
                    "sources": [
                        {"url": "https://example.com/feed", "type": "rss"},
                        {"url": "https://example.com/page", "type": "html"},
                    ]
                }
            )
        )
        sources = _load_sources(str(p))
        assert len(sources) == 2
        assert sources[0]["type"] == "rss"
        assert sources[1]["type"] == "html"

    def test_duplicate_url_raises(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(
            yaml.dump(
                {
                    "sources": [
                        {"url": "https://example.com/feed", "type": "rss"},
                        {"url": "https://example.com/feed", "type": "html"},
                    ]
                }
            )
        )
        with pytest.raises(ValueError, match="Duplicate"):
            _load_sources(str(p))

    def test_missing_type_raises(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(yaml.dump({"sources": [{"url": "https://example.com/feed"}]}))
        with pytest.raises(ValueError, match="missing required"):
            _load_sources(str(p))

    def test_invalid_type_raises(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(
            yaml.dump(
                {"sources": [{"url": "https://example.com/feed", "type": "epub"}]}
            )
        )
        with pytest.raises(ValueError, match="Invalid source type"):
            _load_sources(str(p))

    def test_empty_sources(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(yaml.dump({"sources": []}))
        sources = _load_sources(str(p))
        assert sources == []

    def test_no_sources_key(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(yaml.dump({"other": "data"}))
        sources = _load_sources(str(p))
        assert sources == []

    def test_optional_name_field(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(
            yaml.dump(
                {
                    "sources": [
                        {
                            "url": "https://example.com/feed",
                            "type": "rss",
                            "name": "My Feed",
                        }
                    ]
                }
            )
        )
        sources = _load_sources(str(p))
        assert len(sources) == 1
        assert sources[0]["name"] == "My Feed"

    def test_missing_url_raises(self, tmp_path):
        p = tmp_path / "sources.yaml"
        p.write_text(yaml.dump({"sources": [{"type": "html"}]}))
        with pytest.raises(ValueError, match="missing required"):
            _load_sources(str(p))


class TestValidateUrl:
    def test_valid_https(self):
        _validate_url("https://example.com/page")

    def test_valid_http(self):
        _validate_url("http://example.com/page")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http"):
            _validate_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="scheme must be http"):
            _validate_url("file:///etc/passwd")

    def test_rejects_cluster_local(self):
        with pytest.raises(ValueError, match="cluster-internal"):
            _validate_url("http://qdrant.qdrant.svc.cluster.local:6333/collections")

    def test_rejects_empty_hostname(self):
        with pytest.raises(ValueError, match="hostname"):
            _validate_url("http://")

    def test_rejects_private_ip_address(self):
        """Verify that a hostname resolving to a private IP is rejected."""
        # Mock getaddrinfo to return a private RFC-1918 address
        private_info = [(None, None, None, None, ("192.168.1.1", 0))]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
            return_value=private_info,
        ):
            with pytest.raises(ValueError, match="private"):
                _validate_url("http://internal-host.example.com")

    def test_rejects_loopback_address(self):
        """Verify that a hostname resolving to loopback is rejected."""
        loopback_info = [(None, None, None, None, ("127.0.0.1", 0))]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
            return_value=loopback_info,
        ):
            with pytest.raises(ValueError, match="private"):
                _validate_url("http://localhost-alias.example.com")

    def test_dns_failure_is_allowed(self):
        """Verify DNS failures are allowed (sandbox/test environments)."""
        import socket

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            # Should not raise
            _validate_url("https://no-dns-in-sandbox.example.com")

    def test_public_ip_is_allowed(self):
        """Verify public IP is not blocked."""
        public_info = [(None, None, None, None, ("1.2.3.4", 0))]
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
            return_value=public_info,
        ):
            # Should not raise
            _validate_url("https://public-site.example.com")


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestScrapeEndpoint:
    """Tests for POST /scrape."""

    @pytest.mark.asyncio
    async def test_scrape_invalid_url_returns_400(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/scrape", json={"url": "ftp://evil.com"})
        assert response.status_code == 400
        assert "scheme must be http" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_scrape_cluster_local_returns_400(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/scrape",
                json={"url": "http://qdrant.ns.svc.cluster.local/data"},
            )
        assert response.status_code == 400
        assert "cluster-internal" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_scrape_valid_url_with_no_extractors(self, monkeypatch):
        """With no extractors initialized, scrape returns an error result (not a 5xx)."""
        from httpx import ASGITransport, AsyncClient

        monkeypatch.setenv("OTEL_ENABLED", "false")
        # Ensure extractors list is empty (default when lifespan is not run)
        with patch.object(scraper_module, "extractors", []):
            with patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
                return_value=[],
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/scrape",
                        json={"url": "https://example.com/page"},
                    )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["error"] is not None
        assert "No extractor" in data["results"][0]["error"]

    @pytest.mark.asyncio
    async def test_scrape_with_mock_extractor_stores_new_doc(self, monkeypatch):
        """When extractor returns a document and storage is set, it stores it."""
        from datetime import datetime

        from httpx import ASGITransport, AsyncClient

        from projects.blog_knowledge_graph.knowledge_graph.app.models import Document

        monkeypatch.setenv("OTEL_ENABLED", "false")

        mock_extractor = MagicMock()
        mock_extractor.can_handle.return_value = True
        mock_extractor.extract = MagicMock(
            return_value=[
                Document(
                    source_type="html",
                    source_url="https://example.com/page",
                    title="Test Page",
                    author=None,
                    published_at=None,
                    content="# Title\n\nContent here.",
                )
            ]
        )

        mock_storage = MagicMock()
        mock_storage.exists.return_value = False
        mock_storage.store.return_value = "abc123hash"

        with (
            patch.object(scraper_module, "extractors", [mock_extractor]),
            patch.object(scraper_module, "storage", mock_storage),
            patch.object(scraper_module, "rate_limiter", None),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
                return_value=[],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/scrape",
                    json={"url": "https://example.com/page", "type": "html"},
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["is_new"] is True

    @pytest.mark.asyncio
    async def test_scrape_existing_doc_not_stored_again(self, monkeypatch):
        """When storage reports the doc exists, is_new is False."""
        from httpx import ASGITransport, AsyncClient

        from projects.blog_knowledge_graph.knowledge_graph.app.models import Document

        monkeypatch.setenv("OTEL_ENABLED", "false")

        mock_extractor = MagicMock()
        mock_extractor.can_handle.return_value = True
        mock_extractor.extract = MagicMock(
            return_value=[
                Document(
                    source_type="html",
                    source_url="https://example.com/page",
                    title="Old Page",
                    author=None,
                    published_at=None,
                    content="# Old content.",
                )
            ]
        )

        mock_storage = MagicMock()
        mock_storage.exists.return_value = True  # Already stored

        with (
            patch.object(scraper_module, "extractors", [mock_extractor]),
            patch.object(scraper_module, "storage", mock_storage),
            patch.object(scraper_module, "rate_limiter", None),
            patch(
                "projects.blog_knowledge_graph.knowledge_graph.app.scraper_main.socket.getaddrinfo",
                return_value=[],
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post(
                    "/scrape",
                    json={"url": "https://example.com/page"},
                )

        data = response.json()
        assert data["results"][0]["is_new"] is False
        mock_storage.store.assert_not_called()


class TestScrapeAllEndpoint:
    """Tests for POST /scrape-all."""

    @pytest.mark.asyncio
    async def test_scrape_all_empty_sources(self, monkeypatch):
        """With no sources, scrape-all returns zero results."""
        from httpx import ASGITransport, AsyncClient

        monkeypatch.setenv("OTEL_ENABLED", "false")

        with (
            patch.object(scraper_module, "sources", []),
            patch.object(scraper_module, "notifier", None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post("/scrape-all")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["new"] == 0
        assert data["errors"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_scrape_all_returns_elapsed_seconds(self, monkeypatch):
        """Response always contains elapsed_seconds."""
        from httpx import ASGITransport, AsyncClient

        monkeypatch.setenv("OTEL_ENABLED", "false")

        with (
            patch.object(scraper_module, "sources", []),
            patch.object(scraper_module, "notifier", None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.post("/scrape-all")

        data = response.json()
        assert "elapsed_seconds" in data
        assert isinstance(data["elapsed_seconds"], (int, float))

    @pytest.mark.asyncio
    async def test_scrape_all_calls_notifier_when_set(self, monkeypatch):
        """If notifier is configured, notify_batch is called after scraping."""
        from httpx import ASGITransport, AsyncClient
        from unittest.mock import AsyncMock

        monkeypatch.setenv("OTEL_ENABLED", "false")

        mock_notifier = MagicMock()
        mock_notifier.notify_batch = AsyncMock()

        with (
            patch.object(scraper_module, "sources", []),
            patch.object(scraper_module, "notifier", mock_notifier),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                await client.post("/scrape-all")

        mock_notifier.notify_batch.assert_called_once()


class TestStatusEndpoint:
    """Tests for GET /status/{url}."""

    @pytest.mark.asyncio
    async def test_status_returns_503_when_storage_not_initialized(self):
        from httpx import ASGITransport, AsyncClient

        with patch.object(scraper_module, "storage", None):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/status/https://example.com")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_status_found_returns_metadata(self):
        from httpx import ASGITransport, AsyncClient

        meta = {
            "source_url": "https://example.com/article",
            "title": "My Article",
            "content_hash": "hash1",
        }
        mock_storage = MagicMock()
        mock_storage.list_all_hashes.return_value = ["hash1"]
        mock_storage.get_meta.return_value = meta

        with patch.object(scraper_module, "storage", mock_storage):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/status/https://example.com/article")

        assert response.status_code == 200
        data = response.json()
        assert data["scraped"] is True
        assert data["content_hash"] == "hash1"
        assert data["meta"]["title"] == "My Article"

    @pytest.mark.asyncio
    async def test_status_not_found_returns_scraped_false(self):
        from httpx import ASGITransport, AsyncClient

        mock_storage = MagicMock()
        mock_storage.list_all_hashes.return_value = ["hash1"]
        mock_storage.get_meta.return_value = {
            "source_url": "https://other-site.com",
        }

        with patch.object(scraper_module, "storage", mock_storage):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/status/https://example.com/not-here")

        assert response.status_code == 200
        assert response.json()["scraped"] is False

    @pytest.mark.asyncio
    async def test_status_empty_storage_returns_scraped_false(self):
        from httpx import ASGITransport, AsyncClient

        mock_storage = MagicMock()
        mock_storage.list_all_hashes.return_value = []

        with patch.object(scraper_module, "storage", mock_storage):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get("/status/https://example.com/article")

        assert response.json()["scraped"] is False
