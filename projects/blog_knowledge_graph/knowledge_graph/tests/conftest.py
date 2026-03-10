"""Shared fixtures for knowledge graph tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.config import (
    EmbedderSettings,
    McpSettings,
    ScraperSettings,
)
from projects.blog_knowledge_graph.knowledge_graph.app.models import Document


@pytest.fixture
def scraper_settings(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        "sources:\n"
        '  - url: "https://example.com/feed.xml"\n'
        '    type: "rss"\n'
        '    name: "Test Feed"\n'
        '  - url: "https://example.com/article"\n'
        '    type: "html"\n'
    )
    return ScraperSettings(
        sources_yaml_path=sources_yaml,
        s3_endpoint="http://localhost:8333",
        s3_bucket="test-bucket",
        slack_webhook_url="",
    )


@pytest.fixture
def embedder_settings():
    return EmbedderSettings(
        s3_endpoint="http://localhost:8333",
        s3_bucket="test-bucket",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection",
        provider="ollama",
        ollama_url="http://localhost:11434",
    )


@pytest.fixture
def mcp_settings():
    return McpSettings(
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection",
        s3_endpoint="http://localhost:8333",
        s3_bucket="test-bucket",
        provider="ollama",
        ollama_url="http://localhost:11434",
    )


@pytest.fixture
def sample_document():
    return Document(
        source_type="html",
        source_url="https://example.com/article",
        title="Test Article",
        author="Test Author",
        published_at=datetime(2025, 1, 15),
        content="# Test\n\nSome content here.\n\n## Section Two\n\nMore content.",
    )


@pytest.fixture
def sample_rss_document():
    return Document(
        source_type="rss",
        source_url="https://blog.example.com/post-1",
        title="Blog Post One",
        author="Blog Author",
        published_at=datetime(2025, 2, 1),
        content="# Blog Post\n\nThis is a blog post from an RSS feed.\n\n## Details\n\nSome details here.",
    )


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.exists.return_value = False
    storage.store.return_value = "abc123hash"
    storage.get_content.return_value = "# Test\n\nContent here."
    storage.get_meta.return_value = {
        "source_type": "html",
        "source_url": "https://example.com/article",
        "title": "Test Article",
        "author": "Test Author",
        "published_at": "2025-01-15T00:00:00",
        "content_hash": "abc123hash",
    }
    storage.list_all_hashes.return_value = ["abc123hash", "def456hash"]
    return storage
