"""Tests for scraper FastAPI application."""

import pytest
import yaml

from knowledge_graph.app.scraper_main import (
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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
