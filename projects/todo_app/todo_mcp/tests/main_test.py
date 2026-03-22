"""Tests for Todo MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

import projects.todo_app.todo_mcp.app.main as _mod
from projects.todo_app.todo_mcp.app.main import (
    Settings,
    _request,
    configure,
    get_tasks,
    reset_daily,
    reset_weekly,
    set_tasks,
)

_PATCH = "projects.todo_app.todo_mcp.app.main._request"


@pytest.fixture(autouse=True)
def _configure_client():
    configure(Settings(url="http://todo.test:8080"))


class TestSettings:
    def test_default_port(self):
        s = Settings(url="http://todo.test:8080")
        assert s.port == 8000

    def test_custom_port(self):
        s = Settings(url="http://todo.test:8080", port=9090)
        assert s.port == 9090

    def test_requires_url(self):
        with pytest.raises(ValidationError):
            Settings()

    def test_env_prefix(self):
        assert Settings.model_config["env_prefix"] == "TODO_"

    def test_url_from_env_var(self, monkeypatch):
        """TODO_URL env var should be read when Settings() is instantiated without
        an explicit url argument, confirming the env_prefix is actually applied."""
        monkeypatch.setenv("TODO_URL", "http://from-env.test:9000")
        monkeypatch.delenv("TODO_PORT", raising=False)
        s = Settings()
        assert s.url == "http://from-env.test:9000"

    def test_port_from_env_var(self, monkeypatch):
        """TODO_PORT env var should override the default port (8000) when
        Settings() is instantiated without an explicit port argument."""
        monkeypatch.setenv("TODO_URL", "http://test.local:8080")
        monkeypatch.setenv("TODO_PORT", "7777")
        s = Settings()
        assert s.port == 7777


class TestConfigure:
    def test_sets_async_client(self):
        settings = Settings(url="http://todo.test:8080")
        configure(settings)
        assert isinstance(_mod._client, httpx.AsyncClient)

    def test_client_uses_base_url(self):
        settings = Settings(url="http://todo.example.com:9000")
        configure(settings)
        assert str(_mod._client.base_url) == "http://todo.example.com:9000"

    def test_replaces_existing_client(self):
        configure(Settings(url="http://first.test"))
        first = _mod._client
        configure(Settings(url="http://second.test"))
        assert _mod._client is not first

    def test_client_timeout_is_30_seconds(self):
        """httpx.AsyncClient must be constructed with timeout=30.0."""
        settings = Settings(url="http://todo.test:8080")
        with patch("projects.todo_app.todo_mcp.app.main.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock(spec=httpx.AsyncClient)
            configure(settings)
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs.get("timeout") == 30.0


class TestRequest:
    async def test_success_returns_json(self):
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.content = b'{"weekly": {"task": "Write code", "done": false}}'
        mock_resp.json.return_value = {"weekly": {"task": "Write code", "done": False}}
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("GET", "/api/todo")
        assert result["weekly"]["task"] == "Write code"

    async def test_204_no_content_returns_ok(self):
        """204 No Content (e.g. after a reset) must return {'status': 'ok'}."""
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 204
        mock_resp.content = b""
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("POST", "/api/reset/daily")
        assert result == {"status": "ok"}

    async def test_empty_body_returns_ok(self):
        """Responses with is_success=True but no body return {'status': 'ok'}."""
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.content = b""
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("PUT", "/api/todo")
        assert result == {"status": "ok"}

    async def test_http_error_returns_error_dict(self):
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await _request("GET", "/api/todo")
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
            result = await _request("GET", "/api/todo")
        assert "error" in result
        assert "404" in result["error"]

    async def test_exception_returns_error_dict(self):
        with patch.object(
            _mod._client,
            "request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await _request("GET", "/api/todo")
        assert "error" in result
        assert "Connection refused" in result["error"]

    async def test_passes_kwargs_to_client(self):
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.content = b"{}"
        mock_resp.json.return_value = {}
        with patch.object(
            _mod._client, "request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await _request("PUT", "/api/todo", json={"weekly": {}})
        mock_req.assert_called_once_with("PUT", "/api/todo", json={"weekly": {}})

    async def test_exception_calls_logger_warning(self):
        """logger.warning must be called when the underlying request raises."""
        with patch.object(
            _mod._client,
            "request",
            new_callable=AsyncMock,
            side_effect=Exception("network failure"),
        ):
            with patch.object(_mod.logger, "warning") as mock_warn:
                result = await _request("GET", "/api/todo")
        mock_warn.assert_called_once()
        assert "Todo API request failed" in mock_warn.call_args[0][0]
        assert "error" in result


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
            _PATCH,
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_req:
            result = await get_tasks()
        mock_req.assert_called_once_with("GET", "/api/todo")
        assert result["weekly"]["task"] == "Ship feature"
        assert len(result["daily"]) == 3

    async def test_returns_daily_done_state(self):
        expected = {
            "weekly": {"task": "Week goal", "done": True},
            "daily": [
                {"task": "Task A", "done": True},
                {"task": "Task B", "done": True},
                {"task": "Task C", "done": False},
            ],
        }
        with patch(_PATCH, new_callable=AsyncMock, return_value=expected):
            result = await get_tasks()
        assert result["weekly"]["done"] is True
        assert result["daily"][0]["done"] is True
        assert result["daily"][2]["done"] is False

    async def test_http_error_returns_error_dict(self):
        with patch(
            _PATCH,
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
            _PATCH,
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

    async def test_sends_state_with_done_true(self):
        """Marking tasks as done must correctly set done=True in the payload."""
        expected_state = {
            "weekly": {"task": "Finished goal", "done": True},
            "daily": [
                {"task": "Done task 1", "done": True},
                {"task": "Done task 2", "done": True},
                {"task": "Done task 3", "done": True},
            ],
        }
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"status": "ok"}
        ) as mock_req:
            await set_tasks(
                weekly_task="Finished goal",
                weekly_done=True,
                daily_1_task="Done task 1",
                daily_1_done=True,
                daily_2_task="Done task 2",
                daily_2_done=True,
                daily_3_task="Done task 3",
                daily_3_done=True,
            )
        mock_req.assert_called_once_with("PUT", "/api/todo", json=expected_state)

    async def test_sends_empty_slots(self):
        """Empty string task slots are preserved in the payload."""
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"status": "ok"}
        ) as mock_req:
            await set_tasks(
                weekly_task="Focus",
                weekly_done=False,
                daily_1_task="Task 1",
                daily_1_done=False,
                daily_2_task="",
                daily_2_done=False,
                daily_3_task="",
                daily_3_done=False,
            )
        body = mock_req.call_args[1]["json"]
        assert body["daily"][1]["task"] == ""
        assert body["daily"][2]["task"] == ""

    async def test_http_error_returns_error_dict(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Todo API error: 422"},
        ):
            result = await set_tasks(
                weekly_task="x",
                weekly_done=False,
                daily_1_task="",
                daily_1_done=False,
                daily_2_task="",
                daily_2_done=False,
                daily_3_task="",
                daily_3_done=False,
            )
        assert "error" in result

    async def test_uses_put_method(self):
        """set_tasks must use PUT (not POST or PATCH)."""
        with patch(
            _PATCH, new_callable=AsyncMock, return_value={"status": "ok"}
        ) as mock_req:
            await set_tasks(
                weekly_task="x",
                weekly_done=False,
                daily_1_task="",
                daily_1_done=False,
                daily_2_task="",
                daily_2_done=False,
                daily_3_task="",
                daily_3_done=False,
            )
        assert mock_req.call_args[0][0] == "PUT"


class TestResetDaily:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_daily()
        mock_req.assert_called_once_with("POST", "/api/reset/daily")
        assert result["status"] == "ok"

    async def test_error_returns_error_dict(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Todo API error: 500"},
        ):
            result = await reset_daily()
        assert "error" in result


class TestResetWeekly:
    async def test_posts_to_reset_endpoint(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_req:
            result = await reset_weekly()
        mock_req.assert_called_once_with("POST", "/api/reset/weekly")
        assert result["status"] == "ok"

    async def test_error_returns_error_dict(self):
        with patch(
            _PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Todo API error: 500"},
        ):
            result = await reset_weekly()
        assert "error" in result
