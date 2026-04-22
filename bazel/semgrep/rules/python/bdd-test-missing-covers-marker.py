# Tests for bdd-test-missing-covers-marker rule.
#
# This rule targets **/tests/bdd_*_test.py files only.
# Test methods (def test_*) MUST have a @covers_route, @covers_page, or
# @covers_public decorator from shared.testing.markers.
import httpx

from shared.testing.markers import covers_page, covers_public, covers_route


class TestScheduleAPI:
    # ruleid: bdd-test-missing-covers-marker
    def test_missing_marker(self, live_server):
        r = httpx.get(f"{live_server}/api/home/schedule/today")
        assert r.status_code == 200

    # ruleid: bdd-test-missing-covers-marker
    def test_another_missing_marker(self, live_server):
        r = httpx.get(f"{live_server}/api/home/schedule/week")
        assert r.status_code == 200

    # ok: bdd-test-missing-covers-marker — has @covers_route decorator
    @covers_route("/api/home/schedule/today")
    def test_with_covers_route(self, live_server):
        r = httpx.get(f"{live_server}/api/home/schedule/today")
        assert r.status_code == 200

    # ok: bdd-test-missing-covers-marker — has @covers_page decorator
    @covers_page("/home/schedule")
    def test_with_covers_page(self, live_server):
        r = httpx.get(f"{live_server}/home/schedule")
        assert r.status_code == 200

    # ok: bdd-test-missing-covers-marker — has @covers_public decorator
    @covers_public("home.services.schedule.get_today")
    def test_with_covers_public(self, live_server):
        from home.services import schedule

        result = schedule.get_today()
        assert result is not None


class TestPublicPages:
    # ruleid: bdd-test-missing-covers-marker
    def test_page_loads_without_marker(self, live_server):
        r = httpx.get(f"{live_server}/home")
        assert r.status_code == 200

    # ok: bdd-test-missing-covers-marker — has @covers_route with method kwarg
    @covers_route("/api/home/items", method="POST")
    def test_post_endpoint(self, live_server):
        r = httpx.post(f"{live_server}/api/home/items", json={"name": "test"})
        assert r.status_code == 201


# ok: bdd-test-missing-covers-marker — helper functions (not test_*) are exempt
def _setup_fixture(server):
    return httpx.get(f"{server}/api/health")


# ok: bdd-test-missing-covers-marker — non-test methods in test classes are exempt
class TestHelpers:
    def setup_method(self):
        pass

    def teardown_method(self):
        pass
