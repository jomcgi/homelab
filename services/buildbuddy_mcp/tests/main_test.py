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

    @pytest.mark.asyncio
    async def test_include_child_invocations(self):
        expected = {
            "invocation": [
                {
                    "id": {"invocation_id": "workflow-1"},
                    "child_invocations": [
                        {"invocation_id": "child-1"},
                        {"invocation_id": "child-2"},
                    ],
                }
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            result = await get_invocation(
                invocation_id="workflow-1",
                include_child_invocations=True,
            )
        # Verify the include flag was passed as a top-level request field
        call_body = mock_post.call_args[0][1]
        assert call_body["include_child_invocations"] is True
        assert len(result["invocation"][0]["child_invocations"]) == 2


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

    @pytest.mark.asyncio
    async def test_status_filter_returns_only_matching(self):
        api_response = {
            "target": [
                {"label": "//pkg:build", "status": "BUILT"},
                {"label": "//pkg:test_a", "status": "PASSED"},
                {"label": "//pkg:test_b", "status": "FAILED"},
                {"label": "//pkg:test_c", "status": "FAILED"},
            ]
        }

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_target(invocation_id="abc-123", status="FAILED")
        assert len(result["target"]) == 2
        assert all(t["status"] == "FAILED" for t in result["target"])

    @pytest.mark.asyncio
    async def test_status_filter_with_pagination(self):
        page1 = {
            "target": [{"label": "//a:t", "status": "PASSED"}],
            "next_page_token": "page2",
        }
        page2 = {
            "target": [{"label": "//b:t", "status": "FAILED"}],
        }

        call_count = 0

        async def mock_post(endpoint, body):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await get_target(invocation_id="abc-123", status="FAILED")
        assert len(result["target"]) == 1
        assert result["target"][0]["label"] == "//b:t"


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
    async def test_decodes_base64_text(self):
        import base64

        text = "PASS: //pkg:test\nRan 1 test in 0.5s"
        b64 = base64.b64encode(text.encode()).decode()

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"data": b64},
        ):
            result = await get_file(uri="bytestream://example/blobs/abc/123")
        assert result["contents"] == text

    @pytest.mark.asyncio
    async def test_binary_file_returns_error(self):
        import base64

        binary_data = bytes(range(256))
        b64 = base64.b64encode(binary_data).decode()

        with patch(
            "services.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"data": b64},
        ):
            result = await get_file(uri="bytestream://example/blobs/abc/256")
        assert "error" in result
        assert result["size_bytes"] == 256


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
