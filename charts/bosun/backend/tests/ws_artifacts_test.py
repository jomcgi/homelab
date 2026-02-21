"""
Tests for artifact extraction (mermaid blocks).

Validates that mermaid code blocks in assistant text are extracted
and sent as separate mermaid_artifact WS messages, including when
mermaid content is written to files via the Write tool.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from charts.bosun.backend.tests.conftest import (
    make_mock_subprocess,
    collect_ws_messages,
)


def test_mermaid_block_extracted(patched_server):
    """Mermaid code blocks in text produce mermaid_artifact WS messages."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("mermaid_response.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Show me a diagram"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    assert "mermaid_artifact" in types, f"Expected mermaid_artifact, got: {types}"

    mermaid_msgs = [m for m in received if m["type"] == "mermaid_artifact"]
    assert len(mermaid_msgs) == 1
    assert "code" in mermaid_msgs[0]
    assert "label" in mermaid_msgs[0]
    assert "graph TD" in mermaid_msgs[0]["code"]
    assert "A[Frontend]" in mermaid_msgs[0]["code"]


def test_no_mermaid_when_absent(patched_server):
    """No mermaid_artifact messages when text has no mermaid blocks."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("simple_text.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Hello"})
            received = collect_ws_messages(ws, until_type="result")

    mermaid_msgs = [m for m in received if m["type"] == "mermaid_artifact"]
    assert len(mermaid_msgs) == 0, "Should not produce mermaid_artifact for plain text"


def test_mermaid_from_write_tool(patched_server):
    """Mermaid content written to .mmd file via Write tool produces mermaid_artifact."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=make_mock_subprocess("write_mermaid.json"),
    ):
        client = TestClient(patched_server.app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "message", "text": "Create a diagram"})
            received = collect_ws_messages(ws, until_type="result")

    types = [m["type"] for m in received]
    assert "mermaid_artifact" in types, (
        f"Expected mermaid_artifact from Write, got: {types}"
    )

    mermaid_msgs = [m for m in received if m["type"] == "mermaid_artifact"]
    assert len(mermaid_msgs) == 1
    assert "graph TD" in mermaid_msgs[0]["code"]
    assert "A[Frontend]" in mermaid_msgs[0]["code"]
    assert mermaid_msgs[0]["label"] == "architecture.mmd"
