"""BDD Playwright tests for home domain frontend pages."""

import pytest

from shared.testing.markers import covers_page

playwright = pytest.importorskip("playwright")


class TestPrivateDashboard:
    @covers_page("/private")
    def test_dashboard_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/private")
        assert page.title() or page.locator("body").inner_text()


class TestSLOPage:
    @covers_page("/public/slos")
    def test_slo_page_loads(self, page, sveltekit_server):
        page.goto(f"{sveltekit_server}/public/slos")
        assert page.title() or page.locator("body").inner_text()
