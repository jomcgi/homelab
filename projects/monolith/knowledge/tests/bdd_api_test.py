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
        assert isinstance(r.json(), list)


class TestKnowledgeNotes:
    @covers_route("/api/knowledge/notes", method="POST")
    def test_create_note(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Test note content", "title": "Test Note"},
        )
        assert r.status_code == 201
        assert "id" in r.json()

    @covers_route("/api/knowledge/notes/{note_id}", method="GET")
    def test_get_note(self, live_server_with_fake_embedding):
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Retrievable note", "title": "Get Test"},
        )
        note_id = create.json()["id"]  # nosemgrep: unsafe-json-field-access
        r = httpx.get(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}"
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Get Test"  # nosemgrep: unsafe-json-field-access

    @covers_route("/api/knowledge/notes/{note_id}", method="PUT")
    def test_update_note(self, live_server_with_fake_embedding):
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Original", "title": "Update Test"},
        )
        note_id = create.json()["id"]  # nosemgrep: unsafe-json-field-access
        r = httpx.put(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}",
            json={"content": "Updated content"},
        )
        assert r.status_code == 200

    @covers_route("/api/knowledge/notes/{note_id}", method="DELETE")
    def test_delete_note(self, live_server_with_fake_embedding):
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Deletable", "title": "Delete Test"},
        )
        note_id = create.json()["id"]  # nosemgrep: unsafe-json-field-access
        r = httpx.delete(
            f"{live_server_with_fake_embedding}/api/knowledge/notes/{note_id}"
        )
        assert r.status_code == 200


class TestKnowledgeIngest:
    @covers_route("/api/knowledge/ingest", method="POST")
    def test_ingest_accepts_payload(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/ingest",
            json={"content": "Ingest test", "source": "test"},
        )
        assert r.status_code == 201


class TestDeadLetter:
    @covers_route("/api/knowledge/dead-letter")
    def test_list_dead_letters(self, live_server_with_fake_embedding):
        r = httpx.get(f"{live_server_with_fake_embedding}/api/knowledge/dead-letter")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

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
        create = httpx.post(
            f"{live_server_with_fake_embedding}/api/knowledge/notes",
            json={"content": "Task note", "title": "Task Test", "type": "task"},
        )
        note_id = create.json()["id"]  # nosemgrep: unsafe-json-field-access
        r = httpx.patch(
            f"{live_server_with_fake_embedding}/api/knowledge/tasks/{note_id}",
            json={"status": "done"},
        )
        assert r.status_code in (200, 404)
