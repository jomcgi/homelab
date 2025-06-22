"""
Configuration management for the find_good_hikes project.

This module provides centralized configuration with sensible defaults
and environment variable overrides using Pydantic BaseSettings.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    """Database configuration settings."""
    walks_db_path: str = Field(default="walks.db", env="WALKS_DB_PATH")
    forecasts_db_path: str = Field(default="forecasts.sqlite.db", env="FORECASTS_DB_PATH")
    
    class Config:
        env_prefix = "DB_"
        case_sensitive = False

class CacheConfig(BaseSettings):
    """Cache configuration settings."""
    walkhighlands_cache_name: str = Field(default="walkhighlands_cache", env="WALKHIGHLANDS_CACHE_NAME")
    weather_cache_name: str = Field(default="met_weather_cache", env="WEATHER_CACHE_NAME")
    weather_cache_expire_hours: int = Field(default=1, env="WEATHER_CACHE_EXPIRE_HOURS", ge=1, le=168)  # 1 hour to 1 week
    
    class Config:
        env_prefix = "CACHE_"
        case_sensitive = False

class ScrapingConfig(BaseSettings):
    """Web scraping configuration settings."""
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        env="USER_AGENT"
    )
    request_timeout: int = Field(default=15, env="REQUEST_TIMEOUT", ge=5, le=300)  # 5 seconds to 5 minutes
    base_url: str = Field(default="https://www.walkhighlands.co.uk/", env="WALKHIGHLANDS_BASE_URL")
    
    class Config:
        env_prefix = "SCRAPING_"
        case_sensitive = False

class WeatherConfig(BaseSettings):
    """Weather API configuration settings."""
    api_user_agent: str = Field(
        default="find-good-hikes/1.0 (https://github.com/user/find-good-hikes)",
        env="WEATHER_API_USER_AGENT"
    )
    api_base_url: str = Field(
        default="https://api.met.no/weatherapi/locationforecast/2.0/compact",
        env="WEATHER_API_BASE_URL"
    )
    coordinate_precision: int = Field(default=4, env="COORDINATE_PRECISION", ge=1, le=10)  # 1-10 decimal places
    
    class Config:
        env_prefix = "WEATHER_"
        case_sensitive = False

class LoggingConfig(BaseSettings):
    """Logging configuration settings."""
    level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    
    class Config:
        env_prefix = "LOG_"
        case_sensitive = False
        
    @validator('level')
    def validate_level(cls, v):
        """Validate logging level is valid."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in valid_levels:
            raise ValueError(f'Invalid log level: {v}. Must be one of {valid_levels}')
        return v.upper()

class AppConfig(BaseSettings):
    """Main application configuration."""
    # Default search parameters
    default_search_radius_km: float = Field(default=25.0, env="DEFAULT_SEARCH_RADIUS_KM", ge=1.0, le=1000.0)
    default_hours_ahead: int = Field(default=48, env="DEFAULT_HOURS_AHEAD", ge=1, le=168)  # 1 hour to 1 week
    
    # Data directory
    data_dir: str = Field(default=".", env="DATA_DIR")
    
    class Config:
        env_prefix = "APP_"
        case_sensitive = False

def get_config() -> AppConfig:
    """Get the application configuration."""
    return AppConfig()

def get_database_config() -> DatabaseConfig:
    """Get database configuration."""
    return DatabaseConfig()

def get_cache_config() -> CacheConfig:
    """Get cache configuration."""
    return CacheConfig()

def get_scraping_config() -> ScrapingConfig:
    """Get scraping configuration."""
    return ScrapingConfig()

def get_weather_config() -> WeatherConfig:
    """Get weather configuration."""
    return WeatherConfig()

def get_logging_config() -> LoggingConfig:
    """Get logging configuration."""
    return LoggingConfig()

def get_data_dir() -> Path:
    """Get the directory for storing data files."""
    config = get_config()
    data_dir = Path(config.data_dir).resolve()
    data_dir.mkdir(exist_ok=True)
    return data_dir

def get_db_path(filename: str) -> str:
    """Get the full path for a database file."""
    return str(get_data_dir() / filename)

# Convenience function to get all configs at once
def get_all_configs() -> tuple[AppConfig, DatabaseConfig, CacheConfig, ScrapingConfig, WeatherConfig, LoggingConfig]:
    """Get all configuration objects."""
    return (
        get_config(),
        get_database_config(),
        get_cache_config(),
        get_scraping_config(),
        get_weather_config(),
        get_logging_config()
    )