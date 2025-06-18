from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObsidianSettings(BaseSettings):
    """Configuration settings for the Obsidian MCP server."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    repo_url: str = Field(
        ..., 
        alias="OBSIDIAN_REPO_URL",
        description="GitHub repository URL (e.g., 'username/repo-name')"
    )
    
    github_token: Optional[str] = Field(
        None,
        alias="GITHUB_TOKEN", 
        description="GitHub personal access token (optional for public repos)"
    )
    
    branch: str = Field(
        "main",
        alias="OBSIDIAN_BRANCH",
        description="Git branch to use"
    )
    
    path_prefix: str = Field(
        "",
        alias="OBSIDIAN_PATH_PREFIX",
        description="Path prefix within the repository (e.g., 'docs/')"
    )