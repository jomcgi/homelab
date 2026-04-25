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


# ---------------------------------------------------------------------------
# Gap lifecycle endpoint tests
# ---------------------------------------------------------------------------

SAMPLE_GAP = {
    "id": 1,
    "term": "Linkerd mTLS",
    "gap_class": "internal",
    "state": "in_review",
}


class TestListGapsEndpoint:
    """Tests for GET /api/knowledge/gaps.

    Verifies that query params are correctly forwarded to
    KnowledgeStore.list_gaps() via split_csv(), that limit bounds are
    enforced by FastAPI validation, and that the response is wrapped in
    {"gaps": [...]}.
    """

    def test_happy_path_returns_gaps(self, note_client):
        """list_gaps result is returned as {"gaps": [...]}."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = [SAMPLE_GAP]
            r = note_client.get("/api/knowledge/gaps")

        assert r.status_code == 200
        assert r.json() == {"gaps": [SAMPLE_GAP]}

    def test_empty_result_returns_empty_list(self, note_client):
        """No gaps in store returns {"gaps": []}."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            r = note_client.get("/api/knowledge/gaps")

        assert r.status_code == 200
        assert r.json() == {"gaps": []}

    def test_no_filters_passes_none_to_store(self, note_client):
        """Omitting state/gap_class passes states=None, classes=None to the store."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=None,
                classes=None,
                limit=100,
            )

    def test_state_filter_forwarded_to_store(self, note_client):
        """Single state value is split and forwarded as a list."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?state=in_review")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=["in_review"],
                classes=None,
                limit=100,
            )

    def test_state_csv_split_into_list(self, note_client):
        """Comma-separated state param is split into a list by split_csv()."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?state=in_review,classified")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=["in_review", "classified"],
                classes=None,
                limit=100,
            )

    def test_gap_class_csv_split_into_list(self, note_client):
        """Comma-separated gap_class param is split into a list by split_csv()."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?gap_class=internal,hybrid")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=None,
                classes=["internal", "hybrid"],
                limit=100,
            )

    def test_limit_forwarded_to_store(self, note_client):
        """Explicit limit is forwarded to the store."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?limit=50")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=None,
                classes=None,
                limit=50,
            )

    def test_default_limit_is_100(self, note_client):
        """Default limit is 100 when not specified."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=None,
                classes=None,
                limit=100,
            )

    def test_limit_over_max_returns_422(self, note_client):
        """limit > 500 is rejected with HTTP 422 (FastAPI ge/le validation)."""
        r = note_client.get("/api/knowledge/gaps?limit=501")
        assert r.status_code == 422

    def test_limit_zero_returns_422(self, note_client):
        """limit=0 violates ge=1 constraint and returns HTTP 422."""
        r = note_client.get("/api/knowledge/gaps?limit=0")
        assert r.status_code == 422

    def test_trailing_comma_in_state_stripped(self, note_client):
        """Trailing comma must not produce an empty-string filter segment.

        Regression: without split_csv(), state=in_review, would pass [""]
        through as a filter value which silently hides gaps.
        """
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?state=in_review,")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=["in_review"],
                classes=None,
                limit=100,
            )

    def test_all_comma_state_passes_none(self, note_client):
        """state=, (only commas/spaces) passes None rather than empty list."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?state=,")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=None,
                classes=None,
                limit=100,
            )

    def test_both_filters_forwarded_together(self, note_client):
        """state and gap_class filters are both forwarded simultaneously."""
        with patch("knowledge.router.KnowledgeStore") as MockStore:
            MockStore.return_value.list_gaps.return_value = []
            note_client.get("/api/knowledge/gaps?state=in_review&gap_class=internal")

            MockStore.return_value.list_gaps.assert_called_once_with(
                states=["in_review"],
                classes=["internal"],
                limit=100,
            )


class TestReviewQueueEndpoint:
    """Tests for GET /api/knowledge/gaps/review-queue.

    Delegates to list_review_queue(session); response is {"gaps": [...]}.
    """

    def test_happy_path_returns_gaps(self, note_client):
        """list_review_queue result is wrapped in {"gaps": [...]}."""
        with patch("knowledge.router.list_review_queue") as mock_queue:
            mock_queue.return_value = [SAMPLE_GAP]
            r = note_client.get("/api/knowledge/gaps/review-queue")

        assert r.status_code == 200
        assert r.json() == {"gaps": [SAMPLE_GAP]}

    def test_empty_queue_returns_empty_list(self, note_client):
        """Empty queue returns {"gaps": []}."""
        with patch("knowledge.router.list_review_queue") as mock_queue:
            mock_queue.return_value = []
            r = note_client.get("/api/knowledge/gaps/review-queue")

        assert r.status_code == 200
        assert r.json() == {"gaps": []}

    def test_session_forwarded_to_list_review_queue(self, note_client, fake_session):
        """The injected DB session is forwarded to list_review_queue."""
        with patch("knowledge.router.list_review_queue") as mock_queue:
            mock_queue.return_value = []
            note_client.get("/api/knowledge/gaps/review-queue")

            mock_queue.assert_called_once_with(fake_session)

    def test_multiple_gaps_returned_in_order(self, note_client):
        """Multiple gaps are returned in the order list_review_queue provides."""
        gap_a = {**SAMPLE_GAP, "id": 1, "term": "alpha"}
        gap_b = {**SAMPLE_GAP, "id": 2, "term": "beta"}
        with patch("knowledge.router.list_review_queue") as mock_queue:
            mock_queue.return_value = [gap_a, gap_b]
            r = note_client.get("/api/knowledge/gaps/review-queue")

        assert r.status_code == 200
        terms = [g["term"] for g in r.json()["gaps"]]
        assert terms == ["alpha", "beta"]


class TestAnswerGapEndpoint:
    """Tests for POST /api/knowledge/gaps/{gap_id}/answer.

    The endpoint accepts {"answer": "..."}, delegates to answer_gap(), and
    maps ValueError sub-types to specific HTTP status codes:
      - "Gap not found"        → 404
      - "expected 'in_review'" → 409
      - "frontmatter terminator" → 400
      - any other ValueError   → 400
    """

    def test_happy_path_returns_answer_gap_result(self, note_client):
        """Successful answer_gap() result is returned directly."""
        expected = {
            "gap_id": 1,
            "note_id": "linkerd-mtls",
            "path": "_processed/linkerd-mtls.md",
        }
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.return_value = expected
            r = note_client.post(
                "/api/knowledge/gaps/1/answer",
                json={"answer": "Linkerd uses per-pod sidecars on port 4143."},
            )

        assert r.status_code == 200
        assert r.json() == expected

    def test_answer_and_gap_id_forwarded_to_answer_gap(self, note_client):
        """gap_id and answer string are forwarded positionally to answer_gap."""
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.return_value = {"gap_id": 42, "note_id": "x", "path": "x.md"}
            note_client.post(
                "/api/knowledge/gaps/42/answer",
                json={"answer": "my answer text"},
            )

            args, _ = mock_answer.call_args
            # answer_gap(session, gap_id, answer, vault_root)
            assert args[1] == 42
            assert args[2] == "my answer text"

    def test_gap_not_found_returns_404(self, note_client):
        """ValueError containing 'Gap not found' maps to HTTP 404."""
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.side_effect = ValueError("Gap not found: id=9999")
            r = note_client.post(
                "/api/knowledge/gaps/9999/answer",
                json={"answer": "anything"},
            )

        assert r.status_code == 404
        assert "Gap not found" in r.json().get("detail", "")

    def test_wrong_state_returns_409(self, note_client):
        """ValueError containing 'expected in_review' maps to HTTP 409."""
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.side_effect = ValueError(
                "Gap 1 is in state 'discovered', expected 'in_review'"
            )
            r = note_client.post(
                "/api/knowledge/gaps/1/answer",
                json={"answer": "x"},
            )

        assert r.status_code == 409
        assert "expected 'in_review'" in r.json().get("detail", "")

    def test_frontmatter_terminator_returns_400(self, note_client):
        """ValueError containing 'frontmatter terminator' maps to HTTP 400."""
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.side_effect = ValueError(
                "Answer contains a frontmatter terminator (---)"
            )
            r = note_client.post(
                "/api/knowledge/gaps/1/answer",
                json={"answer": "foo\n---\nbar"},
            )

        assert r.status_code == 400
        assert "frontmatter terminator" in r.json().get("detail", "")

    def test_other_value_error_returns_400(self, note_client):
        """Any other ValueError (not matched by the three specific checks) → 400."""
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.side_effect = ValueError("some unexpected validation failure")
            r = note_client.post(
                "/api/knowledge/gaps/1/answer",
                json={"answer": "x"},
            )

        assert r.status_code == 400

    def test_missing_answer_field_returns_422(self, note_client):
        """Request body without 'answer' field is rejected by FastAPI with 422."""
        r = note_client.post(
            "/api/knowledge/gaps/1/answer",
            json={},
        )
        assert r.status_code == 422

    def test_error_detail_message_preserved(self, note_client):
        """The ValueError message is preserved verbatim in the detail field."""
        msg = "Gap not found: id=777"
        with patch("knowledge.router.answer_gap") as mock_answer:
            mock_answer.side_effect = ValueError(msg)
            r = note_client.post(
                "/api/knowledge/gaps/777/answer",
                json={"answer": "x"},
            )

        assert r.json().get("detail") == msg
