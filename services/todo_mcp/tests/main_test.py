"""Tests for Todo MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.todo_mcp.app.main import (
    Settings,
    configure,
    get_tasks,
    set_tasks,
    reset_daily,
    reset_weekly,
)


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://todo.test:8080"))


class TestGetTasks:
    async def test_returns_full_state(self):
        expected = {
            "weekly": {"task": "Ship feature", "done": False},
            "daily": [
                {"task": "Review PR", "done": True},
                {"task": "Write tests", "done": False},
                {"task": "", "done": False},
            ],
        }

        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_req:
            result = await get_tasks()
        mock_req.assert_called_once_with("GET", "/api/todo")
        assert result["weekly"]["task"] == "Ship feature"
        assert len(result["daily"]) == 3

    async def test_http_error_returns_error_dict(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"error": "Todo API error: 500 Internal Server Error"},
        ):
            result = await get_tasks()
        assert "error" in result


class TestSetTasks:
    async def test_sends_full_state(self):
        state = {
            "weekly": {"task": "Ship feature", "done": False},
            "daily": [
                {"task": "Review PR", "done": False},
                {"task": "Write tests", "done": False},
                {"task": "", "done": False},
            ],
        }

        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await set_tasks(
                weekly_task="Ship feature",
                weekly_done=False,
                daily_1_task="Review PR",
                daily_1_done=False,
                daily_2_task="Write tests",
                daily_2_done=False,
                daily_3_task="",
                daily_3_done=False,
            )
        mock_req.assert_called_once_with("PUT", "/api/todo", json=state)
        assert result["status"] == "ok"


class TestResetDaily:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_daily()
        mock_req.assert_called_once_with("POST", "/api/reset/daily")
        assert result["status"] == "ok"


class TestResetWeekly:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            "services.todo_mcp.app.main._request",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_weekly()
        mock_req.assert_called_once_with("POST", "/api/reset/weekly")
        assert result["status"] == "ok"
