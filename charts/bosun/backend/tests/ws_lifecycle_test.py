"""
Tests for WebSocket session lifecycle.

Validates session_init, cancel, and new_session behavior.
"""

import asyncio
import json
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from charts.bosun.backend.tests.conftest import (
    build_jsonl_lines,
    make_mock_subprocess,
    MockProcess,
    collect_ws_messages,
)


def test_session_init_on_first_message(patched_server):
    """session_init must be the first WS message received after sending a prompt."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Hello"})
            received = collect_ws_messages(ws, until_type="result")

    assert len(received) > 0
    assert received[0]["type"] == "session_init"
    assert received[0]["session_id"] == "test-simple-001"


def test_cancel_sends_cancelled(patched_server):
    """Sending 'cancel' type produces a 'cancelled' WS message."""

    class SlowMockStdout:
        """Stdout that yields init then blocks until cancelled."""

        def __init__(self):
            self._init_sent = False
            self._event = asyncio.Event()

        async def readline(self) -> bytes:
            if not self._init_sent:
                self._init_sent = True
                return (
                    json.dumps(
                        {
                            "type": "system",
                            "subtype": "init",
                            "session_id": "test-cancel-001",
                        }
                    )
                    + "\n"
                ).encode()
            # Block until the process is terminated
            try:
                await asyncio.wait_for(self._event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            return b""

    class SlowMockProcess:
        def __init__(self):
            self.stdout = SlowMockStdout()
            from charts.bosun.backend.tests.conftest import MockStderr

            self.stderr = MockStderr()
            self.returncode = None
            self.pid = 99998

        async def wait(self):
            self.returncode = -15  # SIGTERM
            return self.returncode

        def terminate(self):
            self.returncode = -15
            self.stdout._event.set()

    async def _slow_subprocess(*args, **kwargs):
        return SlowMockProcess()

    with patch("asyncio.create_subprocess_exec", side_effect=_slow_subprocess):
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
    call_count = 0

    async def _multi_subprocess(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        lines = build_jsonl_lines("simple_text.json")
        return MockProcess(lines)

    with patch("asyncio.create_subprocess_exec", side_effect=_multi_subprocess):
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
