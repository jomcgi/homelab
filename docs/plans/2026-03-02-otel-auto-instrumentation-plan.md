# OpenTelemetry Auto-Instrumentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the OpenTelemetry Operator and configure auto-instrumentation for Python, Node.js, and Go services.

**Architecture:** Wrapper Helm chart around upstream `opentelemetry-operator` (v0.106.0), deployed via ArgoCD to `cluster-critical`. Instrumentation CRs are templated into workload namespaces. Services opt in via pod annotations.

**Tech Stack:** Helm, ArgoCD, Kustomize, OpenTelemetry Operator, Bazel (BUILD files)

**Design doc:** `docs/plans/2026-03-02-otel-auto-instrumentation-design.md`

**Worktree:** `/tmp/claude-worktrees/otel-auto-instrumentation` (branch: `feat/otel-auto-instrumentation`)

---

## Task 1: Create the OTEL Operator wrapper chart

Create the Helm wrapper chart following the established pattern (see `charts/kyverno/` or `charts/cert-manager/` for reference).

**Files:**

- Create: `charts/opentelemetry-operator/Chart.yaml`
- Create: `charts/opentelemetry-operator/values.yaml`
- Create: `charts/opentelemetry-operator/BUILD`

**Step 1: Create `charts/opentelemetry-operator/Chart.yaml`**

```yaml
apiVersion: v2
name: opentelemetry-operator
description: OpenTelemetry Operator with auto-instrumentation for Python, Node.js, and Go
type: application
version: 0.1.0
appVersion: "0.145.0"
dependencies:
  - name: opentelemetry-operator
    version: 0.106.0
    repository: https://open-telemetry.github.io/opentelemetry-helm-charts
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create `charts/opentelemetry-operator/values.yaml`**

```yaml
# Upstream opentelemetry-operator subchart values
opentelemetry-operator:
  manager:
    resources:
      requests:
        cpu: 50m
        memory: 128Mi
      limits:
        cpu: 200m
        memory: 256Mi
    # Enable Go eBPF auto-instrumentation support
    autoInstrumentation:
      go:
        enabled: true

# Instrumentation CRD configuration
instrumentation:
  # OTEL collector endpoint (SigNoz k8s-infra agent)
  endpoint: http://signoz-k8s-infra-otel-agent.signoz.svc.cluster.local:4317
  propagators:
    - tracecontext
    - baggage
  # Target namespaces to deploy Instrumentation CRs into
  namespaces: []
  python:
    enabled: false
  nodejs:
    enabled: false
  go:
    enabled: false
```

**Step 3: Create `charts/opentelemetry-operator/BUILD`**

Reference the pattern in `charts/kyverno/BUILD`:

```starlark
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    lint = False,
    visibility = ["//overlays/cluster-critical/opentelemetry-operator:__pkg__"],
)
```

**Step 4: Download chart dependency**

Run: `cd /tmp/claude-worktrees/otel-auto-instrumentation/charts/opentelemetry-operator && helm dependency update`

Expected: `charts/opentelemetry-operator-0.106.0.tgz` created in `charts/` subdirectory.

**Step 5: Commit**

```bash
git add charts/opentelemetry-operator/
git commit -m "feat: add opentelemetry-operator wrapper chart"
```

---

## Task 2: Add Instrumentation CR templates

Create Helm templates for the Python, Node.js, and Go `Instrumentation` CRDs. These deploy into each namespace listed in `.Values.instrumentation.namespaces`.

**Files:**

- Create: `charts/opentelemetry-operator/templates/instrumentation-python.yaml`
- Create: `charts/opentelemetry-operator/templates/instrumentation-nodejs.yaml`
- Create: `charts/opentelemetry-operator/templates/instrumentation-go.yaml`

**Step 1: Create `charts/opentelemetry-operator/templates/instrumentation-python.yaml`**

```yaml
{{- if .Values.instrumentation.python.enabled }}
{{- range .Values.instrumentation.namespaces }}
---
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: python
  namespace: {{ . }}
spec:
  exporter:
    endpoint: {{ $.Values.instrumentation.endpoint }}
  propagators:
  {{- range $.Values.instrumentation.propagators }}
    - {{ . }}
  {{- end }}
  python:
    env:
      - name: OTEL_TRACES_EXPORTER
        value: otlp
      - name: OTEL_METRICS_EXPORTER
        value: none
      - name: OTEL_LOGS_EXPORTER
        value: none
{{- end }}
{{- end }}
```

**Step 2: Create `charts/opentelemetry-operator/templates/instrumentation-nodejs.yaml`**

```yaml
{{- if .Values.instrumentation.nodejs.enabled }}
{{- range .Values.instrumentation.namespaces }}
---
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: nodejs
  namespace: {{ . }}
spec:
  exporter:
    endpoint: {{ $.Values.instrumentation.endpoint }}
  propagators:
  {{- range $.Values.instrumentation.propagators }}
    - {{ . }}
  {{- end }}
  nodejs:
    env:
      - name: OTEL_TRACES_EXPORTER
        value: otlp
      - name: OTEL_METRICS_EXPORTER
        value: none
      - name: OTEL_LOGS_EXPORTER
        value: none
{{- end }}
{{- end }}
```

**Step 3: Create `charts/opentelemetry-operator/templates/instrumentation-go.yaml`**

```yaml
{{- if .Values.instrumentation.go.enabled }}
{{- range .Values.instrumentation.namespaces }}
---
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: go
  namespace: {{ . }}
spec:
  exporter:
    endpoint: {{ $.Values.instrumentation.endpoint }}
  propagators:
  {{- range $.Values.instrumentation.propagators }}
    - {{ . }}
  {{- end }}
  go: {}
{{- end }}
{{- end }}
```

**Step 4: Commit**

```bash
git add charts/opentelemetry-operator/templates/
git commit -m "feat: add Instrumentation CR templates for Python, Node.js, and Go"
```

---

## Task 3: Create the overlay in cluster-critical

Create the ArgoCD Application, kustomization, values, and BUILD files following the pattern in `overlays/cluster-critical/kyverno/`.

**Files:**

- Create: `overlays/cluster-critical/opentelemetry-operator/application.yaml`
- Create: `overlays/cluster-critical/opentelemetry-operator/kustomization.yaml`
- Create: `overlays/cluster-critical/opentelemetry-operator/values.yaml`
- Create: `overlays/cluster-critical/opentelemetry-operator/BUILD`
- Modify: `overlays/cluster-critical/kustomization.yaml` — add `./opentelemetry-operator`

**Step 1: Create `overlays/cluster-critical/opentelemetry-operator/application.yaml`**

Follow the pattern in `overlays/cluster-critical/kyverno/application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: opentelemetry-operator
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: charts/opentelemetry-operator
    helm:
      releaseName: opentelemetry-operator
      valueFiles:
        - values.yaml
        - ../../overlays/cluster-critical/opentelemetry-operator/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: opentelemetry-operator
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

**Step 2: Create `overlays/cluster-critical/opentelemetry-operator/kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create `overlays/cluster-critical/opentelemetry-operator/values.yaml`**

This enables all three languages and lists the target namespaces:

```yaml
# Cluster-specific overrides for OpenTelemetry Operator

# Enable all three auto-instrumentation languages
instrumentation:
  python:
    enabled: true
  nodejs:
    enabled: true
  go:
    enabled: true
  # Namespaces to deploy Instrumentation CRs into
  namespaces:
    # Production
    - trips
    - knowledge-graph
    - api-gateway
    - mcp-servers
    - todo
    # Development
    - grimoire
    - marine
    - stargazer
```

**Step 4: Create `overlays/cluster-critical/opentelemetry-operator/BUILD`**

Follow the pattern in `overlays/cluster-critical/kyverno/BUILD`:

```starlark
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "opentelemetry-operator",
    chart = "charts/opentelemetry-operator",
    chart_files = "//charts/opentelemetry-operator:chart",
    namespace = "opentelemetry-operator",
    release_name = "opentelemetry-operator",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/opentelemetry-operator:values.yaml",
        "values.yaml",
    ],
)
```

**Step 5: Add to cluster-critical kustomization**

Modify `overlays/cluster-critical/kustomization.yaml` — add `./opentelemetry-operator` to the resources list. Place it after `./kyverno` (Kyverno needs to be running to inject OTEL env vars, but the operator itself doesn't depend on Kyverno).

**Step 6: Commit**

```bash
git add overlays/cluster-critical/opentelemetry-operator/ overlays/cluster-critical/kustomization.yaml
git commit -m "feat: add opentelemetry-operator ArgoCD application and overlay"
```

---

## Task 4: Add podAnnotations support to charts that need it

Several charts have hardcoded annotations in their Deployment templates without a `podAnnotations` values hook. Add `podAnnotations` support to enable auto-instrumentation opt-in.

**Charts that already support `podAnnotations`** (no changes needed):

- `charts/marine` — `.Values.ingest.podAnnotations`, `.Values.api.podAnnotations`, `.Values.frontend.podAnnotations`
- `charts/stargazer` — `.Values.podAnnotations`

**Charts that need `podAnnotations` added:**

### 4a: `charts/trips/templates/api-deployment.yaml`

**File:** Modify `charts/trips/templates/api-deployment.yaml`

Find the existing hardcoded annotations block in the pod template:

```yaml
annotations:
  # Mark NATS port as opaque for Linkerd
  config.linkerd.io/opaque-ports: "4222"
```

Add after the existing annotation:

```yaml
      annotations:
        # Mark NATS port as opaque for Linkerd
        config.linkerd.io/opaque-ports: "4222"
        {{- with .Values.api.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
```

### 4b: `charts/grimoire/templates/ws-gateway-deployment.yaml`

**File:** Modify `charts/grimoire/templates/ws-gateway-deployment.yaml`

Find the existing annotations block:

```yaml
annotations:
  config.linkerd.io/skip-outbound-ports: "{{ .Values.redis.service.port }}"
```

Add after:

```yaml
      annotations:
        config.linkerd.io/skip-outbound-ports: "{{ .Values.redis.service.port }}"
        {{- with .Values.wsGateway.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
```

### 4c: `charts/grimoire/templates/frontend-deployment.yaml` (grimoire API deployment)

**File:** Check if grimoire has a separate api-deployment.yaml. If so, modify it similarly.

Search for `charts/grimoire/templates/api-deployment.yaml` or equivalent — the Go API server deployment needs `podAnnotations` for Go auto-instrumentation.

### 4d: `charts/api-gateway/templates/deployment.yaml`

**File:** Modify `charts/api-gateway/templates/deployment.yaml`

Find the existing annotations block:

```yaml
annotations:
  checksum/nginx-config:
    { { include (print $.Template.BasePath "/configmap.yaml") . | sha256sum } }
  checksum/collector-config:
    {
      {
        include (print $.Template.BasePath "/collector-configmap.yaml") . | sha256sum,
      },
    }
```

Add after:

```yaml
      annotations:
        checksum/nginx-config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        checksum/collector-config: {{ include (print $.Template.BasePath "/collector-configmap.yaml") . | sha256sum }}
        {{- with .Values.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
```

### 4e: `charts/todo/templates/deployment.yaml`

**File:** Modify `charts/todo/templates/deployment.yaml`

The template currently has no annotations block. Add one in the pod template metadata:

```yaml
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
```

### 4f: `charts/knowledge-graph` deployments

**File:** Modify `charts/knowledge-graph/templates/deployment-scraper.yaml` (and any other deployment templates in this chart).

Find the existing annotations block and add `podAnnotations` support.

### 4g: `charts/mcp-servers/templates/deployment.yaml`

**File:** Modify `charts/mcp-servers/templates/deployment.yaml`

The template currently has no annotations block in pod template. Add one:

```yaml
  template:
    metadata:
      {{- with .podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
```

Note: mcp-servers iterates over `.Values.servers`, so the annotation would come from each server entry's `.podAnnotations`.

**Step (final): Commit**

```bash
git add charts/trips/ charts/grimoire/ charts/api-gateway/ charts/todo/ charts/knowledge-graph/ charts/mcp-servers/
git commit -m "feat: add podAnnotations support to chart templates for auto-instrumentation"
```

---

## Task 5: Add auto-instrumentation annotations to service values

Add the opt-in annotation to each service's overlay `values.yaml`.

**Important:** The annotation value must match the language. Use `"true"` to reference the Instrumentation CR named after the language in the same namespace.

### 5a: Marine services (dev) — `overlays/dev/marine/values.yaml`

Marine already has `podAnnotations` per component. Add the annotation:

- `ingest.podAnnotations` — add `instrumentation.opentelemetry.io/inject-python: "true"` (ais_ingest is Python)
- `api.podAnnotations` — add `instrumentation.opentelemetry.io/inject-python: "true"` (ships_api is Python)
- `frontend.podAnnotations` — add `instrumentation.opentelemetry.io/inject-nodejs: "true"` (ships_frontend is Bun/JS)

### 5b: Stargazer (dev) — `overlays/dev/stargazer/values.yaml`

Add to existing `podAnnotations`:

```yaml
podAnnotations:
  otel.injected-by: kyverno/inject-otel-env-vars
  instrumentation.opentelemetry.io/inject-python: "true"
```

### 5c: Grimoire (dev) — `overlays/dev/grimoire/values.yaml`

Add new values for each component:

```yaml
wsGateway:
  podAnnotations:
    instrumentation.opentelemetry.io/inject-go: "true"
```

Check grimoire's chart for additional Go components (api server) and add similarly.

### 5d: Trips (prod) — `overlays/prod/trips/values.yaml`

Add:

```yaml
api:
  podAnnotations:
    instrumentation.opentelemetry.io/inject-python: "true"
```

### 5e: Knowledge-graph (prod) — `overlays/prod/knowledge-graph/values.yaml`

Add podAnnotations for the scraper deployment (Python):

```yaml
podAnnotations:
  instrumentation.opentelemetry.io/inject-python: "true"
```

### 5f: API Gateway (prod) — `overlays/prod/api-gateway/values.yaml`

Check what language api-gateway uses, then add appropriate annotation. If it's an nginx-based gateway, auto-instrumentation won't apply — skip this service.

### 5g: Todo (prod) — `overlays/prod/todo/values.yaml`

Todo is a Go service. Add:

```yaml
podAnnotations:
  instrumentation.opentelemetry.io/inject-go: "true"
```

### 5h: MCP Servers (prod) — `overlays/prod/mcp-servers/values.yaml`

Add `podAnnotations` to each server entry that's Python-based. Check which servers are Python.

**Step (final): Commit**

```bash
git add overlays/
git commit -m "feat: add auto-instrumentation annotations to service overlays"
```

---

## Task 6: Validate with helm template and bazel build

Verify the chart renders correctly and passes Bazel builds.

**Step 1: Render the operator chart**

Run: `helm template opentelemetry-operator charts/opentelemetry-operator/ -f overlays/cluster-critical/opentelemetry-operator/values.yaml`

Expected: Valid YAML output with:

- Operator Deployment in `opentelemetry-operator` namespace
- Instrumentation CRs in each target namespace (trips, knowledge-graph, etc.)
- Python, Node.js, and Go `Instrumentation` resources

**Step 2: Verify Instrumentation CRs have correct namespaces**

Run: `helm template opentelemetry-operator charts/opentelemetry-operator/ -f overlays/cluster-critical/opentelemetry-operator/values.yaml | grep -A2 "kind: Instrumentation"`

Expected: Each Instrumentation CR should have a `namespace:` matching a workload namespace.

**Step 3: Render service charts to verify annotations**

Run for each modified service chart:

- `helm template trips charts/trips/ -f overlays/prod/trips/values.yaml | grep -A5 "inject-python"`
- `helm template marine charts/marine/ -f overlays/dev/marine/values.yaml | grep -A5 "inject-"`
- etc.

Expected: Auto-instrumentation annotations present in pod templates.

**Step 4: Run bazel build**

Run: `bazel build //...`

Expected: Build succeeds with no errors for the new chart and overlay.

**Step 5: Run format check**

Run: `format`

Expected: No formatting changes needed (or apply them if needed).

**Step 6: Commit any fixes**

If formatting or build fixes are needed:

```bash
git add -A
git commit -m "fix: formatting and build fixes for opentelemetry-operator"
```

---

## Task 7: Push and create PR

**Step 1: Push branch**

Run: `git push -u origin feat/otel-auto-instrumentation`

**Step 2: Create PR**

Use `gh pr create` with a summary of all changes.

**Step 3: Verify CI passes**

Check BuildBuddy workflow results. Fix any issues.
