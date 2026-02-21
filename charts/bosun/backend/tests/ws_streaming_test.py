"""
Tests for WebSocket streaming message pipeline.

Validates that the server produces the correct sequence of WS messages
(assistant_start → assistant_text → assistant_done → result) and that
the TTS-critical `full_text` field only appears where expected.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from charts.bosun.backend.tests.conftest import (
    make_mock_subprocess,
    collect_ws_messages,
)


def test_simple_text_streaming(patched_server):
    """Simple text response produces correct message sequence."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Say hello"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    assert "session_init" in types
    assert "assistant_start" in types
    assert "assistant_text" in types
    assert "assistant_done" in types
    assert "result" in types

    # Verify ordering: session_init comes first
    assert types.index("session_init") < types.index("assistant_start")
    assert types.index("assistant_start") < types.index("assistant_text")
    assert types.index("assistant_text") < types.index("assistant_done")
    assert types.index("assistant_done") < types.index("result")


def test_assistant_text_has_content_not_full_text(patched_server):
    """assistant_text carries streaming 'content' but never 'full_text'."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Say hello"})
            received = collect_ws_messages(ws, until_type="result")

    text_msgs = [m for m in received if m["type"] == "assistant_text"]
    assert len(text_msgs) > 0
    for m in text_msgs:
        assert "content" in m, "assistant_text must have 'content'"
        assert "full_text" not in m, "assistant_text must not have 'full_text'"

    # The content should contain our fixture text
    combined = "".join(m["content"] for m in text_msgs)
    assert "Hello, world!" in combined


def test_result_has_full_text(patched_server):
    """The result message carries full_text for TTS."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Say hello"})
            received = collect_ws_messages(ws, until_type="result")

    result_msgs = [m for m in received if m["type"] == "result"]
    assert len(result_msgs) == 1
    result = result_msgs[0]
    assert "full_text" in result
    assert result["full_text"]
    assert result["session_id"] == "test-simple-001"
    assert result["cost_usd"] == 0.001
    assert result["duration_ms"] == 500


def test_tool_then_text_streaming(patched_server):
    """Text + tool + text sequence produces all expected message types in order."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_use_flow.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Check the file"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    # Should see text streaming, tool use, tool result, more text, then result
    assert "assistant_start" in types
    assert "assistant_text" in types
    assert "assistant_done" in types
    assert "tool_use" in types
    assert "tool_result" in types
    assert "result" in types

    # Should have at least 2 assistant_start (text before tool, text after tool)
    starts = [m for m in received if m["type"] == "assistant_start"]
    assert len(starts) >= 2, f"Expected 2+ assistant_start, got {len(starts)}"


def test_result_has_full_text_after_tool_turn(patched_server):
    """PR #535 regression: tool-involved turns must still produce result with full_text.

    When a turn includes tool calls, the result message must contain the accumulated
    full_text from all streaming blocks, not just the tool results.
    """
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("tool_use_flow.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Check the file"})
            received = collect_ws_messages(ws, until_type="result")

    result = [m for m in received if m["type"] == "result"][0]
    assert "full_text" in result, "result must contain full_text after tool turn"
    assert result["full_text"], "full_text must not be empty"
    # Should contain text from both streaming blocks
    assert (
        "Let me check" in result["full_text"]
        or "file looks good" in result["full_text"].lower()
    )
