"""Stargazer configuration using pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BoundsConfig(BaseSettings):
    """Geographic bounds for the target region (Scotland)."""

    model_config = SettingsConfigDict(env_prefix="BOUNDS_")

    north: float = 60.86  # Shetland
    south: float = 54.63  # Scottish Borders
    west: float = -8.65  # Outer Hebrides
    east: float = -0.76  # Aberdeenshire coast


class EuropeBoundsConfig(BaseSettings):
    """Geographic bounds for the Europe LP atlas image."""

    model_config = SettingsConfigDict(env_prefix="EUROPE_BOUNDS_")

    north: float = 75.0
    south: float = 34.0
    west: float = -32.0
    east: float = 70.0


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    # Paths
    data_dir: Path = Field(default=Path("/data"))

    # Bounds
    bounds: BoundsConfig = Field(default_factory=BoundsConfig)
    europe_bounds: EuropeBoundsConfig = Field(default_factory=EuropeBoundsConfig)

    # Light pollution zones where LPI < 1.0 (natural sky dominates)
    acceptable_zones: list[str] = Field(
        default=["0", "1a", "1b", "2a", "2b", "3a", "3b"]
    )

    # Processing parameters
    color_tolerance: int = 15  # RGB matching tolerance for zone classification
    road_buffer_m: int = 1000  # Accessibility radius from roads
    grid_spacing_m: int = 5000  # Sample point density (5km)
    min_astronomy_score: int = 60  # Weather score threshold

    # Forecast settings
    forecast_hours: int = 72  # Look ahead window

    # MET Norway API settings
    met_norway_user_agent: str = "stargazer/1.0 github.com/jomcgi/homelab"
    met_norway_rate_limit: int = 15  # requests per second (safe limit)
    cache_ttl_hours: int = 1  # Honor API caching

    # Data source URLs (DJ Lorenz 2024 Light Pollution Atlas)
    lp_source_url: str = "https://djlorenz.github.io/astronomy/lp2024/Europe2024.png"
    colorbar_url: str = "https://djlorenz.github.io/astronomy/lp/colorbar.png"
    osm_source_url: str = (
        "https://download.geofabrik.de/europe/united-kingdom/scotland-latest.osm.pbf"
    )

    # OpenTelemetry settings (auto-injected by Kyverno in cluster)
    otel_enabled: bool = True
    otel_service_name: str = "stargazer"
    otel_exporter_otlp_endpoint: str = ""  # e.g., "http://signoz:4317"

    @property
    def raw_dir(self) -> Path:
        """Directory for raw downloaded data."""
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        """Directory for processed intermediate data."""
        return self.data_dir / "processed"

    @property
    def cache_dir(self) -> Path:
        """Directory for API response cache."""
        return self.data_dir / "cache"

    @property
    def output_dir(self) -> Path:
        """Directory for final output files."""
        return self.data_dir / "output"
