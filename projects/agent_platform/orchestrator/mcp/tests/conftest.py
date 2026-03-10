"""Pytest configuration for Agent Orchestrator MCP tests."""

import pytest_asyncio  # noqa: F401 — registers the asyncio marker


def pytest_configure(config):
    """Set asyncio_mode to auto so @pytest.mark.asyncio is not needed."""
    config.option.asyncio_mode = "auto"
