import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def mock_topology():
    """Minimal topology response matching existing JSON shape."""
    return {
        "groups": [
            {
                "id": "testgroup",
                "label": "TEST GROUP",
                "tier": "critical",
                "status": "healthy",
                "description": "test",
                "children": ["child_a"],
                "brief": "100%",
                "slo": {"target": 99.0, "current": 100.0},
                "budget": {
                    "consumed": 0,
                    "elapsed": 100,
                    "remaining": "432.0 min",
                    "window": "30d",
                },
                "metrics": [],
            }
        ],
        "nodes": [
            {
                "id": "child_a",
                "label": "CHILD A",
                "tier": "critical",
                "group": "testgroup",
                "status": "healthy",
                "description": "a child",
                "brief": "100%",
                "slo": {"target": 99.0, "current": 100.0},
                "budget": {
                    "consumed": 0,
                    "elapsed": 100,
                    "remaining": "432.0 min",
                    "window": "30d",
                },
                "metrics": [{"k": "rps", "v": "1.5"}],
            }
        ],
        "edges": [{"from": "ext", "to": "child_a"}],
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the module-level cache between tests."""
    import observability.router as mod

    mod._cache = None
    mod._cache_time = 0.0


class TestObservabilityRouter:
    @patch("observability.router.build_topology")
    def test_get_topology_returns_json(self, mock_build, mock_topology):
        mock_build.return_value = mock_topology
        client = TestClient(app)
        resp = client.get("/api/public/observability/topology")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert "nodes" in data
        assert "edges" in data

    @patch("observability.router.build_topology")
    def test_topology_has_slo_fields(self, mock_build, mock_topology):
        mock_build.return_value = mock_topology
        client = TestClient(app)
        resp = client.get("/api/public/observability/topology")
        data = resp.json()
        node = data["nodes"][0]
        assert "slo" in node
        assert "status" in node
        assert "brief" in node

    @patch("observability.router.build_topology")
    def test_topology_cached(self, mock_build, mock_topology):
        mock_build.return_value = mock_topology
        client = TestClient(app)
        client.get("/api/public/observability/topology")
        client.get("/api/public/observability/topology")
        # build_topology called only once due to cache
        assert mock_build.call_count == 1
