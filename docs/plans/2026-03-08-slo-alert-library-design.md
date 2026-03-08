# SigNoz SLO Alert Library Chart

## Problem

Alert noise from poorly tuned thresholds. The current approach (hand-written SigNoz alert ConfigMaps per service) leads to duplicated JSON, inconsistent aggregation strategies, and no error-budget-based reasoning. PR #883 fixed the immediate issues (stale series poisoning `avg`, cumulative counters never clearing), but the underlying pattern — manually defining thresholds — doesn't scale.

## Solution

A Helm **library chart** (`charts/signoz-alerts/`) that generates SigNoz alert ConfigMaps from SLO definitions. Consumers declare availability targets; the chart computes burn-rate thresholds using multi-window multi-burn-rate (MWMB) math from Google's SRE workbook.

## Why not Sloth.dev directly?

Sloth outputs PrometheusRules with PromQL. SigNoz uses ClickHouse with its own builder query format (v5) — no Prometheus server, no recording rules, no Alertmanager. Deploying Prometheus solely for recording rules adds ~2Gi memory and operational complexity for no benefit at homelab scale. Instead, we compute burn rates inline at alert eval time.

## Design

### Input

SLO definitions in a consuming chart's `values.yaml`:

```yaml
slos:
  - name: api-gateway
    metric: httpcheck.status
    filter: "http.url = 'https://api.jomcgi.dev/status.json'"
    op: "2"             # comparison operator: "2" = less than (default)
    threshold: 1        # value to compare against
    severity: critical  # optional (default: critical)
    channels:           # notification channels
      - incidentio
```

### Output

Two SigNoz alert ConfigMaps per SLO, labeled `signoz.io/alert: "true"` for the existing signoz-dashboard-sidecar to reconcile:

1. **`<name>-slo-burn-fast`** — High burn rate detected. Something is actively broken. Short eval window (5m), fires when the condition is sustained for the full window (`matchType: "3"`).

2. **`<name>-slo-budget-exhausted`** — Error budget consumed. Accumulated errors over a longer window (6h) indicate the budget is on track to be fully spent. Fires when sustained (`matchType: "3"`).

### Burn-Rate Math

For a 7-day SLO window at 99.9% target:

- **Error budget:** 0.1% of 7 days = ~10.08 minutes of downtime
- **Burn-fast alert:** 14.4x burn rate factor. At this rate, the full 7-day budget would be consumed in ~11.7 hours. Detection window: 5m eval / 1m frequency.
- **Budget-exhausted alert:** 1x burn rate factor. Budget is being consumed at exactly the rate that would exhaust it by end of window. Detection window: 6h eval / 5m frequency.

The burn rate determines whether the metric violates the threshold — it doesn't modify the threshold value itself. Both alerts use the same `op`, `threshold`, and `metric`. The difference is the eval window duration and how sustained the violation must be.

### Chart Structure

```
charts/signoz-alerts/
├── Chart.yaml          # type: library, version: 0.1.0
├── templates/
│   └── _slo.tpl        # {{- define "signoz-alerts.slo" }} — generates burn-fast + budget-exhausted alerts
└── values.yaml         # defaults: severity=critical, channels=[incidentio]
```

### Alert ConfigMap Format

Follows the SigNoz v0.113 v5 query builder format documented in `architecture/observability-alerting.md`. Key details:

- `spaceAggregation: "max"` — resilient to stale metric series from previous collector pod incarnations
- Thresholds defined in both legacy condition-level fields and `thresholds` block (both required per v0.113 behavior)
- `version: "v5"` with `queries` array format

### Consumer Integration

Any chart adds the library as a dependency:

```yaml
# Chart.yaml
dependencies:
  - name: signoz-alerts
    version: "0.1.0"
    repository: "file://../signoz-alerts"
```

Then includes the template:

```yaml
# templates/slo-alerts.yaml
{{- range .Values.slos }}
{{ include "signoz-alerts.slo" (dict "slo" . "Chart" $.Chart "Release" $.Release "defaults" $.Values.sloDefaults) }}
{{- end }}
```

### Migration Path

The 11 existing httpcheck alert ConfigMaps can be replaced with SLO definitions in each service's values.yaml. The hand-written alert YAML files in overlays get deleted. Migration is incremental — both old-style and SLO alerts can coexist during transition.

### Scope Boundaries

- **In scope:** SLO-based alerts with burn-rate math, library chart, SigNoz v5 query format
- **Out of scope:** Vanilla alerts (keep hand-written), heartbeat/dead-man's-switch alerts, OpenSLO CRD input format (use Helm values), Grafana dashboard generation
- **Future:** Could add OpenSLO YAML parsing via a CLI tool if the Helm template approach becomes limiting
