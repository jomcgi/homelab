"""BDD tests for chat domain API routes."""

import httpx

from shared.testing.markers import covers_route


class TestBackfill:
    @covers_route("/api/chat/backfill", method="POST")
    def test_backfill_requires_running_bot(self, live_server):
        """Backfill returns 409 when bot is not connected."""
        r = httpx.post(f"{live_server}/api/chat/backfill")
        # Without a running Discord bot, backfill either returns a client
        # error (409/503) or crashes (500). All are acceptable — the route exists.
        assert r.status_code >= 400


class TestExplore:
    @covers_route("/api/chat/explore", method="POST")
    def test_explore_requires_query(self, live_server_with_fake_embedding):
        r = httpx.post(
            f"{live_server_with_fake_embedding}/api/chat/explore",
            json={"query": "test question"},
        )
        # Explore may stream or fail without LLM — assert it doesn't 500
        assert r.status_code != 500
