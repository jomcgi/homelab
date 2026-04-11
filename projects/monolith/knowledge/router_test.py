"""Unit tests for knowledge/router.py — /search and /notes endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from knowledge.router import get_embedding_client
from knowledge.service import VAULT_ROOT_ENV

FAKE_EMBEDDING = [0.1] * 1024

CANNED_RESULTS = [
    {
        "note_id": "n1",
        "title": "Attention Is All You Need",
        "path": "papers/attention.md",
        "type": "paper",
        "tags": ["ml", "transformers"],
        "score": 0.95,
        "snippet": "The transformer replaces recurrence entirely with attention.",
        "section": "## Architecture",
    },
]


@pytest.fixture()
def fake_embed_client():
    client = AsyncMock()
    client.embed.return_value = FAKE_EMBEDDING
    return client


@pytest.fixture()
def fake_session():
    return MagicMock()


@pytest.fixture()
def client(fake_session, fake_embed_client):
    """TestClient with overridden session and embedding client."""
    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[get_embedding_client] = lambda: fake_embed_client
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestSearchEndpoint:
    """Tests for GET /api/knowledge/search."""

    def test_happy_path_returns_canned_results(self, client, fake_embed_client):
        """Query >= 2 chars returns results with all expected fields."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_notes_with_context.return_value = (
                CANNED_RESULTS
            )
            r = client.get("/api/knowledge/search?q=attention")

        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == 1
        result = body["results"][0]
        assert result["note_id"] == "n1"
        assert result["title"] == "Attention Is All You Need"
        assert result["path"] == "papers/attention.md"
        assert result["type"] == "paper"
        assert result["tags"] == ["ml", "transformers"]
        assert result["score"] == 0.95
        assert "transformer replaces recurrence" in result["snippet"]
        assert result["section"] == "## Architecture"

        fake_embed_client.embed.assert_awaited_once_with("attention")

    def test_empty_query_returns_empty_results(self, client, fake_embed_client):
        """Empty query returns [] without calling embed or store."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            r = client.get("/api/knowledge/search?q=")

            assert r.status_code == 200
            assert r.json() == {"results": []}
            fake_embed_client.embed.assert_not_awaited()
            MockStore.assert_not_called()

    def test_single_char_query_returns_empty_results(self, client, fake_embed_client):
        """Single-char query returns [] without calling embed."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            r = client.get("/api/knowledge/search?q=a")

            assert r.status_code == 200
            assert r.json() == {"results": []}
            fake_embed_client.embed.assert_not_awaited()
            MockStore.assert_not_called()

    def test_type_filter_forwarded_to_store(self, client):
        """type query param is passed as type_filter to the store."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_notes_with_context.return_value = []
            client.get("/api/knowledge/search?q=attention&type=paper")

            MockStore.return_value.search_notes_with_context.assert_called_once_with(
                query_embedding=FAKE_EMBEDDING,
                limit=20,
                type_filter="paper",
            )

    def test_limit_forwarded_to_store(self, client):
        """limit query param is passed through to the store."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_notes_with_context.return_value = []
            client.get("/api/knowledge/search?q=attention&limit=5")

            MockStore.return_value.search_notes_with_context.assert_called_once_with(
                query_embedding=FAKE_EMBEDDING,
                limit=5,
                type_filter=None,
            )

    def test_embedding_failure_returns_503(self, fake_session):
        """Embedding client exception produces HTTP 503."""
        failing_client = AsyncMock()
        failing_client.embed.side_effect = RuntimeError("boom")
        app.dependency_overrides[get_session] = lambda: fake_session
        app.dependency_overrides[get_embedding_client] = lambda: failing_client
        try:
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/api/knowledge/search?q=hello")
            assert r.status_code == 503
            body = r.json()
            assert body.get("detail") == "embedding unavailable"
        finally:
            app.dependency_overrides.clear()

    def test_default_limit_is_20(self, client):
        """When limit is not specified, store is called with limit=20."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_notes_with_context.return_value = []
            client.get("/api/knowledge/search?q=attention")

            MockStore.return_value.search_notes_with_context.assert_called_once_with(
                query_embedding=FAKE_EMBEDDING,
                limit=20,
                type_filter=None,
            )

    def test_search_results_include_edges(self, client, fake_embed_client):
        """Search results include edges with resolved_note_id for typed edges."""
        results_with_edges = [
            {
                **CANNED_RESULTS[0],
                "edges": [
                    {
                        "target_id": "n2",
                        "kind": "edge",
                        "edge_type": "refines",
                        "target_title": None,
                        "resolved_note_id": "n2",
                    },
                ],
            },
        ]
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.search_notes_with_context.return_value = (
                results_with_edges
            )
            r = client.get("/api/knowledge/search?q=attention")

        assert r.status_code == 200
        body = r.json()
        result = body["results"][0]
        assert "edges" in result
        assert result["edges"][0]["target_id"] == "n2"
        assert result["edges"][0]["edge_type"] == "refines"
        assert result["edges"][0]["resolved_note_id"] == "n2"


SAMPLE_NOTE = {
    "note_id": "n1",
    "title": "Attention Is All You Need",
    "path": "papers/attention.md",
    "type": "paper",
    "tags": ["ml", "transformers"],
}


@pytest.fixture()
def note_client(fake_session):
    """TestClient with only session override — /notes doesn't need embed."""
    app.dependency_overrides[get_session] = lambda: fake_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestGetNoteEndpoint:
    """Tests for GET /api/knowledge/notes/{note_id}."""

    def test_happy_path_returns_note_with_content(
        self, tmp_path, fake_session, monkeypatch
    ):
        """Existing note + vault file returns all fields plus content."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "attention.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("# Attention\n\nSelf-attention mechanism.")

        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = SAMPLE_NOTE
                r = c.get("/api/knowledge/notes/n1")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        body = r.json()
        assert body["note_id"] == "n1"
        assert body["title"] == "Attention Is All You Need"
        assert body["path"] == "papers/attention.md"
        assert body["type"] == "paper"
        assert body["tags"] == ["ml", "transformers"]
        assert body["content"] == "# Attention\n\nSelf-attention mechanism."

    def test_missing_note_returns_404(self, note_client):
        """get_note_by_id returns None -> 404 'note not found'."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.get_note_by_id.return_value = None
            r = note_client.get("/api/knowledge/notes/nonexistent")

        assert r.status_code == 404
        body = r.json()
        assert body.get("detail") == "note not found"

    def test_missing_vault_file_returns_404(self, tmp_path, fake_session, monkeypatch):
        """Note exists in DB but vault file missing on disk -> 404."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))

        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    **SAMPLE_NOTE,
                    "path": "nonexistent/missing.md",
                }
                c = TestClient(app, raise_server_exceptions=False)
                r = c.get("/api/knowledge/notes/n1")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 404
        body = r.json()
        assert body.get("detail") == "vault file missing"

    def test_note_includes_edges(self, tmp_path, fake_session, monkeypatch):
        """Note detail response includes edges."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_file = vault_dir / "papers" / "attention.md"
        note_file.parent.mkdir(parents=True)
        note_file.write_text("# Attention\n\nContent.")

        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))
        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            c = TestClient(app, raise_server_exceptions=False)
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = SAMPLE_NOTE
                MockStore.return_value.get_note_links.return_value = [
                    {
                        "target_id": "n2",
                        "kind": "link",
                        "edge_type": None,
                        "target_title": "Related Note",
                    },
                ]
                r = c.get("/api/knowledge/notes/n1")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 200
        body = r.json()
        assert "edges" in body
        assert body["edges"][0]["target_id"] == "n2"
        assert body["edges"][0]["target_title"] == "Related Note"

    def test_path_traversal_returns_404(self, tmp_path, fake_session, monkeypatch):
        """Path traversal is caught by is_relative_to guard."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        # Create a file outside vault that the traversal path would reach
        secret = tmp_path / "secret.txt"
        secret.write_text("should not be readable")
        monkeypatch.setenv(VAULT_ROOT_ENV, str(vault_dir))

        app.dependency_overrides[get_session] = lambda: fake_session
        try:
            with patch("knowledge.router.KnowledgeStore") as MockStore:
                MockStore.return_value.get_note_by_id.return_value = {
                    **SAMPLE_NOTE,
                    "path": "../secret.txt",
                }
                c = TestClient(app, raise_server_exceptions=False)
                r = c.get("/api/knowledge/notes/n1")
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 404
        body = r.json()
        assert body.get("detail") == "vault file missing"
