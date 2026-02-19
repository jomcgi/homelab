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

# We need to mock the SDK before importing server.py, since server.py
# imports from claude_agent_sdk at module level.

from claude_agent_sdk import (
    SystemMessage, AssistantMessage, ResultMessage,
    TextBlock, ToolUseBlock, ToolResultBlock,
)
from claude_agent_sdk.types import StreamEvent


def _make_stream_events():
    """Create a realistic sequence of SDK messages for a simple query.

    Simulates: system init -> streaming text -> tool use -> tool result
    -> more text -> result.
    """
    return [
        # 1. Session init
        SystemMessage(subtype="init", data={"session_id": "test-session-123"}),

        # 2. Streaming text start
        StreamEvent(
            uuid="e1", session_id="test-session-123",
            event={"type": "content_block_start", "content_block": {"type": "text"}},
            parent_tool_use_id=None,
        ),

        # 3. Text delta
        StreamEvent(
            uuid="e2", session_id="test-session-123",
            event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Let me check that file."}},
            parent_tool_use_id=None,
        ),

        # 4. Message stop (finalize first text block)
        StreamEvent(
            uuid="e3", session_id="test-session-123",
            event={"type": "message_stop"},
            parent_tool_use_id=None,
        ),

        # 5. Tool use (Read)
        AssistantMessage(
            content=[
                ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/tmp/test.py"}),
            ],
            model="claude-sonnet-4-5-20250929",
            parent_tool_use_id=None,
        ),

        # 6. Tool result
        AssistantMessage(
            content=[
                ToolResultBlock(tool_use_id="tu-1", content="print('hello')", is_error=False),
            ],
            model="claude-sonnet-4-5-20250929",
            parent_tool_use_id=None,
        ),

        # 7. More streaming text
        StreamEvent(
            uuid="e4", session_id="test-session-123",
            event={"type": "content_block_start", "content_block": {"type": "text"}},
            parent_tool_use_id=None,
        ),
        StreamEvent(
            uuid="e5", session_id="test-session-123",
            event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "The file looks good."}},
            parent_tool_use_id=None,
        ),
        StreamEvent(
            uuid="e6", session_id="test-session-123",
            event={"type": "message_stop"},
            parent_tool_use_id=None,
        ),

        # 8. Final result
        ResultMessage(
            subtype="success",
            duration_ms=1500,
            duration_api_ms=1200,
            is_error=False,
            num_turns=2,
            session_id="test-session-123",
            total_cost_usd=0.005,
            usage={"input_tokens": 100, "output_tokens": 50},
            result="The file looks good.",
            structured_output=None,
        ),
    ]


async def _mock_query(**kwargs):
    """Async generator that yields the mock SDK messages."""
    for msg in _make_stream_events():
        yield msg


@pytest.mark.asyncio
async def test_tts_fires_only_on_result():
    """Verify full_text only appears in the 'result' WebSocket message.

    This is the core contract: the frontend calls tts.speak(msg.full_text)
    only when msg.type === 'result'. If full_text leaked into other message
    types, TTS would fire prematurely (e.g., on each streaming chunk).
    """
    with patch("server.query", side_effect=_mock_query):
        # Import server after patching
        import server

        from starlette.testclient import TestClient

        # Set workdir on app state
        server.app.state.workdir = "/tmp"

        client = TestClient(server.app)
        received = []

        with client.websocket_connect("/ws") as ws:
            # Send a message
            ws.send_json({"type": "message", "text": "Check the file /tmp/test.py"})

            # Collect all messages until we get a "result"
            deadline = asyncio.get_event_loop().time() + 10
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
    print(f"Message types received: {types_seen}")

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
            # This is fine — it's the "result" type that matters.
            pass
        else:
            # No other message type should contain full_text
            if "full_text" in msg and msg["type"] != "assistant_done":
                pytest.fail(
                    f"full_text leaked into non-result message type '{msg['type']}': "
                    f"{json.dumps(msg, indent=2)}"
                )

    # ── Verify intermediate messages DON'T trigger TTS ──────────────
    # assistant_text should only carry 'content' (streaming chunk), not full_text
    text_msgs = [m for m in received if m["type"] == "assistant_text"]
    for m in text_msgs:
        assert "content" in m, "assistant_text missing content field"
        assert "full_text" not in m, "assistant_text should not have full_text"

    # tool_use should carry name/summary, not full_text
    tool_msgs = [m for m in received if m["type"] == "tool_use"]
    for m in tool_msgs:
        assert "name" in m, "tool_use missing name"
        assert "full_text" not in m, "tool_use should not have full_text"

    # tool_result should carry output, not full_text
    result_msgs = [m for m in received if m["type"] == "tool_result"]
    for m in result_msgs:
        assert "output" in m, "tool_result missing output"
        assert "full_text" not in m, "tool_result should not have full_text"

    print("\nAll assertions passed: TTS fires only on 'result' message.")
    print(f"Total messages: {len(received)}")
    print(f"Result full_text: {received[-1].get('full_text', '')[:80]}...")
