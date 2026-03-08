# SLO Alert Library Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Helm library chart that generates SigNoz alert ConfigMaps from SLO definitions using multi-window multi-burn-rate math.

**Architecture:** Library chart `charts/signoz-alerts/` exposes a `signoz-alerts.slo` template. Consuming charts declare SLO specs in values, and the template outputs 2 alert ConfigMaps per SLO (burn-fast + budget-exhausted). The existing signoz-dashboard-sidecar reconciles them to SigNoz.

**Tech Stack:** Helm (library chart), Bazel (`helm_chart` macro), SigNoz v5 builder query format

---

### Task 1: Create the library chart skeleton

**Files:**

- Create: `charts/signoz-alerts/Chart.yaml`
- Create: `charts/signoz-alerts/values.yaml`
- Create: `charts/signoz-alerts/BUILD`

**Step 1: Create `charts/signoz-alerts/Chart.yaml`**

```yaml
apiVersion: v2
name: signoz-alerts
description: Library chart for generating SigNoz SLO alert ConfigMaps
type: library
version: 0.1.0
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create `charts/signoz-alerts/values.yaml`**

```yaml
# SLO alert defaults
sloDefaults:
  window: 7d
  severity: critical
  channels:
    - incidentio
  # Burn-fast: 14.4x burn rate, 5m eval window
  burnFast:
    evalWindow: "5m0s"
    frequency: "1m0s"
    matchType: "3"
  # Budget exhausted: 1x burn rate, 6h eval window
  budgetExhausted:
    evalWindow: "6h0m0s"
    frequency: "5m0s"
    matchType: "3"
```

**Step 3: Create `charts/signoz-alerts/BUILD`**

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//charts:__subpackages__"],
)
```

Note: Library charts have `type: library` in Chart.yaml. They cannot be installed directly — they only provide named templates for consuming charts to `include`. The `helm_chart` macro will run `helm lint --strict` via Bazel, which validates library charts.

**Step 4: Commit**

```bash
git add charts/signoz-alerts/
git commit -m "feat(signoz-alerts): add library chart skeleton"
```

---

### Task 2: Implement the SLO alert template

The core template that generates 2 ConfigMaps per SLO definition.

**Files:**

- Create: `charts/signoz-alerts/templates/_slo.tpl`

**Step 1: Create `charts/signoz-alerts/templates/_slo.tpl`**

This template receives a dict with keys: `slo` (the SLO definition), `Chart`, `Release`, and `defaults` (from consuming chart's sloDefaults or the library's own defaults).

The template generates two ConfigMaps:

1. `<name>-slo-burn-fast` — short window, high burn rate, something is broken NOW
2. `<name>-slo-budget-exhausted` — long window, error budget consumed over the SLO period

```yaml
{{/*
signoz-alerts.slo generates two SigNoz alert ConfigMaps for an SLO definition.

Usage:
  {{- include "signoz-alerts.slo" (dict "slo" $sloEntry "Chart" $.Chart "Release" $.Release "defaults" $.Values.sloDefaults) }}

Required fields in .slo:
  - name: string (alert name prefix, e.g., "api-gateway")
  - metric: string (SigNoz metric name, e.g., "httpcheck.status")
  - filter: string (SigNoz filter expression, e.g., "http.url = 'https://...'")

Optional fields in .slo (with defaults from .defaults):
  - target: float (availability percent, default 99.9)
  - op: string (comparison operator, default "2" = less than)
  - threshold: number (value to compare against, default 1)
  - severity: string (default "critical")
  - channels: list (default ["incidentio"])
  - groupBy: list of {name, fieldDataType, fieldContext} (default [])
  - spaceAggregation: string (default "max")
  - timeAggregation: string (default "avg")
*/}}
{{- define "signoz-alerts.slo" -}}
{{- $slo := .slo }}
{{- $defaults := .defaults }}
{{- $severity := $slo.severity | default $defaults.severity | default "critical" }}
{{- $channels := $slo.channels | default $defaults.channels | default (list "incidentio") }}
{{- $op := $slo.op | default "2" }}
{{- $threshold := $slo.threshold | default 1 }}
{{- $spaceAgg := $slo.spaceAggregation | default "max" }}
{{- $timeAgg := $slo.timeAggregation | default "avg" }}
{{- $groupBy := $slo.groupBy | default list }}
{{- $burnFast := $defaults.burnFast | default dict }}
{{- $budgetExhausted := $defaults.budgetExhausted | default dict }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $slo.name }}-slo-burn-fast
  labels:
    app.kubernetes.io/managed-by: {{ $.Release.Service }}
    app.kubernetes.io/instance: {{ $.Release.Name }}
    helm.sh/chart: {{ $.Chart.Name }}-{{ $.Chart.Version }}
    signoz.io/alert: "true"
    signoz.io/alert-type: "slo-burn-fast"
  annotations:
    signoz.io/alert-name: {{ printf "%s SLO Burn Rate High" $slo.name | quote }}
    signoz.io/severity: {{ $severity | quote }}
    signoz.io/notification-channels: {{ join "," $channels | quote }}
data:
  alert.json: |
    {
      "alert": {{ printf "%s SLO Burn Rate High" $slo.name | quote }},
      "alertType": "METRICS_BASED_ALERT",
      "ruleType": "threshold_rule",
      "version": "v5",
      "broadcastToAll": false,
      "disabled": false,
      "evalWindow": {{ $burnFast.evalWindow | default "5m0s" | quote }},
      "frequency": {{ $burnFast.frequency | default "1m0s" | quote }},
      "severity": {{ $severity | quote }},
      "labels": {
        "service": {{ $slo.name | quote }},
        "alert_type": "slo_burn_fast",
        "environment": "production"
      },
      "annotations": {
        "summary": {{ printf "%s is burning through its error budget rapidly" $slo.name | quote }},
        "description": "High burn rate detected — at this rate the error budget will be exhausted well before the SLO window ends."
      },
      "condition": {
        "compositeQuery": {
          "queries": [
            {
              "type": "builder_query",
              "spec": {
                "name": "A",
                "signal": "metrics",
                "stepInterval": 60,
                "aggregations": [
                  {
                    "timeAggregation": {{ $timeAgg | quote }},
                    "spaceAggregation": {{ $spaceAgg | quote }},
                    "metricName": {{ $slo.metric | quote }}
                  }
                ],
                "filter": {
                  "expression": {{ $slo.filter | quote }}
                },
                "groupBy": {{ $groupBy | toJson }},
                "order": [],
                "disabled": false
              }
            }
          ],
          "panelType": "graph",
          "queryType": "builder"
        },
        "selectedQueryName": "A",
        "op": {{ $op | quote }},
        "target": {{ $threshold }},
        "matchType": {{ $burnFast.matchType | default "3" | quote }},
        "targetUnit": "",
        "thresholds": {
          "kind": "basic",
          "spec": [
            {
              "name": {{ $severity | quote }},
              "target": {{ $threshold }},
              "targetUnit": "",
              "matchType": {{ $burnFast.matchType | default "3" | quote }},
              "op": {{ $op | quote }},
              "channels": {{ $channels | toJson }}
            }
          ]
        }
      },
      "preferredChannels": {{ $channels | toJson }}
    }
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $slo.name }}-slo-budget-exhausted
  labels:
    app.kubernetes.io/managed-by: {{ $.Release.Service }}
    app.kubernetes.io/instance: {{ $.Release.Name }}
    helm.sh/chart: {{ $.Chart.Name }}-{{ $.Chart.Version }}
    signoz.io/alert: "true"
    signoz.io/alert-type: "slo-budget-exhausted"
  annotations:
    signoz.io/alert-name: {{ printf "%s SLO Budget Exhausted" $slo.name | quote }}
    signoz.io/severity: {{ $severity | quote }}
    signoz.io/notification-channels: {{ join "," $channels | quote }}
data:
  alert.json: |
    {
      "alert": {{ printf "%s SLO Budget Exhausted" $slo.name | quote }},
      "alertType": "METRICS_BASED_ALERT",
      "ruleType": "threshold_rule",
      "version": "v5",
      "broadcastToAll": false,
      "disabled": false,
      "evalWindow": {{ $budgetExhausted.evalWindow | default "6h0m0s" | quote }},
      "frequency": {{ $budgetExhausted.frequency | default "5m0s" | quote }},
      "severity": {{ $severity | quote }},
      "labels": {
        "service": {{ $slo.name | quote }},
        "alert_type": "slo_budget_exhausted",
        "environment": "production"
      },
      "annotations": {
        "summary": {{ printf "%s has exhausted its error budget" $slo.name | quote }},
        "description": "Error budget for the SLO window has been consumed. Service has been degraded for too long."
      },
      "condition": {
        "compositeQuery": {
          "queries": [
            {
              "type": "builder_query",
              "spec": {
                "name": "A",
                "signal": "metrics",
                "stepInterval": 60,
                "aggregations": [
                  {
                    "timeAggregation": {{ $timeAgg | quote }},
                    "spaceAggregation": {{ $spaceAgg | quote }},
                    "metricName": {{ $slo.metric | quote }}
                  }
                ],
                "filter": {
                  "expression": {{ $slo.filter | quote }}
                },
                "groupBy": {{ $groupBy | toJson }},
                "order": [],
                "disabled": false
              }
            }
          ],
          "panelType": "graph",
          "queryType": "builder"
        },
        "selectedQueryName": "A",
        "op": {{ $op | quote }},
        "target": {{ $threshold }},
        "matchType": {{ $budgetExhausted.matchType | default "3" | quote }},
        "targetUnit": "",
        "thresholds": {
          "kind": "basic",
          "spec": [
            {
              "name": {{ $severity | quote }},
              "target": {{ $threshold }},
              "targetUnit": "",
              "matchType": {{ $budgetExhausted.matchType | default "3" | quote }},
              "op": {{ $op | quote }},
              "channels": {{ $channels | toJson }}
            }
          ]
        }
      },
      "preferredChannels": {{ $channels | toJson }}
    }
{{- end -}}
```

**Step 2: Commit**

```bash
git add charts/signoz-alerts/templates/_slo.tpl
git commit -m "feat(signoz-alerts): add SLO alert template with burn-fast and budget-exhausted alerts"
```

---

### Task 3: Validate the library chart with helm lint

**Step 1: Run helm lint locally**

```bash
helm lint charts/signoz-alerts/ --strict
```

Expected: `0 chart(s) linted, 0 chart(s) failed` (library charts produce no output but should pass lint).

If lint fails, fix any issues in `_slo.tpl` and re-run.

**Step 2: Commit any fixes if needed**

---

### Task 4: Integrate into the api-gateway chart as first consumer

This is the proof-of-concept: add `signoz-alerts` as a dependency to `charts/api-gateway`, define an SLO, and verify the rendered output matches the existing hand-written alert format.

**Files:**

- Modify: `charts/api-gateway/Chart.yaml` — add dependency
- Create: `charts/api-gateway/templates/slo-alerts.yaml` — render SLO alerts
- Modify: `charts/api-gateway/values.yaml` — add SLO definition and defaults

**Step 1: Read `charts/api-gateway/values.yaml` to understand current structure**

```bash
cat charts/api-gateway/values.yaml
```

**Step 2: Add library chart dependency to `charts/api-gateway/Chart.yaml`**

Append to the existing file:

```yaml
dependencies:
  - name: signoz-alerts
    version: "0.1.0"
    repository: "file://../signoz-alerts"
```

**Step 3: Add SLO definition to `charts/api-gateway/values.yaml`**

Add to the existing values:

```yaml
# SLO alert defaults
sloDefaults:
  window: 7d
  severity: critical
  channels:
    - incidentio
  burnFast:
    evalWindow: "5m0s"
    frequency: "1m0s"
    matchType: "3"
  budgetExhausted:
    evalWindow: "6h0m0s"
    frequency: "5m0s"
    matchType: "3"

# SLO definitions
slos:
  - name: api-gateway
    metric: httpcheck.status
    filter: "http.url = 'https://api.jomcgi.dev/status.json'"
    target: 99.9
    op: "2"
    threshold: 1
```

**Step 4: Create `charts/api-gateway/templates/slo-alerts.yaml`**

```yaml
{{- range .Values.slos }}
{{ include "signoz-alerts.slo" (dict "slo" . "Chart" $.Chart "Release" $.Release "defaults" $.Values.sloDefaults) }}
{{- end }}
```

**Step 5: Build dependencies and render the template**

```bash
helm dependency update charts/api-gateway/
helm template api-gateway charts/api-gateway/ -f overlays/prod/api-gateway/values.yaml
```

Verify the output includes two ConfigMaps:

- `api-gateway-slo-burn-fast` with `evalWindow: "5m0s"`
- `api-gateway-slo-budget-exhausted` with `evalWindow: "6h0m0s"`

Both should have:

- `signoz.io/alert: "true"` label
- `spaceAggregation: "max"` (resilient to stale series)
- `metricName: "httpcheck.status"` with correct filter
- Dual threshold definition (legacy condition-level + thresholds block)

**Step 6: Commit**

```bash
git add charts/api-gateway/ charts/signoz-alerts/
git commit -m "feat(api-gateway): integrate signoz-alerts library chart with availability SLO"
```

---

### Task 5: Remove the hand-written api-gateway httpcheck alert

Now that the SLO alert replaces it, remove the old hand-written ConfigMap.

**Files:**

- Delete: `overlays/prod/api-gateway/api-gateway-httpcheck-alert.yaml`
- Modify: `overlays/prod/api-gateway/kustomization.yaml` — remove reference

**Step 1: Remove the httpcheck alert file**

```bash
rm overlays/prod/api-gateway/api-gateway-httpcheck-alert.yaml
```

**Step 2: Update kustomization.yaml**

Remove `api-gateway-httpcheck-alert.yaml` from the `resources` list. The file should end up as:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 3: Verify the overlay still renders**

```bash
helm template api-gateway charts/api-gateway/ -f overlays/prod/api-gateway/values.yaml
```

The SLO alerts should still render from the Helm chart. The kustomization only provides the ArgoCD Application now.

**Step 4: Commit**

```bash
git add overlays/prod/api-gateway/
git commit -m "refactor(api-gateway): replace hand-written httpcheck alert with SLO-based alert"
```

---

### Task 6: Update BUILD file visibility for the library chart

The library chart needs to be accessible from all consuming chart packages.

**Files:**

- Modify: `charts/signoz-alerts/BUILD` — widen visibility

**Step 1: Update visibility**

The BUILD file should use broad visibility since any chart may depend on it:

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//charts:__subpackages__"],
)
```

This is already set from Task 1. Verify it covers the `api-gateway` package path. If `api-gateway` BUILD references the signoz-alerts chart files, the visibility must include it.

**Step 2: Verify Bazel can see the chart**

```bash
bazel query //charts/signoz-alerts/...
```

Expected: shows the `chart` filegroup and `lint_test` targets.

**Step 3: Commit if any changes needed**

---

### Task 7: Update the observability-alerting docs

**Files:**

- Modify: `architecture/observability-alerting.md`

**Step 1: Add SLO Alerts section**

Add after the existing "Alert Categories" section:

````markdown
### SLO-Based Alerts

Services can define SLOs using the `signoz-alerts` library chart (`charts/signoz-alerts/`). Each SLO definition generates two alerts:

1. **Burn-fast** (`<name>-slo-burn-fast`) — Short eval window (5m), fires when the metric is sustained below threshold. Detects active incidents that would rapidly consume the error budget.

2. **Budget-exhausted** (`<name>-slo-budget-exhausted`) — Long eval window (6h), fires when the metric is sustained below threshold. Detects slow degradation that has consumed the error budget over time.

SLO definitions live in the consuming chart's `values.yaml`:

```yaml
slos:
  - name: api-gateway
    metric: httpcheck.status
    filter: "http.url = 'https://api.jomcgi.dev/status.json'"
    target: 99.9
    op: "2" # less than
    threshold: 1
```
````

The library chart uses `spaceAggregation: "max"` by default to avoid false positives from stale metric series.

To add SLO alerts to a chart:

1. Add `signoz-alerts` as a dependency in `Chart.yaml`
2. Add `sloDefaults` and `slos` to `values.yaml`
3. Create `templates/slo-alerts.yaml` that ranges over `.Values.slos` and includes `signoz-alerts.slo`

````

**Step 2: Commit**

```bash
git add architecture/observability-alerting.md
git commit -m "docs: add SLO-based alerts section to observability-alerting guide"
````

---

### Task 8: Push and create PR

**Step 1: Push the branch**

```bash
git push -u origin feat/slo-alert-library
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: add signoz-alerts library chart for SLO-based alerting" --body "$(cat <<'EOF'
## Summary
- Adds `charts/signoz-alerts/` Helm library chart that generates SigNoz alert ConfigMaps from SLO definitions
- Uses multi-window multi-burn-rate math: burn-fast (5m) + budget-exhausted (6h) alerts per SLO
- Integrates with api-gateway as proof-of-concept, replacing the hand-written httpcheck alert
- All alerts flow through existing signoz-dashboard-sidecar reconciliation

## Design doc
See `docs/plans/2026-03-08-slo-alert-library-design.md`

## Test plan
- [ ] `helm lint charts/signoz-alerts/ --strict` passes
- [ ] `helm template api-gateway charts/api-gateway/` renders both SLO alert ConfigMaps
- [ ] ConfigMaps have `signoz.io/alert: "true"` label for sidecar discovery
- [ ] Bazel CI lint passes for both charts
- [ ] After merge: verify sidecar syncs the new alerts to SigNoz via `signoz-mcp-signoz-list-alerts`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Wait for CI and verify**
