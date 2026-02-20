"""
Tests for REST API endpoints (non-WebSocket).

Validates /health, /api/status, and /api/intent.
"""

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient


def test_health_returns_200(patched_server):
    """/health returns 200 with status ok."""
    client = TestClient(patched_server.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_status_endpoint(patched_server):
    """/api/status returns expected structure."""
    client = TestClient(patched_server.app)

    # Initialize _ws_status (normally set by WS connection)
    patched_server.app.state._ws_status = {
        "session_id": None,
        "streaming": False,
        "queue_depth": 0,
        "connected": False,
    }

    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "streaming" in data
    assert "queue_depth" in data
    assert "connected" in data
    assert data["streaming"] is False


def test_intent_fallback_without_gemini(patched_server):
    """/api/intent returns 'message' when Gemini is not configured."""
    with patch.object(patched_server, "_get_gemini", return_value=None):
        client = TestClient(patched_server.app)
        resp = client.post(
            "/api/intent",
            json={"text": "what is this", "context": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "message"


def test_intent_empty_text(patched_server):
    """/api/intent returns 'message' for empty text."""
    client = TestClient(patched_server.app)
    resp = client.post("/api/intent", json={"text": "", "context": {}})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "message"
