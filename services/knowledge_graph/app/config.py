"""Configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ScraperSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCRAPER_")

    port: int = 8080
    sources_yaml_path: Path = Path("/config/sources.yaml")

    # S3 / SeaweedFS
    s3_endpoint: str = "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    s3_bucket: str = "knowledge"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Rate limiting
    default_rate_limit_seconds: float = 1.0
    retry_attempts: int = 3
    retry_base_delay: float = 2.0

    # Notifications
    slack_webhook_url: str = ""
    slack_notify_mode: str = "summary_only"  # summary_only | on_new_content


class EmbedderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDER_")

    # S3
    s3_endpoint: str = "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    s3_bucket: str = "knowledge"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Qdrant
    qdrant_url: str = "http://qdrant.qdrant.svc.cluster.local:6333"
    qdrant_collection: str = "knowledge_graph"
    vector_size: int = 768

    # Embedding provider
    provider: str = "ollama"  # ollama | gemini
    ollama_url: str = "http://ollama.ollama.svc.cluster.local:11434"
    ollama_model: str = "nomic-embed-text"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-embedding-001"

    # Chunking
    chunk_max_tokens: int = 512
    chunk_min_tokens: int = 50


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_")

    port: int = 8080

    # Qdrant
    qdrant_url: str = "http://qdrant.qdrant.svc.cluster.local:6333"
    qdrant_collection: str = "knowledge_graph"

    # S3
    s3_endpoint: str = "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    s3_bucket: str = "knowledge"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Embedding (for query embedding)
    provider: str = "ollama"
    ollama_url: str = "http://ollama.ollama.svc.cluster.local:11434"
    ollama_model: str = "nomic-embed-text"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-embedding-001"
