"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Obsidian API settings (via Cloudflare Tunnel)
    obsidian_api_url: str = "https://obsidian.jomcgi.dev"

    # Cloudflare service token for bypassing Access
    # (Cloudflare Access injects Obsidian API credentials automatically)
    cloudflare_client_id: str
    cloudflare_client_secret: str

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


# Settings loaded from environment variables
# pyright doesn't understand that pydantic-settings loads from env
settings = Settings()  # type: ignore[call-arg]
