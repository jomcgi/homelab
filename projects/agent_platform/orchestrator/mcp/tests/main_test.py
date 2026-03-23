"""Tests for Agent Orchestrator MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

import projects.agent_platform.orchestrator.mcp.app.main as _mod
from projects.agent_platform.orchestrator.mcp.app.main import (
    Settings,
    _request,
    cancel_job,
    configure,
    get_job,
    get_job_output,
    list_jobs,
    submit_job,
)

_PATCH = "projects.agent_platform.orchestrator.mcp.app.main._request"


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://orchestrator.test:8080"))


class TestSettings:
    def test_default_port(self):
        s = Settings(url="http://orchestrator.test:8080")
        assert s.port == 8000

    def test_custom_port(self):
        s = Settings(url="http://orchestrator.test:8080", port=9090)
        assert s.port == 9090

    def test_requires_url(self):
        with pytest.raises(ValidationError):
            Settings()

    def test_env_prefix(self):
        assert Settings.model_config["env_prefix"] == "ORCHESTRATOR_"

    def test_reads_url_from_env(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://env-orch.test:1234")
        monkeypatch.delenv("ORCHESTRATOR_PORT", raising=False)
        s = Settings()
        assert s.url == "http://env-orch.test:1234"
        assert s.port == 8000

    def test_reads_port_from_env(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://env-orch.test")
        monkeypatch.setenv("ORCHESTRATOR_PORT", "9999")
        s = Settings()
        assert s.port == 9999


class TestConfigure:
    def test_sets_async_client(self):
        settings = Settings(url="http://orchestrator.test:8080")
        configure(settings)
        assert isinstance(_mod._client, httpx.AsyncClient)

    def test_client_uses_base_url(self):
        settings = Settings(url="http://orch.example.com:9000")
        configure(settings)
        assert str(_mod._client.base_url) == "http://orch.example.com:9000"

    def test_replaces_existing_client(self):
        configure(Settings(url="http://first.test"))
        first = _mod._client
        configure(Settings(url="http://second.test"))
        assert _mod._client is not first

    def test_client_timeout_is_30_seconds(self):
        """httpx.AsyncClient must be constructed with timeout=30.0."""
        settings = Settings(url="http://orchestrator.test:8080")
        with patch(
            "projects.agent_platform.orchestrator.mcp.app.main.httpx.AsyncClient"
        ) as mock_cls:
            configure(settings)
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs.get("timeout") == 30.0


class TestRequest:
    async def test_success_returns_json(self):
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {"id": "01ABC", "status": "PENDING"}
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("GET", "/jobs/01ABC")
        assert result == {"id": "01ABC", "status": "PENDING"}

    async def test_http_error_returns_error_dict(self):
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("GET", "/jobs")
        assert "error" in result
        assert "500" in result["error"]

    async def test_http_404_returns_error_dict(self):
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("GET", "/jobs/missing")
        assert "error" in result
        assert "404" in result["error"]

    async def test_exception_returns_error_dict(self):
        with patch.object(
            _mod._client,
            "request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await _request("GET", "/jobs")
        assert "error" in result
        assert "Connection refused" in result["error"]

    async def test_passes_kwargs_to_client(self):
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {}
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await _request("POST", "/jobs", json={"task": "test"})
        mock_req.assert_called_once_with("POST", "/jobs", json={"task": "test"})

    async def test_exception_calls_logger_warning(self):
        """logger.warning must be called when the underlying request raises."""
        with patch.object(
            _mod._client,
            "request",
            new_callable=AsyncMock,
            side_effect=Exception("network failure"),
        ):
            with patch.object(_mod.logger, "warning") as mock_warn:
                result = await _request("GET", "/jobs")
        mock_warn.assert_called_once()
        assert "Orchestrator API request failed" in mock_warn.call_args[0][0]
        assert "error" in result


class TestSubmitJob:
    async def test_submits_with_task_only(self):
        expected = {
            "id": "01ABC",
            "status": "PENDING",
            "created_at": "2026-03-07T00:00:00Z",
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await submit_job(task="Fix the auth bug")
        mock_req.assert_called_once_with(
            "POST", "/jobs", json={"task": "Fix the auth bug"}
        )
        assert result["id"] == "01ABC"
        assert result["status"] == "PENDING"

    async def test_submits_with_all_params(self):
        expected = {
            "id": "01ABC",
            "status": "PENDING",
            "created_at": "2026-03-07T00:00:00Z",
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await submit_job(
                task="Debug CI",
                profile="ci-debug",
                max_retries=3,
                source="github",
            )
        mock_req.assert_called_once_with(
            "POST",
            "/jobs",
            json={
                "task": "Debug CI",
                "profile": "ci-debug",
                "max_retries": 3,
                "source": "github",
            },
        )
        assert result["status"] == "PENDING"

    async def test_max_retries_zero_is_included(self):
        """max_retries=0 is not None and must be included in the request body."""
        expected = {
            "id": "01ABC",
            "status": "PENDING",
            "created_at": "2026-03-07T00:00:00Z",
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            await submit_job(task="No retries", max_retries=0)
        body = mock_req.call_args[1]["json"]
        assert "max_retries" in body
        assert body["max_retries"] == 0

    async def test_none_optional_params_excluded(self):
        """None optional params must not appear in the JSON body."""
        expected = {
            "id": "01ABC",
            "status": "PENDING",
            "created_at": "2026-03-07T00:00:00Z",
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            await submit_job(task="Only task")
        body = mock_req.call_args[1]["json"]
        assert list(body.keys()) == ["task"]

    async def test_source_only_optional_param(self):
        """source alone (without profile/max_retries) must be included in body."""
        expected = {
            "id": "01ABC",
            "status": "PENDING",
            "created_at": "2026-03-07T00:00:00Z",
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            await submit_job(task="From CLI", source="cli")
        body = mock_req.call_args[1]["json"]
        assert body == {"task": "From CLI", "source": "cli"}

    async def test_http_error_returns_error_dict(self):
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"error": "API error: 500"}
        ):
            result = await submit_job(task="Fail")
        assert "error" in result


class TestListJobs:
    async def test_lists_without_filters(self):
        expected = {"jobs": [{"id": "01ABC"}], "total": 1}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs()
        mock_req.assert_called_once_with("GET", "/jobs", params={})
        assert result["total"] == 1

    async def test_lists_with_status_filter(self):
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(status="RUNNING,PENDING")
        mock_req.assert_called_once_with(
            "GET", "/jobs", params={"status": "RUNNING,PENDING"}
        )
        assert result["total"] == 0

    async def test_lists_with_pagination(self):
        expected = {"jobs": [], "total": 50}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(limit=10, offset=20)
        mock_req.assert_called_once_with(
            "GET", "/jobs", params={"limit": "10", "offset": "20"}
        )
        assert result["total"] == 50

    async def test_lists_with_all_params(self):
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(status="FAILED", limit=5, offset=0)
        mock_req.assert_called_once_with(
            "GET", "/jobs", params={"status": "FAILED", "limit": "5", "offset": "0"}
        )

    async def test_limit_and_offset_converted_to_strings(self):
        """Numeric limit/offset must be sent as strings in query params."""
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            await list_jobs(limit=100, offset=50)
        params = mock_req.call_args[1]["params"]
        assert params["limit"] == "100"
        assert params["offset"] == "50"

    async def test_error_propagated(self):
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"error": "API error: 503"}
        ):
            result = await list_jobs()
        assert "error" in result


class TestGetJob:
    async def test_returns_job_record(self):
        expected = {
            "id": "01ABC",
            "task": "Fix bug",
            "status": "RUNNING",
            "attempts": [{"number": 1, "exit_code": None}],
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await get_job(job_id="01ABC")
        mock_req.assert_called_once_with("GET", "/jobs/01ABC")
        assert result["id"] == "01ABC"
        assert result["status"] == "RUNNING"

    async def test_includes_attempts(self):
        expected = {
            "id": "01ABC",
            "status": "SUCCEEDED",
            "attempts": [{"number": 1, "exit_code": 0}, {"number": 2, "exit_code": 0}],
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected):
            result = await get_job(job_id="01ABC")
        assert len(result["attempts"]) == 2

    async def test_not_found_returns_error(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Orchestrator API error: 404"},
        ):
            result = await get_job(job_id="NONEXISTENT")
        assert "error" in result


class TestCancelJob:
    async def test_cancels_running_job(self):
        expected = {"id": "01ABC", "status": "CANCELLED"}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await cancel_job(job_id="01ABC")
        mock_req.assert_called_once_with("POST", "/jobs/01ABC/cancel")
        assert result["status"] == "CANCELLED"

    async def test_conflict_returns_error(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Orchestrator API error: 409"},
        ):
            result = await cancel_job(job_id="01ABC")
        assert "error" in result

    async def test_uses_post_method(self):
        """Cancel must use POST (not DELETE or PATCH)."""
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"status": "CANCELLED"}
        ) as mock_req:
            await cancel_job(job_id="XYZ")
        assert mock_req.call_args[0][0] == "POST"


class TestGetJobOutput:
    async def test_returns_output(self):
        expected = {"attempt": 1, "exit_code": 0, "output": "Done!", "truncated": False}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await get_job_output(job_id="01ABC")
        mock_req.assert_called_once_with("GET", "/jobs/01ABC/output")
        assert result["output"] == "Done!"
        assert result["truncated"] is False

    async def test_truncated_flag_true(self):
        """Large outputs have truncated=True to signal 32KB trim."""
        expected = {
            "attempt": 1,
            "exit_code": 1,
            "output": "A" * 100,
            "truncated": True,
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected):
            result = await get_job_output(job_id="01ABC")
        assert result["truncated"] is True

    async def test_no_output_returns_error(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Orchestrator API error: 404"},
        ):
            result = await get_job_output(job_id="01ABC")
        assert "error" in result


class TestMain:
    def test_configures_and_runs(self, monkeypatch):
        """main() must configure the HTTP client and start the MCP server."""
        monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator.test:8080")
        monkeypatch.delenv("ORCHESTRATOR_PORT", raising=False)

        mock_app = MagicMock()
        with (
            patch.object(_mod.mcp, "http_app", return_value=mock_app) as mock_http_app,
            patch("uvicorn.run") as mock_uvicorn,
        ):
            from projects.agent_platform.orchestrator.mcp.app.main import main

            main()

        mock_http_app.assert_called_once()
        mock_app.add_route.assert_called_once()
        route_path = mock_app.add_route.call_args[0][0]
        assert route_path == "/healthz"
        mock_uvicorn.assert_called_once_with(mock_app, host="0.0.0.0", port=8000)
        assert _mod._client is not None
