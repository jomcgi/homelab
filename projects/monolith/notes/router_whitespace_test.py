"""Tests for whitespace-only content in notes/router.py.

The ``post_note`` handler calls ``data.content.strip()`` and raises HTTP 400
when the result is falsy.  The existing ``router_test.py`` covers the truly
empty string (``""``) but NOT whitespace-only strings such as ``"   "`` or
``"\n\n"``.

This file fills that gap.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(name="client")
def client_fixture():
    return TestClient(app, raise_server_exceptions=False)


class TestPostNoteWhitespaceContent:
    """Whitespace-only content must be rejected with HTTP 400."""

    def test_spaces_only_returns_400(self, client):
        """A content string of spaces is rejected with 400."""
        response = client.post("/api/notes", json={"content": "   "})
        assert response.status_code == 400

    def test_tabs_only_returns_400(self, client):
        """A content string of tabs is rejected with 400."""
        response = client.post("/api/notes", json={"content": "\t\t\t"})
        assert response.status_code == 400

    def test_newlines_only_returns_400(self, client):
        """A content string of newlines is rejected with 400."""
        response = client.post("/api/notes", json={"content": "\n\n\n"})
        assert response.status_code == 400

    def test_mixed_whitespace_returns_400(self, client):
        """A string of mixed whitespace characters is rejected with 400."""
        response = client.post("/api/notes", json={"content": "  \t \n  "})
        assert response.status_code == 400

    def test_single_space_returns_400(self, client):
        """A single space is rejected with 400 (strip() makes it empty)."""
        response = client.post("/api/notes", json={"content": " "})
        assert response.status_code == 400

    def test_whitespace_error_detail_message(self, client):
        """The 400 response for whitespace content includes the expected detail."""
        response = client.post("/api/notes", json={"content": "   "})
        assert response.status_code == 400
        data = response.json()
        assert "content is required" in data.get("detail", "")
