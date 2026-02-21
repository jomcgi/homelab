"""
Tests for diff artifact detection.

Validates that code diffs are extracted from Edit tool inputs and from
tool results containing unified diff output (e.g. git diff), and sent
as 'diff' WS events that the frontend can render.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from charts.bosun.backend.tests.conftest import (
    make_mock_subprocess,
    collect_ws_messages,
)


def test_edit_tool_produces_diff(patched_server):
    """Edit tool_use with old_string/new_string emits a diff event."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("edit_file.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Fix the function"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    assert "diff" in types, f"Expected 'diff' event from Edit tool, got: {types}"

    diff_msgs = [m for m in received if m["type"] == "diff"]
    assert len(diff_msgs) == 1
    diff = diff_msgs[0]
    assert diff["file"] == "handler.py"
    assert "--- a/src/handler.py" in diff["content"]
    assert "+++ b/src/handler.py" in diff["content"]
    assert "+    if not req:" in diff["content"]
    assert "+        return 400" in diff["content"]


def test_bash_diff_output_produces_diff(patched_server):
    """Bash tool result containing unified diff emits a diff event."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("bash_diff.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Show me the changes"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    assert "diff" in types, f"Expected 'diff' event from Bash output, got: {types}"

    diff_msgs = [m for m in received if m["type"] == "diff"]
    assert len(diff_msgs) == 1
    diff = diff_msgs[0]
    assert "--- a/src/handler.py" in diff["content"]
    assert "+    if not req:" in diff["content"]


def test_no_diff_for_plain_tool_result(patched_server):
    """Tool results without diff content should not produce diff events."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Hello"})
            received = collect_ws_messages(ws, until_type="result")

    diff_msgs = [m for m in received if m["type"] == "diff"]
    assert len(diff_msgs) == 0, "Should not produce diff for plain text response"
