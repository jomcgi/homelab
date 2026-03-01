"""BuildBuddy MCP server."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUILDBUDDY_")

    api_key: str
    url: str
    port: int = 8000


mcp = FastMCP("BuildBuddy")


def main():
    settings = Settings()
    mcp.run(transport="http", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
