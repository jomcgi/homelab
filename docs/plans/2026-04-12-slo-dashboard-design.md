# SLO Dashboard — Live Observability Data for Topology DAG

## Problem

The observability-demo page at `public.jomcgi.dev` displays a topology DAG of homelab services with SLO data, but all values are hardcoded in `topology.json`. There is no live data backing the availability percentages, latency numbers, or error budgets. The existing SLO alert library (`signoz-addons/alerts`) only does single-metric threshold alerting — it doesn't compute availability ratios or produce dashboards.

## Solution

A FastAPI backend module that reads a YAML topology config, executes ClickHouse queries against SigNoz's database, and returns live SLO + metric data. The frontend fetches this instead of importing a static JSON file. The page moves to `public.jomcgi.dev/slos`.

## Architecture

```
topology.yaml ──► FastAPI router ──► ClickHouse (HTTP :8123) ──► JSON response
                       │                                              │
                  15m in-memory cache                         Same shape as
                                                              topology.json
                                                                      │
                                                              SvelteKit page
                                                              (client-side fetch)
```

### Data Flow

1. On first request (or cache miss), the backend loads `topology.yaml`
2. Executes all leaf node SLO + metric queries against ClickHouse in parallel
3. For groups: aggregates children's results (min availability, sum rps, max p99)
4. Computes derived fields: `status`, `brief`, `budget` (from SLO target vs actual)
5. Caches the full response for 15 minutes
6. Returns JSON matching the existing `topology.json` shape

### ClickHouse Connection

Direct HTTP POST to `chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123` using `httpx.AsyncClient`. No auth needed (cluster-internal). No ClickHouse client library — raw SQL over HTTP.

## YAML Config Shape

All queries are raw ClickHouse SQL. Every query must return a `value` column (first row extracted). Spark queries return multiple rows with `bucket` + `value`.

```yaml
cache_ttl: 900 # seconds

groups:
  - id: monolith
    label: MONOLITH
    tier: critical
    ingress: true
    description: "fastapi + sveltekit"
    children: [home, knowledge, chat]
    slo:
      target: 99.0
      window: 30d
      # No query — aggregated from children

nodes:
  - id: external
    label: EXTERNAL
    tier: ingress
    description: "webpage · claude · cli"
    metrics:
      - key: clients
        static: "webpage, claude, cli"

  - id: home
    group: monolith
    label: HOME
    tier: critical
    description: "dashboard + notes + schedule"
    slo:
      target: 99.0
      window: 30d
      query: |
        WITH bad AS (...), total AS (...)
        SELECT round((1 - sum(coalesce(b.v,0)) / sum(t.v)) * 100, 4) AS value
        FROM total t LEFT JOIN bad b ON t.mb = b.mb
    metrics:
      - key: rps
        query: "SELECT ... AS value"

edges:
  - from: external
    to: cloudflare
```

## SLO Query Strategies

Four proven patterns, validated against live ClickHouse data:

### 1. Container Readiness (uptime)

For services without HTTP traffic metrics. Uses `k8s.container.ready` from the OTel k8sclusterreceiver. The `max()` per minute handles stale series from old collector pods.

```sql
WITH per_minute AS (
  SELECT intDiv(s.unix_milli, 60000) AS mb, max(s.value) AS ready
  FROM signoz_metrics.distributed_samples_v4 s
  WHERE s.fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4
    WHERE metric_name = 'k8s.container.ready'
      AND JSONExtractString(labels, 'k8s.namespace.name') = '{namespace}'
      AND JSONExtractString(labels, 'k8s.container.name') = '{container}'
  ) AND s.unix_milli >= toUnixTimestamp(now() - INTERVAL 30 DAY) * 1000
  GROUP BY mb
)
SELECT round(countIf(ready >= 1) / count() * 100, 4) AS value FROM per_minute
```

**Used by:** cloudflare, nats, llama-cpp, voyage-embedder, k8s-mcp, argocd-mcp, signoz-mcp, argocd, signoz, envoy-gateway, longhorn, seaweedfs, otel-operator, linkerd

### 2. Envoy Gateway Success Rate (no 5xx)

For services routed through envoy-gateway. Counts 5xx responses as errors, 2xx/3xx/4xx as good (4xx are client errors, not service failures).

```sql
WITH
bad AS (
  SELECT intDiv(unix_milli, 60000) AS mb, sum(value) AS v
  FROM signoz_metrics.distributed_samples_v4
  WHERE fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4
    WHERE metric_name = 'envoy_cluster_upstream_rq_xx'
      AND JSONExtractString(labels, 'envoy_cluster_name') LIKE '%{route}%'
      AND JSONExtractString(labels, 'envoy_response_code_class') = '5'
  ) AND unix_milli >= toUnixTimestamp(now() - INTERVAL 30 DAY) * 1000
  GROUP BY mb
),
total AS (
  SELECT intDiv(unix_milli, 60000) AS mb, sum(value) AS v
  FROM signoz_metrics.distributed_samples_v4
  WHERE fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4
    WHERE metric_name = 'envoy_cluster_upstream_rq_xx'
      AND JSONExtractString(labels, 'envoy_cluster_name') LIKE '%{route}%'
  ) AND unix_milli >= toUnixTimestamp(now() - INTERVAL 30 DAY) * 1000
  GROUP BY mb
)
SELECT round((1 - sum(coalesce(b.v, 0)) / sum(t.v)) * 100, 4) AS value
FROM total t LEFT JOIN bad b ON t.mb = b.mb
```

**Used by:** home, knowledge, chat (monolith-public/private), agent-platform, context-forge

### 3. CNPG Collector Up (database)

For CloudNativePG-managed Postgres instances.

```sql
WITH per_minute AS (
  SELECT intDiv(s.unix_milli, 60000) AS mb, max(s.value) AS up
  FROM signoz_metrics.distributed_samples_v4 s
  WHERE s.fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4
    WHERE metric_name = 'cnpg_collector_up'
  ) AND s.unix_milli >= toUnixTimestamp(now() - INTERVAL 30 DAY) * 1000
  GROUP BY mb
)
SELECT round(countIf(up >= 1) / count() * 100, 4) AS value FROM per_minute
```

**Used by:** postgres

### 4. HTTPCheck Status (synthetic probes)

Available for 12 URLs but **not used as primary SLO** — httpcheck goes through the full ingress chain (tunnel → envoy → service), conflating failure domains. Kept as an optional supplementary metric.

## Node → SLO Mapping

All targets set to 99% (two 9s).

| Node                            | Strategy          | Readiness key                          |
| ------------------------------- | ----------------- | -------------------------------------- |
| external, discord               | No SLO (external) | —                                      |
| cloudflare                      | container ready   | `envoy-gateway-system` / `cloudflared` |
| home                            | envoy rq_xx       | `monolith-public`                      |
| knowledge                       | envoy rq_xx       | `monolith-private`                     |
| chat                            | envoy rq_xx       | `monolith-private`                     |
| postgres                        | cnpg_collector_up | —                                      |
| nats                            | container ready   | `nats` / `nats`                        |
| agent-platform                  | envoy rq_xx       | `agent-orchestrator`                   |
| llama-cpp                       | container ready   | TBD                                    |
| voyage-embedder                 | container ready   | TBD                                    |
| k8s-mcp, argocd-mcp, signoz-mcp | container ready   | `mcp` namespace                        |
| argocd                          | container ready   | `argocd` / `application-controller`    |
| signoz                          | container ready   | `signoz` / `signoz`                    |
| envoy-gateway                   | container ready   | `envoy-gateway-system` / TBD           |
| longhorn                        | container ready   | `longhorn` / `longhorn-manager`        |
| seaweedfs                       | container ready   | `seaweedfs` / `seaweedfs`              |
| otel-operator                   | container ready   | `opentelemetry-operator` / `manager`   |
| linkerd                         | container ready   | `linkerd` / `linkerd-proxy`            |

## Group Aggregation

Groups have no queries. Their values are computed from children:

| Field          | Aggregation                                           | Reasoning                            |
| -------------- | ----------------------------------------------------- | ------------------------------------ |
| `slo.current`  | `min(children)`                                       | Weakest link determines group health |
| `status`       | Worst child status                                    | degraded child → degraded group      |
| `rps` (metric) | `sum(children)`                                       | Total throughput                     |
| `p99` (metric) | `max(children)`                                       | Worst-case user experience           |
| `budget`       | Computed from aggregated availability vs group target |                                      |

## Status Derivation

Computed from SLO current vs target:

- `healthy`: current >= target
- `warning`: current >= target - 0.5% (within 0.5% of target)
- `degraded`: current < target - 0.5%

## Error Budget Computation

```python
window_minutes = window_days * 24 * 60
budget_minutes = window_minutes * (1 - target / 100)  # total allowed downtime
elapsed_fraction = elapsed_days / window_days
consumed_fraction = 1 - (current / 100)  # fraction of time in error
consumed_minutes = consumed_fraction * elapsed_days * 24 * 60
remaining_minutes = budget_minutes - consumed_minutes
```

## Backend Module Structure

```
projects/monolith/observability/
├── __init__.py
├── router.py          # GET /api/public/observability/topology
├── clickhouse.py      # async query execution via httpx
├── topology.yaml      # the config
└── router_test.py     # unit tests with mocked ClickHouse responses
```

### Router

```python
router = APIRouter(prefix="/api/public/observability", tags=["observability"])

@router.get("/topology")
async def get_topology():
    """Returns topology with live metrics, cached for 15m."""
    return await get_cached_topology()
```

### ClickHouse Client

Minimal — `httpx.AsyncClient` POST to ClickHouse HTTP interface with `FORMAT JSON` suffix. Returns parsed rows. No connection pooling needed at 15m cache intervals.

### Caching

Simple `time.monotonic()` check against `cache_ttl`. Single cached dict, refreshed on expiry. No background refresh — the request that hits an expired cache pays the query cost (~1-2s for all queries in parallel).

## Frontend Changes

1. Move page from `/public/observability-demo` to `/public/slos`
2. Replace `import topology from "./topology.json"` with `fetch("/api/public/observability/topology")`
3. Add loading state while data fetches
4. Keep `ssr = false` (client-side only)
5. The JSON shape is identical — no component changes needed beyond the data source

## ClickHouse Query Constraints

Discovered during spike:

- **Never JOIN samples ↔ time_series directly** — OOMs at ~4.8 GiB. Always use `fingerprint IN (SELECT ... FROM time_series WHERE ...)` subqueries.
- **Always `max()` per time bucket** — stale series from dead collector pods produce 0 values that poison averages.
- **Cumulative counters (envoy rq_xx)** need good/total CTE pattern with separate fingerprint sets per response code class.

## Scope Boundaries

**In scope:**

- FastAPI backend module with ClickHouse queries
- YAML topology config with raw SQL per node
- Group aggregation from children
- 15m cached response
- Frontend route change to `/slos`

**Out of scope:**

- Query templates / abstraction layer (start with raw SQL, refactor when patterns emerge)
- Alert generation from SLO data (existing alert library handles this separately)
- Historical SLO tracking / trend graphs
- Authentication (public endpoint, read-only, no sensitive data)
