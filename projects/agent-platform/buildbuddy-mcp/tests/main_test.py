"""Tests for BuildBuddy MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from projects.agent_platform.buildbuddy_mcp.app.main import (
    Settings,
    configure,
    execute_workflow,
    get_action,
    get_file,
    get_invocation,
    get_log,
    get_target,
    run,
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_log(invocation_id="abc-123")
        assert "ERROR" in result["log"]["contents"]

    @pytest.mark.asyncio
    async def test_errors_only_filters_to_error_lines(self):
        log_text = (
            "Loading: 0 packages loaded\n"
            "Analyzing: target //pkg:test\n"
            "INFO: Build completed\n"
            "FAIL: //pkg:test (see logs)\n"
            "ERROR: Build failed\n"
            "INFO: Streaming results\n"
            "Executed 1 out of 5 tests: 4 pass, 1 fails.\n"
        )
        api_response = {"log": {"contents": log_text}}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "FAIL:" in contents
        assert "ERROR:" in contents
        assert "Executed 1 out of 5 tests" in contents
        # Non-error lines should be excluded
        assert "Loading: 0 packages loaded" not in contents

    @pytest.mark.asyncio
    async def test_errors_only_paginates(self):
        page1 = {
            "log": {"contents": "INFO: ok\nERROR: bad\n"},
            "next_page_token": "p2",
        }
        page2 = {
            "log": {"contents": "FAIL: //test\nExecuted 1 out of 2 tests: 1 fails.\n"},
        }

        call_count = 0

        async def mock_post(endpoint, body):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "ERROR: bad" in contents
        assert "FAIL: //test" in contents

    @pytest.mark.asyncio
    async def test_errors_only_strips_ansi(self):
        log_text = "\x1b[31mERROR:\x1b[0m Build failed\n"
        api_response = {"log": {"contents": log_text}}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=api_response,
        ):
            result = await get_log(invocation_id="abc-123", errors_only=True)
        contents = result["log"]["contents"]
        assert "\x1b[" not in contents
        assert "ERROR:" in contents


class TestGetTarget:
    @pytest.mark.asyncio
    async def test_returns_targets(self):
        expected = {"target": [{"label": "//pkg:test", "status": "PASSED"}]}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await execute_workflow(
                repo_url="https://github.com/jomcgi/homelab",
                branch="main",
            )
        assert result["action_statuses"][0]["action_name"] == "Test and push"

    @pytest.mark.asyncio
    async def test_passes_env_and_visibility(self):
        expected = {
            "action_statuses": [{"action_name": "Test", "invocation_id": "inv-1"}]
        }

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            await execute_workflow(
                repo_url="https://github.com/jomcgi/homelab",
                branch="main",
                env={"FOO": "bar"},
                visibility="PUBLIC",
                disable_retry=True,
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["env"] == {"FOO": "bar"}
        assert call_body["visibility"] == "PUBLIC"
        assert call_body["disable_retry"] is True


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_returns_error_dict(self):
        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._client",
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
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await get_invocation(invocation_id="abc-123")
        assert result == {}


class TestRun:
    @pytest.mark.asyncio
    async def test_sends_steps_as_run_dicts(self):
        expected = {"invocation_id": "run-inv-1"}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_post:
            result = await run(
                repo_url="https://github.com/jomcgi/homelab",
                steps=["bazel test //pkg:test", "echo done"],
                branch="main",
                timeout="15m",
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["steps"] == [
            {"run": "bazel test //pkg:test"},
            {"run": "echo done"},
        ]
        assert call_body["repo"] == "https://github.com/jomcgi/homelab"
        assert call_body["branch"] == "main"
        assert call_body["timeout"] == "15m"
        assert result["invocation_id"] == "run-inv-1"

    @pytest.mark.asyncio
    async def test_passes_env_and_wait_until(self):
        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            new_callable=AsyncMock,
            return_value={"invocation_id": "x"},
        ) as mock_post:
            await run(
                repo_url="https://github.com/jomcgi/homelab",
                steps=["echo hi"],
                env={"KEY": "val"},
                wait_until="STARTED",
            )
        call_body = mock_post.call_args[0][1]
        assert call_body["env"] == {"KEY": "val"}
        assert call_body["wait_until"] == "STARTED"
