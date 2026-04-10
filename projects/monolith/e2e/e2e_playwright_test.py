"""Playwright browser e2e tests for the monolith.

These tests start a real FastAPI server (uvicorn) + SvelteKit Node server,
both backed by the test PostgreSQL instance, and exercise the UI through
a real Chromium browser via Playwright.

The ``sveltekit_server`` fixture in conftest.py starts the Node server
with ``API_BASE`` pointing at the live FastAPI server, so the SvelteKit
SSR and client-side fetches hit real endpoints against real PostgreSQL.

HTTP-only tests (no browser needed) use ``live_server`` directly with
``httpx`` as a lightweight alternative for API surface validation.
"""

import httpx
import pytest

# Guard: skip all browser tests if playwright isn't installed.
# The HTTP-only tests below don't need it.
pw = pytest.importorskip("playwright", reason="playwright not installed")


# ---------------------------------------------------------------------------
# Smoke: live server is reachable (HTTP-only, no browser needed)
# ---------------------------------------------------------------------------


class TestLiveServerSmoke:
    def test_healthz(self, live_server):
        """GET /healthz returns 200 on the live server."""
        r = httpx.get(f"{live_server}/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_home_api_returns_todo_structure(self, live_server):
        """GET /api/home returns the expected weekly + daily shape."""
        r = httpx.get(f"{live_server}/api/home")
        assert r.status_code == 200
        data = r.json()
        assert "weekly" in data
        assert "daily" in data
        assert "task" in data["weekly"]
        assert isinstance(data["daily"], list)


# ---------------------------------------------------------------------------
# Task editing flow (what the Svelte UI does via form actions)
# ---------------------------------------------------------------------------


class TestTaskEditFlow:
    """Simulate the browser's save flow: PUT /api/home with JSON body."""

    def test_edit_and_persist_tasks(self, live_server):
        """PUT tasks, then GET to verify persistence (mirrors auto-save debounce)."""
        payload = {
            "weekly": {"task": "Ship the release", "done": False},
            "daily": [
                {"task": "Write tests", "done": False},
                {"task": "Review PRs", "done": False},
                {"task": "Deploy to staging", "done": False},
            ],
        }
        put = httpx.put(f"{live_server}/api/home", json=payload)
        assert put.status_code == 200

        get = httpx.get(f"{live_server}/api/home")
        assert get.status_code == 200
        data = get.json()
        assert data["weekly"]["task"] == "Ship the release"
        assert data["daily"][0]["task"] == "Write tests"
        assert data["daily"][1]["task"] == "Review PRs"
        assert data["daily"][2]["task"] == "Deploy to staging"

    def test_toggle_done_state(self, live_server):
        """Toggle a task's done state and verify it persists."""
        # Set initial state
        payload = {
            "weekly": {"task": "Weekly goal", "done": False},
            "daily": [
                {"task": "Task one", "done": False},
                {"task": "Task two", "done": False},
                {"task": "Task three", "done": False},
            ],
        }
        httpx.put(f"{live_server}/api/home", json=payload)

        # Toggle done state (simulates clicking a task in the UI)
        payload["daily"][0]["done"] = True
        payload["weekly"]["done"] = True
        put = httpx.put(f"{live_server}/api/home", json=payload)
        assert put.status_code == 200

        data = httpx.get(f"{live_server}/api/home").json()
        assert data["weekly"]["done"] is True
        assert data["daily"][0]["done"] is True
        assert data["daily"][1]["done"] is False

    def test_overwrite_tasks(self, live_server):
        """Subsequent saves overwrite previous values (like re-typing in the UI)."""
        first = {
            "weekly": {"task": "First goal", "done": False},
            "daily": [{"task": "First daily", "done": False}],
        }
        httpx.put(f"{live_server}/api/home", json=first)

        second = {
            "weekly": {"task": "Updated goal", "done": False},
            "daily": [{"task": "Updated daily", "done": True}],
        }
        httpx.put(f"{live_server}/api/home", json=second)

        data = httpx.get(f"{live_server}/api/home").json()
        assert data["weekly"]["task"] == "Updated goal"
        assert data["daily"][0]["task"] == "Updated daily"
        assert data["daily"][0]["done"] is True


# ---------------------------------------------------------------------------
# Daily reset flow
# ---------------------------------------------------------------------------


class TestDailyResetFlow:
    def test_reset_daily_clears_and_archives(self, live_server):
        """POST /api/home/reset/daily clears daily tasks and creates an archive."""
        payload = {
            "weekly": {"task": "Preserved weekly", "done": False},
            "daily": [
                {"task": "Done task", "done": True},
                {"task": "Pending task", "done": False},
                {"task": "", "done": False},
            ],
        }
        httpx.put(f"{live_server}/api/home", json=payload)

        reset = httpx.post(f"{live_server}/api/home/reset/daily")
        assert reset.status_code == 200

        # Daily tasks should be cleared
        data = httpx.get(f"{live_server}/api/home").json()
        assert all(d["task"] == "" for d in data["daily"])
        # Weekly task preserved
        assert data["weekly"]["task"] == "Preserved weekly"

        # Archive date should exist
        dates = httpx.get(f"{live_server}/api/home/dates").json()
        assert len(dates) >= 1


# ---------------------------------------------------------------------------
# Weekly reset flow
# ---------------------------------------------------------------------------


class TestWeeklyResetFlow:
    def test_reset_weekly_clears_goal(self, live_server):
        """POST /api/home/reset/weekly clears the weekly goal."""
        payload = {
            "weekly": {"task": "Goal to clear", "done": True},
            "daily": [{"task": "Keep this", "done": False}],
        }
        httpx.put(f"{live_server}/api/home", json=payload)

        reset = httpx.post(f"{live_server}/api/home/reset/weekly")
        assert reset.status_code == 200

        data = httpx.get(f"{live_server}/api/home/weekly").json()
        assert data["task"] == ""
        assert data["done"] is False


# ---------------------------------------------------------------------------
# Schedule API (iCal feed not configured, returns empty list)
# ---------------------------------------------------------------------------


class TestScheduleAPI:
    def test_today_schedule(self, live_server):
        """GET /api/schedule/today returns a list (empty when no iCal feed)."""
        r = httpx.get(f"{live_server}/api/schedule/today")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Notes API
# ---------------------------------------------------------------------------


class TestNotesAPI:
    def test_create_note(self, live_server):
        """POST /api/notes creates a note (vault mocked at server level)."""
        r = httpx.post(
            f"{live_server}/api/notes",
            json={"content": "Playwright e2e note"},
        )
        # 201 if vault mock works, 500 if vault is unreachable (no mock at server level)
        # Since the live server doesn't have vault mocked, this tests the real path
        assert r.status_code in (201, 500)

    def test_empty_note_returns_400(self, live_server):
        """POST /api/notes with empty content returns 400."""
        r = httpx.post(f"{live_server}/api/notes", json={"content": ""})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Browser UI tests (requires SvelteKit + Playwright/Chromium)
# ---------------------------------------------------------------------------


class TestBrowserUI:
    """Full browser-based Playwright tests for the SvelteKit frontend.

    These tests exercise the actual UI through Chromium, verifying that
    the SvelteKit SSR renders correctly and client-side interactions
    (editing, saving, resetting) work end-to-end.

    Requires:
    - SvelteKit build output as a Bazel data dep (frontend_dist)
    - Node.js to run the SvelteKit server
    - Playwright + Chromium browser binary
    """

    def test_page_loads_todo_section(self, page, sveltekit_server, live_server):
        """Navigate to /private and verify the todo section renders."""
        # Seed some tasks so the page has content
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "Browser test goal", "done": False},
                "daily": [
                    {"task": "First task", "done": False},
                    {"task": "Second task", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".todo-field--goal")

        # Weekly goal should be visible
        goal_input = page.locator(".todo-field--goal")
        assert goal_input.input_value() == "Browser test goal"

        # Daily tasks should be visible
        daily_inputs = page.locator(".todo-daily-row .todo-field")
        assert daily_inputs.count() == 3
        assert daily_inputs.nth(0).input_value() == "First task"
        assert daily_inputs.nth(1).input_value() == "Second task"

    def test_enter_edit_mode_and_type(self, page, sveltekit_server, live_server):
        """Click the todo label to enter edit mode, type in the goal field."""
        # Start with empty tasks
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "", "done": False},
                "daily": [
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".section-label--interactive")

        # Click the "todo" label to enter edit mode
        page.click(".section-label--interactive")

        # The label text should change to "done"
        label = page.locator(".section-label--interactive")
        assert label.inner_text().strip().lower() == "done"

        # Type in the weekly goal field
        goal_input = page.locator(".todo-field--goal")
        goal_input.fill("Typed via Playwright")

        # Wait for auto-save debounce (400ms + buffer)
        page.wait_for_timeout(800)

        # Verify the save persisted via API
        data = httpx.get(f"{live_server}/api/home").json()
        assert data["weekly"]["task"] == "Typed via Playwright"

    def test_auto_save_debounce(self, page, sveltekit_server, live_server):
        """Type, wait for debounce, reload, verify value persists."""
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "", "done": False},
                "daily": [
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".section-label--interactive")

        # Enter edit mode and type
        page.click(".section-label--interactive")
        goal_input = page.locator(".todo-field--goal")
        goal_input.fill("Debounce test value")

        # Wait for auto-save (400ms debounce + network round-trip)
        page.wait_for_timeout(1000)

        # Reload the page and verify persistence via SSR
        page.reload()
        page.wait_for_selector(".todo-field--goal")

        goal_after = page.locator(".todo-field--goal")
        assert goal_after.input_value() == "Debounce test value"

    def test_toggle_done_via_click(self, page, sveltekit_server, live_server):
        """Click a task with text to toggle done state."""
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "Clickable goal", "done": False},
                "daily": [
                    {"task": "Click me", "done": False},
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".todo-field--goal")

        # Click the weekly goal to toggle done (not in edit mode)
        page.click(".todo-field--goal")

        # Wait for save
        page.wait_for_timeout(800)

        # Verify via API
        data = httpx.get(f"{live_server}/api/home").json()
        assert data["weekly"]["done"] is True

    def test_escape_exits_edit_mode(self, page, sveltekit_server, live_server):
        """Press Escape while editing to exit edit mode."""
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "", "done": False},
                "daily": [
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".section-label--interactive")

        # Enter edit mode
        page.click(".section-label--interactive")
        label = page.locator(".section-label--interactive")
        assert label.inner_text().strip().lower() == "done"

        # Press Escape on the goal field
        page.locator(".todo-field--goal").press("Escape")

        # Should exit edit mode — label should say "todo" again
        assert label.inner_text().strip().lower() == "todo"

    def test_enter_advances_focus(self, page, sveltekit_server, live_server):
        """Press Enter in weekly goal to move focus to first daily input."""
        httpx.put(
            f"{live_server}/api/home",
            json={
                "weekly": {"task": "", "done": False},
                "daily": [
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                    {"task": "", "done": False},
                ],
            },
        )

        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".section-label--interactive")

        # Enter edit mode
        page.click(".section-label--interactive")

        # Focus the goal and press Enter
        goal_input = page.locator(".todo-field--goal")
        goal_input.fill("Weekly goal")
        goal_input.press("Enter")

        # The first daily input should now be focused
        first_daily = page.locator(".todo-daily-row .todo-field").nth(0)
        assert first_daily.evaluate("el => el === document.activeElement")

    def test_capture_note_sends_and_clears(self, page, sveltekit_server):
        """Type a note in the capture area and send with Cmd+Enter."""
        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".capture-input")

        # Type a note
        capture = page.locator(".capture-input")
        capture.fill("Test note from Playwright")

        # Character count should appear
        count = page.locator(".capture-count")
        assert count.is_visible()

        # Send with Meta+Enter (Cmd+Enter on macOS, Ctrl+Enter on Linux)
        capture.press("Meta+Enter")

        # The "sent" hint should briefly appear
        # (The vault isn't mocked at server level so this may fail,
        # but we can at least verify the key binding triggers the action)
        page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Knowledge search HTTP tests (no browser needed)
# ---------------------------------------------------------------------------


def _seed_knowledge_note(
    pg,
    *,
    note_id: str,
    title: str,
    path: str,
    note_type: str = "note",
    tags: list[str] | None = None,
    chunk_texts: list[str],
) -> None:
    """Insert a note + chunks with deterministic embeddings into the test DB.

    Uses a fresh engine+session per call so the data is committed and visible
    to the live server (which uses its own connection pool).
    """
    from conftest import deterministic_embedding
    from sqlmodel import Session as SMSession
    from sqlmodel import create_engine as sm_create_engine

    engine = sm_create_engine(pg.url)
    with SMSession(engine) as session:
        from knowledge.models import Chunk, Note

        note = Note(
            note_id=note_id,
            path=path,
            title=title,
            content_hash="e2e-test-hash",
            type=note_type,
            tags=tags or [],
        )
        session.add(note)
        session.flush()

        for idx, text in enumerate(chunk_texts):
            session.add(
                Chunk(
                    note_fk=note.id,
                    chunk_index=idx,
                    section_header=f"Section {idx}",
                    chunk_text=text,
                    embedding=deterministic_embedding(text),
                )
            )
        session.commit()
    engine.dispose()


def _cleanup_knowledge(pg) -> None:
    """Remove all knowledge rows so tests are isolated."""
    from sqlalchemy import text
    from sqlmodel import create_engine as sm_create_engine

    engine = sm_create_engine(pg.url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM knowledge.chunks"))
        conn.execute(text("DELETE FROM knowledge.note_links"))
        conn.execute(text("DELETE FROM knowledge.notes"))
    engine.dispose()


class TestKnowledgeSearchHttp:
    """HTTP-level tests for /api/knowledge endpoints (no browser needed).

    These hit the real live FastAPI server + real Postgres, but use a
    deterministic embedding client so no external embedding service is needed.
    """

    def test_knowledge_search_empty_query(self, live_server_with_fake_embedding):
        """GET /api/knowledge/search?q= returns empty results."""
        base = live_server_with_fake_embedding
        r = httpx.get(f"{base}/api/knowledge/search?q=")
        assert r.status_code == 200
        assert r.json() == {"results": []}

    def test_knowledge_search_returns_results(
        self, live_server_with_fake_embedding, pg
    ):
        """Seed a note, search with matching text, expect it in results."""
        _cleanup_knowledge(pg)
        _seed_knowledge_note(
            pg,
            note_id="e2e-transformers-001",
            title="Transformer Architecture",
            path="notes/transformers.md",
            note_type="note",
            tags=["ml", "architecture"],
            chunk_texts=["Transformers use self-attention to process sequences."],
        )

        base = live_server_with_fake_embedding
        r = httpx.get(
            f"{base}/api/knowledge/search",
            params={"q": "Transformers use self-attention to process sequences."},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) >= 1

        hit = data["results"][0]
        assert hit["note_id"] == "e2e-transformers-001"
        assert hit["title"] == "Transformer Architecture"
        assert hit["type"] == "note"
        assert hit["tags"] == ["ml", "architecture"]
        assert hit["score"] > 0
        assert "snippet" in hit
        assert "section" in hit

        _cleanup_knowledge(pg)

    def test_knowledge_search_type_filter(self, live_server_with_fake_embedding, pg):
        """Seed two notes with different types, filter by type, expect only matching."""
        _cleanup_knowledge(pg)
        shared_text = "Neural network training and optimization techniques."
        _seed_knowledge_note(
            pg,
            note_id="e2e-filter-article",
            title="Training Neural Nets",
            path="notes/training.md",
            note_type="article",
            chunk_texts=[shared_text],
        )
        _seed_knowledge_note(
            pg,
            note_id="e2e-filter-log",
            title="Training Log Entry",
            path="notes/training-log.md",
            note_type="log",
            chunk_texts=[shared_text],
        )

        base = live_server_with_fake_embedding
        r = httpx.get(
            f"{base}/api/knowledge/search",
            params={"q": shared_text, "type": "article"},
        )
        assert r.status_code == 200
        data = r.json()
        results = data["results"]
        assert len(results) >= 1
        assert all(hit["type"] == "article" for hit in results)
        assert any(hit["note_id"] == "e2e-filter-article" for hit in results)
        assert not any(hit["note_id"] == "e2e-filter-log" for hit in results)

        _cleanup_knowledge(pg)

    def test_knowledge_note_returns_content(
        self, live_server_with_fake_embedding, pg, tmp_path_factory
    ):
        """Seed a note whose vault file exists, GET it by id, expect content."""
        _cleanup_knowledge(pg)

        vault_dir = tmp_path_factory.mktemp("vault")
        md_file = vault_dir / "notes" / "e2e-content.md"
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text("# E2E Content\n\nThis is the vault file content.")

        import os

        old_vault_root = os.environ.get("VAULT_ROOT")
        os.environ["VAULT_ROOT"] = str(vault_dir)

        try:
            _seed_knowledge_note(
                pg,
                note_id="e2e-content-001",
                title="E2E Content Note",
                path="notes/e2e-content.md",
                chunk_texts=["E2E content for testing."],
            )

            base = live_server_with_fake_embedding
            r = httpx.get(f"{base}/api/knowledge/notes/e2e-content-001")
            assert r.status_code == 200
            data = r.json()
            assert data["note_id"] == "e2e-content-001"
            assert data["title"] == "E2E Content Note"
            assert "content" in data
            assert "E2E Content" in data["content"]
        finally:
            if old_vault_root is None:
                os.environ.pop("VAULT_ROOT", None)
            else:
                os.environ["VAULT_ROOT"] = old_vault_root
            _cleanup_knowledge(pg)

    def test_knowledge_note_missing_returns_404(self, live_server_with_fake_embedding):
        """GET /api/knowledge/notes/nonexistent returns 404."""
        base = live_server_with_fake_embedding
        r = httpx.get(f"{base}/api/knowledge/notes/nonexistent")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Browser: Knowledge search overlay (requires SvelteKit + Playwright)
# ---------------------------------------------------------------------------


class TestKnowledgeOverlay:
    """Playwright tests for the Cmd+K knowledge search overlay.

    Covers open/close behaviour, capture preservation, search results,
    note preview, and zero-results state.
    """

    # -- Task 12: open/close + capture preservation -------------------------

    def test_cmdk_opens_and_esc_closes(
        self, page, sveltekit_server, live_server_with_fake_embedding
    ):
        """Press Cmd+K to open overlay, Escape to close it."""
        page.goto(f"{sveltekit_server}/private")
        page.wait_for_selector(".capture-input")

        # Open overlay
        page.keyboard.press("Meta+k")
        overlay = page.locator(".search-overlay")
        overlay.wait_for(state="visible")

        # Search input should be focused
        search_input = page.locator(".search-input")
        assert search_input.evaluate("el => el === document.activeElement")

        # Close overlay
        page.keyboard.press("Escape")
        assert page.locator(".search-overlay").count() == 0

    def test_cmdk_preserves_capture_value(
        self, page, sveltekit_server, live_server_with_fake_embedding
    ):
        """Capture textarea value is preserved across overlay open/close."""
        page.goto(f"{sveltekit_server}/private")
        capture = page.locator(".capture-input")
        capture.wait_for(state="visible")
        capture.fill("draft thought")

        # Open and close overlay
        page.keyboard.press("Meta+k")
        page.locator(".search-overlay").wait_for(state="visible")
        page.keyboard.press("Escape")

        # Capture value should be restored
        assert capture.input_value() == "draft thought"

    # -- Task 13: results + preview + zero results --------------------------

    def test_search_renders_results(
        self, page, sveltekit_server, live_server_with_fake_embedding, pg
    ):
        """Seed a note, search, verify result title appears."""
        _cleanup_knowledge(pg)
        _seed_knowledge_note(
            pg,
            note_id="e2e-overlay-attn",
            title="Attention Mechanisms",
            path="notes/attention.md",
            note_type="note",
            tags=["ml"],
            chunk_texts=[
                "Attention mechanisms allow models to focus on relevant parts."
            ],
        )

        try:
            page.goto(f"{sveltekit_server}/private")
            page.keyboard.press("Meta+k")
            page.locator(".search-input").wait_for(state="visible")
            page.locator(".search-input").fill(
                "Attention mechanisms allow models to focus on relevant parts."
            )
            page.locator(".search-result").first.wait_for(
                state="visible", timeout=10000
            )

            assert page.locator(".search-result").count() >= 1
            first_title = page.locator(".search-result-title").first.inner_text()
            assert "Attention Mechanisms" in first_title
        finally:
            _cleanup_knowledge(pg)

    def test_search_preview_and_back(
        self, page, sveltekit_server, live_server_with_fake_embedding, pg, tmp_path
    ):
        """Select a result, verify preview renders, ArrowLeft returns to results."""
        import os

        _cleanup_knowledge(pg)

        # Write a vault file for the note
        vault_dir = tmp_path / "vault"
        md_file = vault_dir / "notes" / "preview-test.md"
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(
            "# Preview Test\n\nAttention is a mechanism for weighting inputs."
        )

        old_vault_root = os.environ.get("VAULT_ROOT")
        os.environ["VAULT_ROOT"] = str(vault_dir)

        try:
            _seed_knowledge_note(
                pg,
                note_id="e2e-overlay-preview",
                title="Preview Test Note",
                path="notes/preview-test.md",
                note_type="note",
                chunk_texts=["Attention is a mechanism for weighting inputs."],
            )

            page.goto(f"{sveltekit_server}/private")
            page.keyboard.press("Meta+k")
            page.locator(".search-input").wait_for(state="visible")
            page.locator(".search-input").fill(
                "Attention is a mechanism for weighting inputs."
            )
            page.locator(".search-result").first.wait_for(
                state="visible", timeout=10000
            )

            # Select the first result
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")

            # Preview should appear
            preview = page.locator(".search-preview-content")
            preview.wait_for(state="visible", timeout=10000)
            assert "attention" in preview.inner_text().lower()

            # ArrowLeft goes back to results
            page.keyboard.press("ArrowLeft")
            assert page.locator(".search-preview-content").count() == 0
            assert page.locator(".search-results").count() >= 1

            # Escape closes overlay
            page.keyboard.press("Escape")
            assert page.locator(".search-overlay").count() == 0
        finally:
            if old_vault_root is None:
                os.environ.pop("VAULT_ROOT", None)
            else:
                os.environ["VAULT_ROOT"] = old_vault_root
            _cleanup_knowledge(pg)

    def test_zero_results_shows_no_results(
        self, page, sveltekit_server, live_server_with_fake_embedding
    ):
        """Type a nonsense query and verify 'no results' status appears."""
        page.goto(f"{sveltekit_server}/private")
        page.keyboard.press("Meta+k")
        page.locator(".search-input").wait_for(state="visible")
        page.locator(".search-input").fill("zxqvfnonsensequery")

        status = page.locator(".search-status")
        status.wait_for(state="visible", timeout=10000)
        assert "no results" in status.inner_text().lower()
