"""Tests for the tasks CLI subcommand."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tools.cli.main import app


@pytest.fixture
def runner():
    return CliRunner()


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_redirect = False
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


class TestListTasks:
    def test_lists_tasks(self, runner):
        """Bare `knowledge tasks` calls GET and formats output."""
        resp = _mock_response(
            {
                "tasks": [
                    {
                        "note_id": "task-1",
                        "title": "Fix the widget",
                        "status": "active",
                        "size": "S",
                        "due": "2026-04-20",
                    },
                    {
                        "note_id": "task-2",
                        "title": "Deploy service",
                        "status": "blocked",
                        "blocked_by": ["task-1"],
                    },
                ]
            }
        )
        with patch("tools.cli.tasks_cmd._request", return_value=resp) as mock_req:
            result = runner.invoke(app, ["knowledge", "tasks"])

        assert result.exit_code == 0
        mock_req.assert_called_once_with("get", "/api/knowledge/tasks", params={})
        assert "task-1" in result.output
        assert "Fix the widget" in result.output
        assert "[active]" in result.output
        assert "due 2026-04-20" in result.output
        assert "task-2" in result.output
        assert "blocked-by" in result.output

    def test_lists_empty(self, runner):
        """Empty task list prints 'No tasks.'."""
        resp = _mock_response({"tasks": []})
        with patch("tools.cli.tasks_cmd._request", return_value=resp):
            result = runner.invoke(app, ["knowledge", "tasks"])

        assert result.exit_code == 0
        assert "No tasks." in result.output


class TestMarkDone:
    def test_marks_done(self, runner):
        """`knowledge tasks done <id>` calls PATCH with done status."""
        resp = _mock_response({})
        with patch("tools.cli.tasks_cmd._request", return_value=resp) as mock_req:
            result = runner.invoke(app, ["knowledge", "tasks", "done", "task-1"])

        assert result.exit_code == 0
        mock_req.assert_called_once_with(
            "patch",
            "/api/knowledge/tasks/task-1",
            json={"status": "done"},
        )
        assert "done" in result.output.lower()


class TestCancel:
    def test_cancel(self, runner):
        """`knowledge tasks cancel <id>` calls PATCH with cancelled status."""
        resp = _mock_response({})
        with patch("tools.cli.tasks_cmd._request", return_value=resp) as mock_req:
            result = runner.invoke(app, ["knowledge", "tasks", "cancel", "task-1"])

        assert result.exit_code == 0
        mock_req.assert_called_once_with(
            "patch",
            "/api/knowledge/tasks/task-1",
            json={"status": "cancelled"},
        )
        assert "cancelled" in result.output.lower()


class TestSearch:
    def test_search(self, runner):
        """`knowledge tasks search "query"` passes q param."""
        resp = _mock_response(
            {
                "tasks": [
                    {
                        "note_id": "task-3",
                        "title": "Search result",
                        "status": "active",
                    }
                ]
            }
        )
        with patch("tools.cli.tasks_cmd._request", return_value=resp) as mock_req:
            result = runner.invoke(app, ["knowledge", "tasks", "search", "my query"])

        assert result.exit_code == 0
        mock_req.assert_called_once_with(
            "get", "/api/knowledge/tasks", params={"q": "my query"}
        )
        assert "task-3" in result.output
        assert "Search result" in result.output
