"""BDD Playwright tests for knowledge domain frontend pages."""

import pytest

from shared.testing.markers import covers_page

playwright = pytest.importorskip("playwright")


class TestChatPage:
    @covers_page("/private/chat")
    def test_chat_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/private/chat")
        assert page.title() or page.locator("body").inner_text()


class TestPublicLanding:
    @covers_page("/public")
    def test_public_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/public")
        assert page.title() or page.locator("body").inner_text()
