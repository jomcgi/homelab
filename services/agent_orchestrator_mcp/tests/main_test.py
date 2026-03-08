"""Tests for Agent Orchestrator MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.agent_orchestrator_mcp.app.main import (
    Settings,
    configure,
    submit_job,
    list_jobs,
)

_PATCH = "services.agent_orchestrator_mcp.app.main._request"


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://orchestrator.test:8080"))


class TestSubmitJob:
    async def test_submits_with_task_only(self):
        expected = {"id": "01ABC", "status": "PENDING", "created_at": "2026-03-07T00:00:00Z"}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await submit_job(task="Fix the auth bug")
        mock_req.assert_called_once_with("POST", "/jobs", json={"task": "Fix the auth bug"})
        assert result["id"] == "01ABC"
        assert result["status"] == "PENDING"

    async def test_submits_with_all_params(self):
        expected = {"id": "01ABC", "status": "PENDING", "created_at": "2026-03-07T00:00:00Z"}
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
            json={"task": "Debug CI", "profile": "ci-debug", "max_retries": 3, "source": "github"},
        )
        assert result["status"] == "PENDING"

    async def test_http_error_returns_error_dict(self):
        with patch(_PATCH, new_callable=AsyncMock, return_value={"error": "API error: 500"}):
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
        mock_req.assert_called_once_with("GET", "/jobs", params={"status": "RUNNING,PENDING"})
        assert result["total"] == 0

    async def test_lists_with_pagination(self):
        expected = {"jobs": [], "total": 50}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(limit=10, offset=20)
        mock_req.assert_called_once_with("GET", "/jobs", params={"limit": "10", "offset": "20"})
        assert result["total"] == 50

    async def test_lists_with_all_params(self):
        expected = {"jobs": [], "total": 0}
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected) as mock_req:
            result = await list_jobs(status="FAILED", limit=5, offset=0)
        mock_req.assert_called_once_with(
            "GET", "/jobs", params={"status": "FAILED", "limit": "5", "offset": "0"}
        )
