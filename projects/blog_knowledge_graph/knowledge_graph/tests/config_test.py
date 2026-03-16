"""Tests for configuration settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from projects.blog_knowledge_graph.knowledge_graph.app.config import (
    EmbedderSettings,
    McpSettings,
    ScraperSettings,
)


class TestScraperSettings:
    def test_default_port(self):
        s = ScraperSettings()
        assert s.port == 8080

    def test_default_s3_bucket(self):
        s = ScraperSettings()
        assert s.s3_bucket == "knowledge"

    def test_default_rate_limit(self):
        s = ScraperSettings()
        assert s.default_rate_limit_seconds == 1.0

    def test_default_retry_attempts(self):
        s = ScraperSettings()
        assert s.retry_attempts == 3

    def test_default_retry_base_delay(self):
        s = ScraperSettings()
        assert s.retry_base_delay == 2.0

    def test_default_slack_webhook_empty(self):
        s = ScraperSettings()
        assert s.slack_webhook_url == ""

    def test_default_slack_notify_mode(self):
        s = ScraperSettings()
        assert s.slack_notify_mode == "summary_only"

    def test_default_sources_yaml_path(self):
        s = ScraperSettings()
        assert s.sources_yaml_path == Path("/config/sources.yaml")

    def test_default_s3_credentials_empty(self):
        s = ScraperSettings()
        assert s.s3_access_key == ""
        assert s.s3_secret_key == ""

    def test_override_port(self):
        s = ScraperSettings(port=9090)
        assert s.port == 9090

    def test_override_s3_bucket(self):
        s = ScraperSettings(s3_bucket="my-bucket")
        assert s.s3_bucket == "my-bucket"

    def test_override_slack_webhook(self):
        s = ScraperSettings(slack_webhook_url="https://hooks.slack.com/test")
        assert s.slack_webhook_url == "https://hooks.slack.com/test"

    def test_override_notify_mode(self):
        s = ScraperSettings(slack_notify_mode="on_new_content")
        assert s.slack_notify_mode == "on_new_content"

    def test_override_rate_limit(self):
        s = ScraperSettings(default_rate_limit_seconds=5.0)
        assert s.default_rate_limit_seconds == 5.0

    def test_env_prefix_port(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_PORT", "9999")
        s = ScraperSettings()
        assert s.port == 9999

    def test_env_prefix_s3_bucket(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_S3_BUCKET", "env-bucket")
        s = ScraperSettings()
        assert s.s3_bucket == "env-bucket"

    def test_env_prefix_slack_webhook(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_SLACK_WEBHOOK_URL", "https://hooks.slack.com/env")
        s = ScraperSettings()
        assert s.slack_webhook_url == "https://hooks.slack.com/env"

    def test_env_prefix_rate_limit(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_DEFAULT_RATE_LIMIT_SECONDS", "3.5")
        s = ScraperSettings()
        assert s.default_rate_limit_seconds == 3.5

    def test_sources_yaml_path_is_path_type(self):
        s = ScraperSettings()
        assert isinstance(s.sources_yaml_path, Path)

    def test_override_sources_yaml_path(self, tmp_path):
        p = tmp_path / "sources.yaml"
        s = ScraperSettings(sources_yaml_path=p)
        assert s.sources_yaml_path == p


class TestEmbedderSettings:
    def test_default_provider(self):
        s = EmbedderSettings()
        assert s.provider == "ollama"

    def test_default_ollama_model(self):
        s = EmbedderSettings()
        assert s.ollama_model == "nomic-embed-text"

    def test_default_gemini_model(self):
        s = EmbedderSettings()
        assert s.gemini_model == "gemini-embedding-001"

    def test_default_vector_size(self):
        s = EmbedderSettings()
        assert s.vector_size == 768

    def test_default_chunk_max_tokens(self):
        s = EmbedderSettings()
        assert s.chunk_max_tokens == 512

    def test_default_chunk_min_tokens(self):
        s = EmbedderSettings()
        assert s.chunk_min_tokens == 50

    def test_default_qdrant_collection(self):
        s = EmbedderSettings()
        assert s.qdrant_collection == "knowledge_graph"

    def test_default_gemini_api_key_empty(self):
        s = EmbedderSettings()
        assert s.gemini_api_key == ""

    def test_default_s3_credentials_empty(self):
        s = EmbedderSettings()
        assert s.s3_access_key == ""
        assert s.s3_secret_key == ""

    def test_default_s3_bucket(self):
        s = EmbedderSettings()
        assert s.s3_bucket == "knowledge"

    def test_override_provider_gemini(self):
        s = EmbedderSettings(provider="gemini")
        assert s.provider == "gemini"

    def test_override_chunk_max_tokens(self):
        s = EmbedderSettings(chunk_max_tokens=256)
        assert s.chunk_max_tokens == 256

    def test_override_chunk_min_tokens(self):
        s = EmbedderSettings(chunk_min_tokens=25)
        assert s.chunk_min_tokens == 25

    def test_override_vector_size(self):
        s = EmbedderSettings(vector_size=1536)
        assert s.vector_size == 1536

    def test_override_qdrant_collection(self):
        s = EmbedderSettings(qdrant_collection="my_collection")
        assert s.qdrant_collection == "my_collection"

    def test_env_prefix_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_PROVIDER", "gemini")
        s = EmbedderSettings()
        assert s.provider == "gemini"

    def test_env_prefix_chunk_max_tokens(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_CHUNK_MAX_TOKENS", "1024")
        s = EmbedderSettings()
        assert s.chunk_max_tokens == 1024

    def test_env_prefix_gemini_api_key(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_GEMINI_API_KEY", "test-key-123")
        s = EmbedderSettings()
        assert s.gemini_api_key == "test-key-123"

    def test_env_prefix_vector_size(self, monkeypatch):
        monkeypatch.setenv("EMBEDDER_VECTOR_SIZE", "1536")
        s = EmbedderSettings()
        assert s.vector_size == 1536


class TestMcpSettings:
    def test_default_port(self):
        s = McpSettings()
        assert s.port == 8080

    def test_default_provider(self):
        s = McpSettings()
        assert s.provider == "ollama"

    def test_default_ollama_model(self):
        s = McpSettings()
        assert s.ollama_model == "nomic-embed-text"

    def test_default_gemini_model(self):
        s = McpSettings()
        assert s.gemini_model == "gemini-embedding-001"

    def test_default_qdrant_collection(self):
        s = McpSettings()
        assert s.qdrant_collection == "knowledge_graph"

    def test_default_s3_bucket(self):
        s = McpSettings()
        assert s.s3_bucket == "knowledge"

    def test_default_gemini_api_key_empty(self):
        s = McpSettings()
        assert s.gemini_api_key == ""

    def test_default_s3_credentials_empty(self):
        s = McpSettings()
        assert s.s3_access_key == ""
        assert s.s3_secret_key == ""

    def test_override_port(self):
        s = McpSettings(port=7070)
        assert s.port == 7070

    def test_override_provider(self):
        s = McpSettings(provider="gemini")
        assert s.provider == "gemini"

    def test_override_qdrant_collection(self):
        s = McpSettings(qdrant_collection="custom_collection")
        assert s.qdrant_collection == "custom_collection"

    def test_env_prefix_port(self, monkeypatch):
        monkeypatch.setenv("MCP_PORT", "1234")
        s = McpSettings()
        assert s.port == 1234

    def test_env_prefix_provider(self, monkeypatch):
        monkeypatch.setenv("MCP_PROVIDER", "gemini")
        s = McpSettings()
        assert s.provider == "gemini"

    def test_env_prefix_qdrant_collection(self, monkeypatch):
        monkeypatch.setenv("MCP_QDRANT_COLLECTION", "env_collection")
        s = McpSettings()
        assert s.qdrant_collection == "env_collection"
