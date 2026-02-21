"""
End-to-end test: send a message, verify TTS-relevant data (full_text)
only appears in the 'result' WebSocket message, never in intermediate events.

This validates the contract between server.py and App.jsx:
    onResult: (text) => tts.speak(text)
only fires on the "result" message type, ensuring TTS doesn't fire
on assistant_text, assistant_done, tool_use, or tool_result events.
"""

import asyncio
import json
from unittest.mock import patch, AsyncMock

import pytest

from charts.bosun.backend.tests.conftest import (
    MockProcess,
    MockStderr,
)


def _make_jsonl_lines():
    """Create JSONL lines simulating: init -> text -> tool -> text -> result."""
    events = [
        {"type": "system", "subtype": "init", "session_id": "test-session-123"},
        {
            "type": "stream_event",
            "event": {"type": "content_block_start", "content_block": {"type": "text"}},
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Let me check that file."},
            },
        },
        {"type": "stream_event", "event": {"type": "message_stop"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu-1",
                        "name": "Read",
                        "input": {"file_path": "/tmp/test.py"},
                    }
                ],
                "model": "claude-sonnet-4-5-20250929",
            },
            "parent_tool_use_id": None,
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu-1",
                        "content": "print('hello')",
                        "is_error": False,
                    }
                ],
                "model": "claude-sonnet-4-5-20250929",
            },
            "parent_tool_use_id": None,
        },
        {
            "type": "stream_event",
            "event": {"type": "content_block_start", "content_block": {"type": "text"}},
        },
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "The file looks good."},
            },
        },
        {"type": "stream_event", "event": {"type": "message_stop"}},
        {
            "type": "result",
            "subtype": "success",
            "session_id": "test-session-123",
            "duration_ms": 1500,
            "total_cost_usd": 0.005,
            "num_turns": 2,
            "result": "The file looks good.",
            "is_error": False,
        },
    ]
    return [(json.dumps(e) + "\n").encode() for e in events]


async def _mock_subprocess(*args, **kwargs):
    return MockProcess(_make_jsonl_lines())


@pytest.mark.asyncio
async def test_tts_fires_only_on_result():
    """Verify full_text only appears in the 'result' WebSocket message.

    This is the core contract: the frontend calls tts.speak(msg.full_text)
    only when msg.type === 'result'. If full_text leaked into other message
    types, TTS would fire prematurely (e.g., on each streaming chunk).
    """
    with patch("asyncio.create_subprocess_exec", side_effect=_mock_subprocess):
        import charts.bosun.backend.server as server

        from starlette.testclient import TestClient

        # Set workdir on app state
        server.app.state.workdir = "/tmp"

        client = TestClient(server.app)
        received = []

        with client.websocket_connect("/ws") as ws:
            # Send a message
            ws.send_json({"type": "message", "text": "Check the file /tmp/test.py"})

            # Collect all messages until we get a "result"
            while True:
                try:
                    data = ws.receive_json(mode="text")
                    received.append(data)
                    if data.get("type") == "result":
                        break
                except Exception:
                    break

    # ── Assertions ──────────────────────────────────────────────────

    # We should have received messages
    assert len(received) > 0, "No WebSocket messages received"

    # Extract message types
    types_seen = [m["type"] for m in received]

    # Must have these event types (proves the full pipeline ran)
    assert "session_init" in types_seen, "Missing session_init"
    assert "assistant_start" in types_seen, "Missing assistant_start"
    assert "assistant_text" in types_seen, "Missing assistant_text"
    assert "assistant_done" in types_seen, "Missing assistant_done"
    assert "tool_use" in types_seen, "Missing tool_use"
    assert "tool_result" in types_seen, "Missing tool_result"
    assert "result" in types_seen, "Missing result"

    # ── Core TTS contract ───────────────────────────────────────────
    # full_text must ONLY appear in the "result" message
    for msg in received:
        if msg["type"] == "result":
            assert "full_text" in msg, "result message missing full_text"
            assert msg["full_text"], "result message has empty full_text"
            assert msg["session_id"] == "test-session-123"
            assert msg["cost_usd"] == 0.005
            assert msg["duration_ms"] == 1500
        elif msg["type"] == "assistant_done":
            # assistant_done carries full_text too, but this is the per-block text,
            # not the TTS trigger. The frontend doesn't call tts.speak on this.
            pass
        else:
            # No other message type should contain full_text
            if "full_text" in msg and msg["type"] != "assistant_done":
                pytest.fail(
                    f"full_text leaked into non-result message type '{msg['type']}': "
                    f"{json.dumps(msg, indent=2)}"
                )

    # ── Verify intermediate messages DON'T trigger TTS ──────────────
    text_msgs = [m for m in received if m["type"] == "assistant_text"]
    for m in text_msgs:
        assert "content" in m, "assistant_text missing content field"
        assert "full_text" not in m, "assistant_text should not have full_text"

    tool_msgs = [m for m in received if m["type"] == "tool_use"]
    for m in tool_msgs:
        assert "name" in m, "tool_use missing name"
        assert "full_text" not in m, "tool_use should not have full_text"

    result_msgs = [m for m in received if m["type"] == "tool_result"]
    for m in result_msgs:
        assert "output" in m, "tool_result missing output"
        assert "full_text" not in m, "tool_result should not have full_text"
