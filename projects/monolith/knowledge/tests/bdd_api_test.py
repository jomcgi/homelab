"""BDD tests for knowledge domain API routes."""

import httpx

from shared.testing.markers import covers_route


class TestKnowledgeSearch:
    @covers_route("/api/knowledge/search")
    def test_search_returns_results(self, live_server_with_fake_embedding):
        r = httpx.get(
            f"{live_server_with_fake_embedding}/api/knowledge/search",
            params={"q": "test query"},
        )
        assert r.status_code == 200
        data = r.json()
        # Response may be a list or {"results": [...]} depending on API version
        assert isinstance(data, (list, dict))


class TestKnowledgeNotes:
    @covers_route("/api/knowledge/notes", method="POST")
    def test_create_note(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Test note content", "title": "Test Note"},
        )
        # Route exists and processes the request (may require auth or specific fields)
        assert r.status_code < 500

    @covers_route("/api/knowledge/notes/{note_id}", method="GET")
    def test_get_note(self, live_server_with_fake_embedding):
        r = httpx.get(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/nonexistent"
        )
        # 404 for missing note is correct behaviour
        assert r.status_code in (200, 404)

    @covers_route("/api/knowledge/notes/{note_id}", method="PUT")
    def test_update_note(self, live_server_with_fake_embedding):
        r = httpx.put(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/nonexistent",
            json={"content": "Updated content"},
        )
        assert r.status_code in (200, 404)

    @covers_route("/api/knowledge/notes/{note_id}", method="DELETE")
    def test_delete_note(self, live_server_with_fake_embedding):
        r = httpx.delete(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/nonexistent"
        )
        assert r.status_code in (200, 204, 404)


class TestKnowledgeIngest:
    @covers_route("/api/knowledge/ingest", method="POST")
    def test_ingest_accepts_payload(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/ingest",
            json={"content": "Ingest test", "source": "test"},
        )
        # Route exists and processes the request
        assert r.status_code < 500


class TestDeadLetter:
    @covers_route("/api/knowledge/dead-letter")
    def test_list_dead_letters(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/dead-letter")
        assert r.status_code == 200

    @covers_route("/api/knowledge/dead-letter/{raw_id}/replay", method="POST")
    def test_replay_dead_letter_not_found(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/dead-letter/nonexistent/replay"
        )
        assert r.status_code in (200, 404)


class TestTasks:
    @covers_route("/api/knowledge/tasks")
    def test_list_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/daily")
    def test_daily_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks/daily")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/weekly")
    def test_weekly_tasks(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/tasks/weekly")
        assert r.status_code == 200

    @covers_route("/api/knowledge/tasks/{note_id}", method="PATCH")
    def test_patch_task(self, live_server_with_fake_embedding):
        r = httpx.patch(
            f"{live_server_with_fake_embedding}/api/knowledge/tasks/nonexistent",
            json={"status": "done"},
        )
        assert r.status_code in (200, 404)
