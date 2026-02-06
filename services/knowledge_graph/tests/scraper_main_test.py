"""Tests for scraper FastAPI application."""

import pytest
import yaml

from services.knowledge_graph.app.scraper_main import _load_sources, app


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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
