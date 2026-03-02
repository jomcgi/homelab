"""Tests for BuildBuddy MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.buildbuddy_mcp.app.main import (
    Settings,
    configure,
    execute_workflow,
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
)


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(api_key="test-key", url="https://test.buildbuddy.io"))


class TestGetInvocation:
    @pytest.mark.asyncio
    async def test_by_invocation_id(self):
        expected = {
            "invocation": [{"id": {"invocation_id": "abc-123"}, "success": True}]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_invocation(invocation_id="abc-123")
        assert result["invocation"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_by_commit_sha(self):
        expected = {
            "invocation": [
                {"id": {"invocation_id": "abc-123"}, "commit_sha": "deadbeef"}
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_invocation(commit_sha="deadbeef")
        assert result["invocation"][0]["commit_sha"] == "deadbeef"


class TestGetLog:
    @pytest.mark.asyncio
    async def test_returns_log_contents(self):
        expected = {"log": {"contents": "Building //...\nERROR: compilation failed"}}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_log(invocation_id="abc-123")
        assert "ERROR" in result["log"]["contents"]


class TestGetTarget:
    @pytest.mark.asyncio
    async def test_returns_targets(self):
        expected = {"target": [{"label": "//pkg:test", "status": "PASSED"}]}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_target(invocation_id="abc-123")
        assert result["target"][0]["label"] == "//pkg:test"


class TestGetAction:
    @pytest.mark.asyncio
    async def test_returns_actions(self):
        expected = {
            "action": [
                {"target_label": "//pkg:test", "shard": 0, "run": 1, "attempt": 1}
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_action(invocation_id="abc-123")
        assert result["action"][0]["target_label"] == "//pkg:test"


class TestGetFile:
    @pytest.mark.asyncio
    async def test_returns_file_data(self):
        expected = {"data": "file contents here"}

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_file(uri="bytestream://example/blobs/sha256/abc/123")
        assert result["data"] == "file contents here"


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_triggers_workflow(self):
        expected = {
            "action_statuses": [
                {"action_name": "Test and push", "invocation_id": "new-inv-123"}
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await execute_workflow(
                repo_url="https://github.com/jomcgi/homelab",
                branch="main",
            )
        assert result["action_statuses"][0]["action_name"] == "Test and push"


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_returns_error_dict(self):
        with patch(
            "services.buildbuddy_mcp.app.main._client",
        ) as mock_client:
            mock_resp = AsyncMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_resp.is_success = False
            mock_client.post = AsyncMock(return_value=mock_resp)

            result = await get_invocation(invocation_id="nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_response_returns_error_dict(self):
        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await get_invocation(invocation_id="abc-123")
        assert result == {}
