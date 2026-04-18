"""Unit tests for POST /api/knowledge/notes — note creation endpoint."""

from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from knowledge.service import VAULT_ROOT_ENV


@pytest.fixture()
def fake_session():
    return MagicMock()


@pytest.fixture()
def client(fake_session, tmp_path, monkeypatch):
    """TestClient with overridden session and a temp vault root."""
    monkeypatch.setenv(VAULT_ROOT_ENV, str(tmp_path))
    app.dependency_overrides[get_session] = lambda: fake_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestCreateNote:
    """Tests for POST /api/knowledge/notes."""

    def test_create_note_writes_file(self, client, tmp_path):
        """POST with content+title returns 201 and writes file with frontmatter."""
        r = client.post(
            "/api/knowledge/notes",
            json={
                "content": "This is my note content.",
                "title": "My Test Note",
                "source": "manual",
                "tags": ["test", "example"],
                "type": "note",
            },
        )

        assert r.status_code == 201
        body = r.json()
        path = body.get("path", "")
        assert path.endswith(".md")

        written = (tmp_path / path).read_text()
        # Parse frontmatter (between --- delimiters)
        parts = written.split("---\n")
        assert len(parts) >= 3, f"Expected frontmatter delimiters, got: {written}"
        fm = yaml.safe_load(parts[1])
        assert fm["title"] == "My Test Note"
        assert fm["source"] == "manual"
        assert fm["tags"] == ["test", "example"]
        assert fm["type"] == "note"
        # Content follows the frontmatter
        assert "This is my note content." in parts[2]

    def test_create_note_content_required(self, client):
        """POST without content field returns 422 (Pydantic validation)."""
        r = client.post(
            "/api/knowledge/notes",
            json={"title": "No content"},
        )
        assert r.status_code == 422

    def test_create_note_empty_content_rejected(self, client):
        """POST with whitespace-only content returns 400."""
        r = client.post(
            "/api/knowledge/notes",
            json={"content": "   \n  "},
        )
        assert r.status_code == 400
        assert "content" in r.json().get("detail", "").lower()

    def test_create_note_generates_title_from_content(self, client, tmp_path):
        """POST without title uses first 60 chars of content as title."""
        content = "A short note about something interesting"
        r = client.post(
            "/api/knowledge/notes",
            json={"content": content},
        )

        assert r.status_code == 201
        path = r.json().get("path", "")
        written = (tmp_path / path).read_text()
        parts = written.split("---\n")
        fm = yaml.safe_load(parts[1])
        assert fm["title"] == content[:60]
