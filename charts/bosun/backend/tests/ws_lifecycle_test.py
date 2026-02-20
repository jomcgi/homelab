"""
Tests for WebSocket session lifecycle.

Validates session_init, cancel, and new_session behavior.
"""

import asyncio
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from claude_agent_sdk import SystemMessage, ResultMessage

from charts.bosun.backend.tests.conftest import (
    build_sdk_events,
    make_mock_query,
    collect_ws_messages,
)


def test_session_init_on_first_message(patched_server):
    """session_init must be the first WS message received after sending a prompt."""
    events = build_sdk_events("simple_text.json")
    mock_query = make_mock_query(events)

    with patch.object(patched_server, "query", side_effect=mock_query):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Hello"})
            received = collect_ws_messages(ws, until_type="result")

    assert len(received) > 0
    assert received[0]["type"] == "session_init"
    assert received[0]["session_id"] == "test-simple-001"


def test_cancel_sends_cancelled(patched_server):
    """Sending 'cancel' type produces a 'cancelled' WS message."""

    async def _slow_query(**kwargs):
        yield SystemMessage(subtype="init", data={"session_id": "test-cancel-001"})
        await asyncio.sleep(5)
        yield ResultMessage(
            subtype="success",
            session_id="test-cancel-001",
            duration_ms=100,
            duration_api_ms=0,
            total_cost_usd=0.0,
            num_turns=0,
            result="",
            is_error=False,
            usage={},
            structured_output=None,
        )

    with patch.object(patched_server, "query", side_effect=_slow_query):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Do something slow"})

            # Wait for init, then cancel
            init_msg = ws.receive_json(mode="text")
            assert init_msg["type"] == "session_init"

            ws.send_json({"type": "cancel"})

            # Collect remaining messages
            received = []
            for _ in range(10):
                try:
                    data = ws.receive_json(mode="text")
                    received.append(data)
                    if data.get("type") == "cancelled":
                        break
                except Exception:
                    break

    types = [m["type"] for m in received]
    assert "cancelled" in types, f"Expected 'cancelled' message, got: {types}"


def test_new_session_resets(patched_server):
    """Sending 'new_session' allows a fresh session on next message."""
    events1 = build_sdk_events("simple_text.json")
    events2 = build_sdk_events("simple_text.json")
    call_count = 0

    async def _multi_query(**kwargs):
        nonlocal call_count
        call_count += 1
        src = events1 if call_count == 1 else events2
        for event in src:
            yield event

    with patch.object(patched_server, "query", side_effect=_multi_query):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            # First message
            ws.send_json({"type": "message", "text": "Hello"})
            received1 = collect_ws_messages(ws, until_type="result")

            # Reset session
            ws.send_json({"type": "new_session"})

            # Second message (should get new session_init)
            ws.send_json({"type": "message", "text": "Hello again"})
            received2 = collect_ws_messages(ws, until_type="result")

    # Both rounds should produce session_init
    assert received1[0]["type"] == "session_init"
    assert received2[0]["type"] == "session_init"
    assert call_count == 2
