# SLO Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hardcoded topology.json data with live SLO metrics from SigNoz ClickHouse, served by a FastAPI endpoint.

**Architecture:** New `observability` module in the monolith queries ClickHouse HTTP interface for each node's SLO + metrics, aggregates groups from children, caches 15m, returns JSON matching existing topology shape. Frontend fetches from API instead of importing static JSON.

**Tech Stack:** FastAPI, httpx (ClickHouse HTTP), PyYAML (already a dep), SvelteKit (existing frontend)

**Design doc:** `docs/plans/2026-04-12-slo-dashboard-design.md`

---

### Task 1: ClickHouse Client Module

**Files:**

- Create: `projects/monolith/observability/__init__.py`
- Create: `projects/monolith/observability/clickhouse.py`
- Create: `projects/monolith/observability/clickhouse_test.py`

The ClickHouse client is a thin async wrapper around httpx POST to port 8123. Queries return `FORMAT JSON` and we parse the `data` array. IMPORTANT: never JOIN samples ↔ time_series directly (OOMs). Always use `fingerprint IN (SELECT ...)`.

**Step 1: Write failing tests**

Create `projects/monolith/observability/clickhouse_test.py`:

```python
import pytest
import httpx
import json

from observability.clickhouse import ClickHouseClient


@pytest.fixture
def mock_ch_response():
    """Standard ClickHouse FORMAT JSON response."""
    return {
        "meta": [{"name": "value", "type": "Float64"}],
        "data": [{"value": 99.9712}],
        "rows": 1,
    }


@pytest.fixture
def mock_ch_multi_row():
    return {
        "meta": [
            {"name": "bucket", "type": "UInt64"},
            {"name": "value", "type": "Float64"},
        ],
        "data": [
            {"bucket": 1, "value": 100.0},
            {"bucket": 2, "value": 99.5},
            {"bucket": 3, "value": 100.0},
        ],
        "rows": 3,
    }


class TestClickHouseClient:
    @pytest.mark.asyncio
    async def test_query_scalar_returns_first_row_value(self, mock_ch_response):
        """query_scalar extracts 'value' from first row."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_ch_response)
        )
        client = ClickHouseClient(
            base_url="http://fake:8123", transport=transport
        )
        result = await client.query_scalar("SELECT 1 AS value")
        assert result == 99.9712

    @pytest.mark.asyncio
    async def test_query_scalar_returns_none_on_empty(self):
        """query_scalar returns None when no rows."""
        empty = {"meta": [], "data": [], "rows": 0}
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=empty)
        )
        client = ClickHouseClient(
            base_url="http://fake:8123", transport=transport
        )
        result = await client.query_scalar("SELECT 1 AS value WHERE 0")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_rows_returns_all_rows(self, mock_ch_multi_row):
        """query_rows returns list of dicts."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=mock_ch_multi_row)
        )
        client = ClickHouseClient(
            base_url="http://fake:8123", transport=transport
        )
        rows = await client.query_rows("SELECT bucket, value FROM ...")
        assert len(rows) == 3
        assert rows[0]["bucket"] == 1
        assert rows[1]["value"] == 99.5

    @pytest.mark.asyncio
    async def test_query_appends_format_json(self):
        """Client appends FORMAT JSON to queries."""
        seen_body = None

        def handler(req):
            nonlocal seen_body
            seen_body = req.content.decode()
            return httpx.Response(
                200, json={"meta": [], "data": [], "rows": 0}
            )

        transport = httpx.MockTransport(handler)
        client = ClickHouseClient(
            base_url="http://fake:8123", transport=transport
        )
        await client.query_scalar("SELECT 1 AS value")
        assert seen_body.rstrip().endswith("FORMAT JSON")

    @pytest.mark.asyncio
    async def test_query_raises_on_http_error(self):
        """Client raises on non-200 responses."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, text="DB error")
        )
        client = ClickHouseClient(
            base_url="http://fake:8123", transport=transport
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.query_scalar("BAD QUERY")
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:observability_clickhouse_test --config=ci`
Expected: FAIL (module doesn't exist)

**Step 3: Write the implementation**

Create `projects/monolith/observability/__init__.py` (empty file).

Create `projects/monolith/observability/clickhouse.py`:

```python
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """Minimal async ClickHouse HTTP client."""

    def __init__(
        self,
        base_url: str = "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        kwargs: dict = {"base_url": base_url, "timeout": timeout}
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**kwargs)

    async def _query(self, sql: str) -> dict:
        query = sql.rstrip().rstrip(";")
        if not query.upper().endswith("FORMAT JSON"):
            query += "\nFORMAT JSON"
        resp = await self._client.post("/", content=query)
        resp.raise_for_status()
        return resp.json()

    async def query_scalar(self, sql: str) -> float | None:
        """Execute query and return 'value' from first row, or None."""
        result = await self._query(sql)
        if not result.get("data"):
            return None
        return result["data"][0].get("value")

    async def query_rows(self, sql: str) -> list[dict]:
        """Execute query and return all rows."""
        result = await self._query(sql)
        return result.get("data", [])

    async def close(self):
        await self._client.aclose()
```

**Step 4: Add BUILD target for the test**

Add to `projects/monolith/BUILD` (after existing test targets):

```starlark
py_test(
    name = "observability_clickhouse_test",
    srcs = ["observability/clickhouse_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//httpx",
        "@pip//pytest",
        "@pip//pytest_asyncio",
    ],
)
```

Also add `"observability/**/*.py"` to the `monolith_backend` py_library srcs glob and the `main` py_venv_binary srcs glob (both have identical glob patterns). Add a `# gazelle:exclude observability` comment at the top of the BUILD file alongside the existing excludes.

**Step 5: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:observability_clickhouse_test --config=ci`
Expected: PASS (5 tests)

**Step 6: Commit**

```
feat(monolith): add ClickHouse HTTP client for observability queries
```

---

### Task 2: Topology Config Loader

**Files:**

- Create: `projects/monolith/observability/config.py`
- Create: `projects/monolith/observability/config_test.py`
- Create: `projects/monolith/observability/topology.yaml` (minimal — 2 nodes + 1 group + 1 edge for testing)

The config loader reads `topology.yaml`, validates structure, and returns typed dataclasses. Groups have no queries — only a target. Leaf nodes have SLO queries + optional metric queries.

**Step 1: Write failing tests**

Create `projects/monolith/observability/config_test.py`:

```python
import textwrap
from pathlib import Path

import pytest

from observability.config import load_config, TopologyConfig, NodeConfig, GroupConfig


MINIMAL_YAML = textwrap.dedent("""\
    cache_ttl: 900

    groups:
      - id: mygroup
        label: MY GROUP
        tier: critical
        description: "test group"
        children: [child_a]
        slo:
          target: 99.0
          window: 30d

    nodes:
      - id: ext
        label: EXTERNAL
        tier: ingress
        description: "external"
        metrics:
          - key: clients
            static: "a, b"

      - id: child_a
        label: CHILD A
        tier: critical
        group: mygroup
        description: "a child"
        slo:
          target: 99.0
          window: 30d
          query: "SELECT 100 AS value"
        metrics:
          - key: rps
            query: "SELECT 1.5 AS value"

    edges:
      - from: ext
        to: child_a
""")


class TestLoadConfig:
    def test_loads_minimal_yaml(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert isinstance(cfg, TopologyConfig)
        assert cfg.cache_ttl == 900

    def test_parses_groups(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.groups) == 1
        g = cfg.groups[0]
        assert g.id == "mygroup"
        assert g.children == ["child_a"]
        assert g.slo.target == 99.0

    def test_parses_nodes(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.nodes) == 2
        ext = next(n for n in cfg.nodes if n.id == "ext")
        assert ext.slo is None
        assert ext.metrics[0].static == "a, b"

    def test_node_with_slo_query(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        child = next(n for n in cfg.nodes if n.id == "child_a")
        assert child.slo is not None
        assert child.slo.query == "SELECT 100 AS value"
        assert child.group == "mygroup"

    def test_parses_edges(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.edges) == 1
        assert cfg.edges[0].source == "ext"
        assert cfg.edges[0].target == "child_a"

    def test_node_slo_window_parsed_to_days(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        child = next(n for n in cfg.nodes if n.id == "child_a")
        assert child.slo.window_days == 30
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:observability_config_test --config=ci`
Expected: FAIL

**Step 3: Write the implementation**

Create `projects/monolith/observability/config.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SloConfig:
    target: float
    window_days: int
    query: str | None = None  # None for groups (aggregated)


@dataclass
class MetricConfig:
    key: str
    query: str | None = None
    static: str | None = None
    unit: str | None = None
    format: str | None = None


@dataclass
class SparkConfig:
    query: str


@dataclass
class NodeConfig:
    id: str
    label: str
    tier: str
    description: str
    group: str | None = None
    ingress: bool = False
    slo: SloConfig | None = None
    metrics: list[MetricConfig] = field(default_factory=list)
    spark: SparkConfig | None = None


@dataclass
class GroupConfig:
    id: str
    label: str
    tier: str
    description: str
    children: list[str]
    ingress: bool = False
    slo: SloConfig | None = None


@dataclass
class EdgeConfig:
    source: str
    target: str
    bidi: bool = False


@dataclass
class TopologyConfig:
    cache_ttl: int
    groups: list[GroupConfig]
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]


def _parse_window(window: str) -> int:
    """Parse '30d' -> 30."""
    m = re.match(r"^(\d+)d$", window)
    if not m:
        raise ValueError(f"Invalid window format: {window!r} (expected e.g. '30d')")
    return int(m.group(1))


def _parse_slo(raw: dict | None) -> SloConfig | None:
    if raw is None:
        return None
    return SloConfig(
        target=raw["target"],
        window_days=_parse_window(raw["window"]),
        query=raw.get("query"),
    )


def _parse_metric(raw: dict) -> MetricConfig:
    return MetricConfig(
        key=raw["key"],
        query=raw.get("query"),
        static=raw.get("static"),
        unit=raw.get("unit"),
        format=raw.get("format"),
    )


def load_config(path: Path) -> TopologyConfig:
    """Load and parse topology.yaml."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    groups = []
    for g in raw.get("groups", []):
        groups.append(
            GroupConfig(
                id=g["id"],
                label=g["label"],
                tier=g["tier"],
                description=g["description"],
                children=g["children"],
                ingress=g.get("ingress", False),
                slo=_parse_slo(g.get("slo")),
            )
        )

    nodes = []
    for n in raw.get("nodes", []):
        spark_raw = n.get("spark")
        spark = SparkConfig(query=spark_raw["query"]) if spark_raw else None
        nodes.append(
            NodeConfig(
                id=n["id"],
                label=n["label"],
                tier=n["tier"],
                description=n["description"],
                group=n.get("group"),
                ingress=n.get("ingress", False),
                slo=_parse_slo(n.get("slo")),
                metrics=[_parse_metric(m) for m in n.get("metrics", [])],
                spark=spark,
            )
        )

    edges = []
    for e in raw.get("edges", []):
        edges.append(
            EdgeConfig(
                source=e["from"],
                target=e["to"],
                bidi=e.get("bidi", False),
            )
        )

    return TopologyConfig(
        cache_ttl=raw.get("cache_ttl", 900),
        groups=groups,
        nodes=nodes,
        edges=edges,
    )
```

**Step 4: Add BUILD target**

```starlark
py_test(
    name = "observability_config_test",
    srcs = ["observability/config_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
        "@pip//pyyaml",
    ],
)
```

**Step 5: Run tests, verify pass**

Run: `bb remote test //projects/monolith:observability_config_test --config=ci`
Expected: PASS (6 tests)

**Step 6: Commit**

```
feat(monolith): add topology config loader for SLO dashboard
```

---

### Task 3: SLO Computation + Group Aggregation

**Files:**

- Create: `projects/monolith/observability/slo.py`
- Create: `projects/monolith/observability/slo_test.py`

This module takes raw query results and computes derived fields: status, brief, error budget. It also aggregates groups from children.

**Step 1: Write failing tests**

Create `projects/monolith/observability/slo_test.py`:

```python
import pytest

from observability.slo import (
    compute_status,
    compute_budget,
    compute_brief,
    aggregate_group,
)


class TestComputeStatus:
    def test_healthy_when_above_target(self):
        assert compute_status(current=99.5, target=99.0) == "healthy"

    def test_warning_when_within_half_percent(self):
        assert compute_status(current=98.8, target=99.0) == "warning"

    def test_degraded_when_below_threshold(self):
        assert compute_status(current=98.0, target=99.0) == "degraded"

    def test_healthy_when_exactly_at_target(self):
        assert compute_status(current=99.0, target=99.0) == "healthy"

    def test_no_slo_returns_healthy(self):
        assert compute_status(current=None, target=None) == "healthy"


class TestComputeBudget:
    def test_full_budget_remaining(self):
        budget = compute_budget(
            current=100.0, target=99.0, window_days=30, elapsed_days=15
        )
        assert budget["consumed"] == 0
        assert budget["remaining"] == "432.0 min"
        assert budget["window"] == "30d"

    def test_budget_partially_consumed(self):
        # 99.0% target over 30d = 432 min budget
        # At 98.0%, consumed = 1% * 15 * 1440 = 216 min
        budget = compute_budget(
            current=98.0, target=99.0, window_days=30, elapsed_days=15
        )
        assert budget["consumed"] > 0
        assert float(budget["remaining"].replace(" min", "")) < 432.0

    def test_budget_exhausted(self):
        budget = compute_budget(
            current=95.0, target=99.0, window_days=30, elapsed_days=30
        )
        assert budget["remaining"] == "0 min"


class TestComputeBrief:
    def test_brief_with_slo_and_metric(self):
        brief = compute_brief(availability=99.97, metrics={"rps": "12.5"})
        assert "99.97%" in brief
        assert "12.5 rps" in brief

    def test_brief_slo_only(self):
        brief = compute_brief(availability=100.0, metrics={})
        assert "100%" in brief

    def test_brief_no_slo(self):
        brief = compute_brief(availability=None, metrics={"clients": "a, b"})
        assert "a, b" in brief


class TestAggregateGroup:
    def test_min_availability(self):
        children = [
            {"slo": {"current": 99.5}},
            {"slo": {"current": 100.0}},
            {"slo": {"current": 99.8}},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        assert result["slo"]["current"] == 99.5

    def test_worst_status(self):
        children = [
            {"status": "healthy"},
            {"status": "degraded"},
            {"status": "healthy"},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        assert result["status"] == "degraded"

    def test_sum_rps(self):
        children = [
            {"slo": {"current": 100.0}, "metrics": [{"k": "rps", "v": "5.0"}]},
            {"slo": {"current": 100.0}, "metrics": [{"k": "rps", "v": "3.2"}]},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        rps = next((m for m in result["metrics"] if m["k"] == "rps"), None)
        assert rps is not None
        assert float(rps["v"]) == pytest.approx(8.2, abs=0.1)

    def test_max_p99(self):
        children = [
            {"slo": {"current": 100.0}, "metrics": [{"k": "p99", "v": "42ms"}]},
            {"slo": {"current": 100.0}, "metrics": [{"k": "p99", "v": "180ms"}]},
        ]
        result = aggregate_group(children, target=99.0, window_days=30)
        p99 = next((m for m in result["metrics"] if m["k"] == "p99"), None)
        assert p99 is not None
        assert p99["v"] == "180ms"
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:observability_slo_test --config=ci`
Expected: FAIL

**Step 3: Write the implementation**

Create `projects/monolith/observability/slo.py`:

```python
from __future__ import annotations

import re
from datetime import datetime, timezone


def compute_status(
    current: float | None, target: float | None
) -> str:
    """Derive status from SLO current vs target."""
    if current is None or target is None:
        return "healthy"
    if current >= target:
        return "healthy"
    if current >= target - 0.5:
        return "warning"
    return "degraded"


def compute_budget(
    current: float, target: float, window_days: int, elapsed_days: int | None = None
) -> dict:
    """Compute error budget consumption."""
    if elapsed_days is None:
        # Default: days elapsed since start of window (assume window ends now)
        elapsed_days = window_days

    window_minutes = window_days * 24 * 60
    budget_minutes = window_minutes * (1 - target / 100)
    error_fraction = 1 - current / 100
    consumed_minutes = error_fraction * elapsed_days * 24 * 60
    remaining = max(0.0, budget_minutes - consumed_minutes)
    consumed_pct = min(100, round(consumed_minutes / budget_minutes * 100)) if budget_minutes > 0 else 0

    return {
        "consumed": consumed_pct,
        "elapsed": round(elapsed_days / window_days * 100) if window_days > 0 else 0,
        "remaining": f"{remaining:.1f} min" if remaining > 0 else "0 min",
        "window": f"{window_days}d",
    }


def compute_brief(
    availability: float | None, metrics: dict[str, str]
) -> str:
    """Generate brief summary string."""
    parts = []
    if availability is not None:
        parts.append(f"{availability:.2f}%" if availability < 100 else "100%")
    if "rps" in metrics:
        parts.append(f"{metrics['rps']} rps")
    elif not parts and metrics:
        # No SLO, just show first metric value
        first_val = next(iter(metrics.values()))
        parts.append(str(first_val))
    return " · ".join(parts) if parts else "healthy"


_STATUS_ORDER = {"healthy": 0, "warning": 1, "degraded": 2}


def aggregate_group(
    children: list[dict], target: float, window_days: int
) -> dict:
    """Aggregate child node results into group-level data."""
    # Availability: min of children
    availabilities = [
        c["slo"]["current"]
        for c in children
        if c.get("slo") and c["slo"].get("current") is not None
    ]
    current = min(availabilities) if availabilities else None

    # Status: worst child
    statuses = [c.get("status", "healthy") for c in children]
    worst_status = max(statuses, key=lambda s: _STATUS_ORDER.get(s, 0))

    # Metrics aggregation
    all_metrics = []
    for c in children:
        for m in c.get("metrics", []):
            all_metrics.append(m)

    # Sum rps, max p99
    aggregated_metrics = []
    rps_total = 0.0
    has_rps = False
    p99_max = 0.0
    p99_label = ""
    has_p99 = False

    for m in all_metrics:
        k, v = m["k"], m["v"]
        if k == "rps":
            has_rps = True
            try:
                rps_total += float(v)
            except (ValueError, TypeError):
                pass
        elif k == "p99":
            has_p99 = True
            num = re.sub(r"[^\d.]", "", str(v))
            try:
                val = float(num)
                if val > p99_max:
                    p99_max = val
                    p99_label = str(v)
            except (ValueError, TypeError):
                pass

    if has_rps:
        aggregated_metrics.append({"k": "rps", "v": f"{rps_total:.1f}"})
    if has_p99:
        aggregated_metrics.append({"k": "p99", "v": p99_label})

    result: dict = {"status": worst_status, "metrics": aggregated_metrics}

    if current is not None:
        result["slo"] = {"target": target, "current": current}
        result["budget"] = compute_budget(current, target, window_days)
        metrics_dict = {m["k"]: m["v"] for m in aggregated_metrics}
        result["brief"] = compute_brief(current, metrics_dict)
    else:
        result["brief"] = "healthy"

    return result
```

**Step 4: Add BUILD target**

```starlark
py_test(
    name = "observability_slo_test",
    srcs = ["observability/slo_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//pytest",
    ],
)
```

**Step 5: Run tests, verify pass**

Run: `bb remote test //projects/monolith:observability_slo_test --config=ci`
Expected: PASS

**Step 6: Commit**

```
feat(monolith): add SLO computation and group aggregation logic
```

---

### Task 4: Topology YAML with All Node Queries

**Files:**

- Create: `projects/monolith/observability/topology.yaml`

Write the full topology config with ClickHouse queries for every node. This is the main config file — all SLO definitions live here.

Refer to `docs/plans/2026-04-12-slo-dashboard-design.md` for the node → SLO mapping table and query patterns. Use the validated query patterns from the spike:

- **Container readiness**: `k8s.container.ready` with `max()` per minute, filter by namespace + container name
- **Envoy gateway**: `envoy_cluster_upstream_rq_xx` good/total CTE, only 5xx = bad
- **CNPG up**: `cnpg_collector_up` with `max()` per minute
- **httpcheck**: Not used as primary SLO (conflates failure domains)

All SLO targets: 99.0 (two 9s). Window: 30d.

Groups: monolith (children: home, knowledge, chat), context-forge (children: k8s-mcp, argocd-mcp, signoz-mcp), cluster (children: argocd, signoz, envoy-gateway, longhorn, seaweedfs, otel-operator, linkerd).

Edges: copy from existing `topology.json`.

Nodes without SLO: external, discord (external tier).

**Step 1: Create the file**

Write the full `topology.yaml`. This is a large file — copy the structure from the existing `topology.json` for node metadata (labels, tiers, descriptions) and add `slo.query` and `metrics[].query` fields with the validated ClickHouse SQL.

For container names not yet confirmed (llama-cpp, voyage-embedder, envoy-gateway pod), port-forward ClickHouse and run:

```sql
SELECT DISTINCT
  JSONExtractString(labels, 'k8s.namespace.name') AS ns,
  JSONExtractString(labels, 'k8s.container.name') AS container
FROM signoz_metrics.distributed_time_series_v4
WHERE metric_name = 'k8s.container.ready'
  AND JSONExtractString(labels, 'k8s.namespace.name') IN ('gpu-operator', 'envoy-gateway-system')
  AND JSONExtractString(labels, 'k8s.container.name') != 'linkerd-proxy'
FORMAT PrettyCompact
```

**Step 2: Validate queries by port-forwarding and running each SLO query manually**

```bash
kubectl port-forward -n signoz svc/chi-signoz-clickhouse-cluster-0-0 8123:8123
curl -s 'http://localhost:8123/' --data "<query from yaml>"
```

**Step 3: Commit**

```
feat(monolith): add topology YAML config with live ClickHouse SLO queries
```

---

### Task 5: Router + Topology Builder

**Files:**

- Create: `projects/monolith/observability/router.py`
- Create: `projects/monolith/observability/router_test.py`
- Modify: `projects/monolith/app/main.py` (add router import + include)

The router loads config, runs all queries in parallel, aggregates groups, caches result, returns JSON.

**Step 1: Write failing tests**

Create `projects/monolith/observability/router_test.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:observability_router_test --config=ci`
Expected: FAIL

**Step 3: Write the implementation**

Create `projects/monolith/observability/router.py`:

```python
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter

from observability.clickhouse import ClickHouseClient
from observability.config import load_config, NodeConfig, GroupConfig, TopologyConfig
from observability.slo import aggregate_group, compute_brief, compute_budget, compute_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public/observability", tags=["observability"])

_cache: dict | None = None
_cache_time: float = 0.0
_config: TopologyConfig | None = None


def _get_config() -> TopologyConfig:
    global _config
    if _config is None:
        config_path = Path(__file__).parent / "topology.yaml"
        _config = load_config(config_path)
    return _config


async def _query_node(client: ClickHouseClient, node: NodeConfig) -> dict:
    """Execute all queries for a single node and return topology JSON."""
    result: dict = {
        "id": node.id,
        "label": node.label,
        "tier": node.tier,
        "description": node.description,
    }
    if node.group:
        result["group"] = node.group
    if node.ingress:
        result["ingress"] = True

    # SLO query
    availability = None
    if node.slo and node.slo.query:
        try:
            availability = await client.query_scalar(node.slo.query)
        except Exception:
            logger.exception("SLO query failed for %s", node.id)

    if node.slo:
        result["slo"] = {"target": node.slo.target, "current": availability}
        if availability is not None:
            result["status"] = compute_status(availability, node.slo.target)
            result["budget"] = compute_budget(
                availability, node.slo.target, node.slo.window_days
            )
        else:
            result["status"] = "degraded"
    else:
        result["status"] = "healthy"

    # Metric queries
    metrics = []
    for m in node.metrics:
        if m.static is not None:
            metrics.append({"k": m.key, "v": m.static})
        elif m.query:
            try:
                val = await client.query_scalar(m.query)
                suffix = m.unit or ""
                v = f"{val}{suffix}" if val is not None else "—"
                metrics.append({"k": m.key, "v": v})
            except Exception:
                logger.exception("Metric query failed for %s.%s", node.id, m.key)
                metrics.append({"k": m.key, "v": "—"})
    result["metrics"] = metrics

    # Brief
    metrics_dict = {m["k"]: m["v"] for m in metrics}
    result["brief"] = compute_brief(availability, metrics_dict)

    # Spark query
    if node.spark:
        try:
            rows = await client.query_rows(node.spark.query)
            result["spark"] = [r.get("value", 0) for r in rows]
        except Exception:
            logger.exception("Spark query failed for %s", node.id)

    return result


async def build_topology() -> dict:
    """Execute all queries and build the full topology response."""
    cfg = _get_config()
    ch_url = os.environ.get(
        "CLICKHOUSE_URL",
        "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123",
    )
    client = ClickHouseClient(base_url=ch_url)

    try:
        # Query all nodes in parallel
        node_results = await asyncio.gather(
            *[_query_node(client, n) for n in cfg.nodes],
            return_exceptions=True,
        )

        # Build node lookup, handling exceptions
        nodes = []
        node_map: dict[str, dict] = {}
        for i, r in enumerate(node_results):
            if isinstance(r, Exception):
                logger.error("Node %s failed: %s", cfg.nodes[i].id, r)
                fallback = {
                    "id": cfg.nodes[i].id,
                    "label": cfg.nodes[i].label,
                    "tier": cfg.nodes[i].tier,
                    "description": cfg.nodes[i].description,
                    "status": "degraded",
                    "brief": "query error",
                    "metrics": [],
                }
                if cfg.nodes[i].group:
                    fallback["group"] = cfg.nodes[i].group
                nodes.append(fallback)
                node_map[cfg.nodes[i].id] = fallback
            else:
                nodes.append(r)
                node_map[r["id"]] = r

        # Aggregate groups
        groups = []
        for g in cfg.groups:
            children = [node_map[cid] for cid in g.children if cid in node_map]
            target = g.slo.target if g.slo else 99.0
            window = g.slo.window_days if g.slo else 30
            agg = aggregate_group(children, target, window)

            group_result = {
                "id": g.id,
                "label": g.label,
                "tier": g.tier,
                "description": g.description,
                "children": g.children,
                **agg,
            }
            if g.ingress:
                group_result["ingress"] = True
            groups.append(group_result)

        # Edges
        edges = []
        for e in cfg.edges:
            edge = {"from": e.source, "to": e.target}
            if e.bidi:
                edge["bidi"] = True
            edges.append(edge)

        return {"groups": groups, "nodes": nodes, "edges": edges}
    finally:
        await client.close()


@router.get("/topology")
async def get_topology():
    """Return topology with live metrics, cached for cache_ttl seconds."""
    global _cache, _cache_time
    cfg = _get_config()
    now = time.monotonic()
    if _cache is not None and (now - _cache_time) < cfg.cache_ttl:
        return _cache
    result = await build_topology()
    _cache = result
    _cache_time = now
    return result
```

**Step 4: Register the router in main.py**

Add to `projects/monolith/app/main.py` — import + include alongside existing routers:

```python
from observability.router import router as observability_router
# ...
app.include_router(observability_router)
```

**Step 5: Add BUILD target**

```starlark
py_test(
    name = "observability_router_test",
    srcs = ["observability/router_test.py"],
    imports = ["."],
    deps = [
        ":monolith_backend",
        "@pip//fastapi",
        "@pip//httpx",
        "@pip//pytest",
    ],
)
```

**Step 6: Run tests, verify pass**

Run: `bb remote test //projects/monolith:observability_router_test --config=ci`
Expected: PASS

**Step 7: Commit**

```
feat(monolith): add observability router with cached ClickHouse topology
```

---

### Task 6: Frontend Route Change

**Files:**

- Rename: `projects/monolith/frontend/src/routes/public/observability-demo/` → `projects/monolith/frontend/src/routes/public/slos/`
- Modify: `projects/monolith/frontend/src/routes/public/slos/+page.ts` (add data fetch)
- Modify: `projects/monolith/frontend/src/routes/public/slos/+page.svelte` (use fetched data instead of static import)
- Delete: `projects/monolith/frontend/src/routes/public/slos/topology.json` (no longer needed — data comes from API)

**Step 1: Move the directory**

```bash
git mv projects/monolith/frontend/src/routes/public/observability-demo \
       projects/monolith/frontend/src/routes/public/slos
```

**Step 2: Update +page.ts to fetch from API**

Replace `projects/monolith/frontend/src/routes/public/slos/+page.ts`:

```typescript
export const ssr = false;

export async function load({ fetch }) {
  const resp = await fetch("/api/public/observability/topology");
  if (!resp.ok) {
    // Fall back to empty topology on error
    return { topology: { groups: [], nodes: [], edges: [] } };
  }
  const topology = await resp.json();
  return { topology };
}
```

**Step 3: Update +page.svelte to use fetched data**

In `+page.svelte`, change the top of the `<script>` block:

Replace:

```javascript
import topology from "./topology.json";
```

With:

```javascript
let { data } = $props();
const topology = data.topology;
```

**Step 4: Delete topology.json**

```bash
git rm projects/monolith/frontend/src/routes/public/slos/topology.json
```

**Step 5: Verify the frontend builds**

Run: `bb remote test //projects/monolith/frontend:build --config=ci`
Expected: PASS (or build completes without error)

**Step 6: Commit**

```
feat(monolith): move observability page to /slos with live API data
```

---

### Task 7: Deploy Configuration

**Files:**

- Modify: `projects/monolith/deploy/values.yaml` (add CLICKHOUSE_URL env var)
- Modify: `projects/monolith/chart/Chart.yaml` (bump version)
- Modify: `projects/monolith/deploy/application.yaml` (bump targetRevision to match)

**Step 1: Add CLICKHOUSE_URL to values.yaml**

Add under `backend:`:

```yaml
backend:
  clickhouseUrl: "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123"
```

Ensure this is wired through the chart's deployment template as an env var `CLICKHOUSE_URL`. Check `projects/monolith/chart/templates/deployment.yaml` for the existing env var pattern and add:

```yaml
- name: CLICKHOUSE_URL
  value: { { .Values.backend.clickhouseUrl | quote } }
```

**Step 2: Bump chart version**

Bump `version` in `projects/monolith/chart/Chart.yaml` and match `targetRevision` in `projects/monolith/deploy/application.yaml`.

**Step 3: Commit**

```
feat(monolith): add ClickHouse URL config for SLO dashboard
```

---

### Task 8: Run All Tests + Integration Verification

**Step 1: Run all monolith tests**

```bash
bb remote test //projects/monolith/... --config=ci
```

Expected: All tests pass, including new observability tests.

**Step 2: Run format**

```bash
format
```

This will update BUILD files (gazelle) and format code.

**Step 3: Verify the full topology endpoint locally (optional)**

Port-forward ClickHouse and run the monolith locally:

```bash
kubectl port-forward -n signoz svc/chi-signoz-clickhouse-cluster-0-0 8123:8123 &
CLICKHOUSE_URL=http://localhost:8123 python -m uvicorn app.main:app --port 8000
curl localhost:8000/api/public/observability/topology | python -m json.tool
```

**Step 4: Final commit if format changed anything**

```
style: auto-format
```

**Step 5: Push and create PR**

```bash
git push -u origin feat/slo-dashboard
gh pr create --title "feat(monolith): live SLO dashboard with ClickHouse queries" \
  --body "$(cat <<'EOF'
## Summary
- Adds FastAPI backend module that queries SigNoz ClickHouse for live SLO data
- YAML config defines topology nodes with raw ClickHouse SQL per service
- Four query strategies: container readiness, envoy gateway success rate, CNPG up, httpcheck
- Groups aggregate SLO from children (min availability, sum rps, max p99)
- 15m in-memory cache, no new dependencies (httpx + pyyaml already in tree)
- Frontend moves from /public/observability-demo to /public/slos, fetches from API

## Design
See `docs/plans/2026-04-12-slo-dashboard-design.md`

## Test plan
- [ ] Unit tests for ClickHouse client (mock transport)
- [ ] Unit tests for config loader
- [ ] Unit tests for SLO computation + group aggregation
- [ ] Unit tests for router (mock build_topology)
- [ ] Manual: port-forward ClickHouse, verify all queries return data
- [ ] Manual: verify /public/slos renders with live data after deploy

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
