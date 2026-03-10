"""Tests for BuildBuddy MCP composite tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from projects.agent_platform.buildbuddy_mcp.app.main import Settings, configure


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(api_key="test-key", url="https://test.buildbuddy.io"))


class TestDiagnoseFailure:
    @pytest.mark.asyncio
    async def test_returns_failed_targets_with_logs(self):
        import base64

        from projects.agent_platform.buildbuddy_mcp.app.composite import (
            diagnose_failure,
        )

        test_log_b64 = base64.b64encode(b"FAIL: assertion error").decode()

        async def mock_post(endpoint, body):
            if endpoint == "/GetInvocation":
                return {
                    "invocation": [
                        {
                            "id": {"invocation_id": "wf-1"},
                            "command": "workflow run",
                            "success": False,
                            "child_invocations": [
                                {"invocation_id": "test-inv-1"},
                            ],
                        }
                    ]
                }
            if endpoint == "/GetTarget":
                return {
                    "target": [
                        {
                            "label": "//pkg:test",
                            "status": "FAILED",
                            "timing": {"duration": "1.2s"},
                        },
                    ]
                }
            if endpoint == "/GetAction":
                return {
                    "action": [
                        {
                            "target_label": "//pkg:test",
                            "file": [
                                {
                                    "name": "test.log",
                                    "uri": "bytestream://x/blobs/abc/100",
                                },
                            ],
                        }
                    ]
                }
            if endpoint == "/GetFile":
                return {"data": test_log_b64}
            if endpoint == "/GetLog":
                return {
                    "log": {
                        "contents": "ERROR: //pkg:test failed\nExecuted 1 out of 1 tests: 0 pass, 1 fails.\n"
                    }
                }
            return {}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await diagnose_failure(invocation_id="wf-1")

        assert result["status"] == "FAILED"
        assert len(result["failed_targets"]) == 1
        assert result["failed_targets"][0]["label"] == "//pkg:test"
        assert "assertion error" in result["failed_targets"][0]["test_log"]
        assert "build_errors" in result

    @pytest.mark.asyncio
    async def test_returns_success_when_no_failures(self):
        from projects.agent_platform.buildbuddy_mcp.app.composite import (
            diagnose_failure,
        )

        async def mock_post(endpoint, body):
            if endpoint == "/GetInvocation":
                return {
                    "invocation": [
                        {
                            "id": {"invocation_id": "wf-1"},
                            "command": "workflow run",
                            "success": True,
                            "child_invocations": [
                                {"invocation_id": "test-inv-1"},
                            ],
                        }
                    ]
                }
            if endpoint == "/GetTarget":
                return {
                    "target": [
                        {"label": "//pkg:test", "status": "PASSED"},
                    ]
                }
            if endpoint == "/GetLog":
                return {"log": {"contents": "Executed 1 out of 1 tests: 1 pass.\n"}}
            return {}

        with patch(
            "projects.agent_platform.buildbuddy_mcp.app.main._post",
            side_effect=mock_post,
        ):
            result = await diagnose_failure(invocation_id="wf-1")

        assert result["status"] == "SUCCESS"
        assert result["failed_targets"] == []
