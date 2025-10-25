"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Obsidian API settings
    obsidian_api_url: str = "http://127.0.0.1:27123"
    obsidian_api_key: str

    # Service settings
    service_host: str = "0.0.0.0"
    service_port: int = 8080
    log_level: str = "INFO"

    # OpenTelemetry settings
    otel_enabled: bool = True
    otel_service_name: str = "n8n-obsidian-api"
    otel_exporter_otlp_endpoint: str = ""  # e.g., "http://signoz:4317"

    # Security
    api_key: str = ""  # Optional API key for securing this service


settings = Settings()
