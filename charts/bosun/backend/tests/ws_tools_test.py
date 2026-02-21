"""
Tests for tool use and tool result WebSocket messages.

Validates that tool_use messages carry name/id/summary,
tool_result messages carry output, and error tools have is_error.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from charts.bosun.backend.tests.conftest import (
    make_mock_subprocess,
    collect_ws_messages,
)


def test_tool_use_has_name_and_id(patched_server):
    """tool_use WS messages must have name, tool_use_id, and summary."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_use_flow.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Read the file"})
            received = collect_ws_messages(ws, until_type="result")

    tool_uses = [m for m in received if m["type"] == "tool_use"]
    assert len(tool_uses) >= 1
    for tu in tool_uses:
        assert "name" in tu, "tool_use must have name"
        assert "tool_use_id" in tu, "tool_use must have tool_use_id"
        assert "summary" in tu, "tool_use must have summary"
        assert tu["name"], "name must not be empty"


def test_tool_result_has_output(patched_server):
    """tool_result WS messages must have output field."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_use_flow.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Read the file"})
            received = collect_ws_messages(ws, until_type="result")

    results = [m for m in received if m["type"] == "tool_result"]
    assert len(results) >= 1
    for tr in results:
        assert "output" in tr, "tool_result must have output"
        assert "full_text" not in tr, "tool_result must not have full_text"


def test_tool_error_has_is_error(patched_server):
    """Tool results with is_error=true must propagate is_error in the WS message."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_error.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Run the command"})
            received = collect_ws_messages(ws, until_type="result")

    results = [m for m in received if m["type"] == "tool_result"]
    assert len(results) >= 1
    error_results = [r for r in results if r.get("is_error")]
    assert len(error_results) >= 1, (
        "Expected at least one tool_result with is_error=True"
    )
    assert "command not found" in error_results[0]["output"]


def test_tool_use_no_full_text(patched_server):
    """tool_use messages must never carry full_text (TTS field)."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_use_flow.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Read the file"})
            received = collect_ws_messages(ws, until_type="result")

    tool_uses = [m for m in received if m["type"] == "tool_use"]
    for tu in tool_uses:
        assert "full_text" not in tu, f"tool_use should not have full_text: {tu}"
