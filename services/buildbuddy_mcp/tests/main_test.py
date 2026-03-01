"""Tests for BuildBuddy MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("BUILDBUDDY_API_KEY", "test-key")
    monkeypatch.setenv("BUILDBUDDY_URL", "https://test.buildbuddy.io")


@pytest.fixture
def mock_response():
    """Create a mock httpx response."""

    def _make(json_data, status_code=200):
        resp = httpx.Response(status_code, json=json_data, request=httpx.Request("POST", "https://test"))
        return resp

    return _make


class TestGetInvocation:
    @pytest.mark.asyncio
    async def test_by_invocation_id(self, mock_response):
        expected = {"invocation": [{"id": {"invocation_id": "abc-123"}, "success": True}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_invocation

            result = await get_invocation(invocation_id="abc-123")
        assert result["invocation"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_by_commit_sha(self, mock_response):
        expected = {"invocation": [{"id": {"invocation_id": "abc-123"}, "commit_sha": "deadbeef"}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_invocation

            result = await get_invocation(commit_sha="deadbeef")
        assert result["invocation"][0]["commit_sha"] == "deadbeef"


class TestGetLog:
    @pytest.mark.asyncio
    async def test_returns_log_contents(self, mock_response):
        expected = {"log": {"contents": "Building //...\nERROR: compilation failed"}}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_log

            result = await get_log(invocation_id="abc-123")
        assert "ERROR" in result["log"]["contents"]


class TestGetTarget:
    @pytest.mark.asyncio
    async def test_returns_targets(self, mock_response):
        expected = {"target": [{"label": "//pkg:test", "status": "PASSED"}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_target

            result = await get_target(invocation_id="abc-123")
        assert result["target"][0]["label"] == "//pkg:test"


class TestGetAction:
    @pytest.mark.asyncio
    async def test_returns_actions(self, mock_response):
        expected = {"action": [{"target_label": "//pkg:test", "shard": 0, "run": 1, "attempt": 1}]}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_action

            result = await get_action(invocation_id="abc-123")
        assert result["action"][0]["target_label"] == "//pkg:test"


class TestGetFile:
    @pytest.mark.asyncio
    async def test_returns_file_data(self, mock_response):
        expected = {"data": "file contents here"}

        with patch("services.buildbuddy_mcp.app.main._post", new_callable=AsyncMock, return_value=expected):
            from services.buildbuddy_mcp.app.main import get_file

            result = await get_file(uri="bytestream://example/blobs/sha256/abc/123")
        assert result["data"] == "file contents here"
