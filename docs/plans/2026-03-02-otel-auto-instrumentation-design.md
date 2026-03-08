# OpenTelemetry Auto-Instrumentation Design

## Status

Approved (2026-03-02)

## Context

The cluster has two observability layers today:

1. **Kyverno OTEL env injection** — mutates all pods to add `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_PROTOCOL` env vars. Apps with an OTEL SDK use these; apps without one ignore them.
2. **Linkerd service mesh** — injects sidecar proxies that capture HTTP request/response traces at the infrastructure level.

Neither layer generates application-level telemetry (database queries, internal function calls, library-level spans) without manual SDK integration. Only 3 of 9 backend services have manual OTEL SDK instrumentation today.

## Decision

Deploy the **OpenTelemetry Operator** (upstream Helm chart v0.106.0, appVersion 0.145.0) to enable automatic instrumentation injection for Python, Node.js, and Go workloads.

## Architecture

### Components

```
charts/opentelemetry-operator/          # Wrapper chart
├── Chart.yaml                          # Depends on upstream 0.106.0
├── values.yaml                         # Default values
├── templates/
│   ├── instrumentation-python.yaml     # Instrumentation CR for Python
│   ├── instrumentation-nodejs.yaml     # Instrumentation CR for Node.js
│   └── instrumentation-go.yaml         # Instrumentation CR for Go (eBPF)

overlays/cluster-critical/opentelemetry-operator/
├── application.yaml                    # ArgoCD Application
├── kustomization.yaml
├── values.yaml                         # Cluster-specific overrides
└── BUILD
```

### Namespace Layout

- **Operator**: deploys to `opentelemetry-operator` namespace
- **Instrumentation CRs**: templated into workload namespaces via a configurable list in values

### Data Flow

```
Pod created with annotation (e.g., instrumentation.opentelemetry.io/inject-python: "true")
  → OTEL Operator webhook intercepts the pod admission
  → Injects init container + env vars based on language annotation
  → App starts with auto-instrumentation agent loaded
  → Telemetry sent to SigNoz collector via existing OTEL_EXPORTER_OTLP_ENDPOINT
```

## Instrumentation CRDs

One `Instrumentation` CR per language, deployed into each workload namespace.

### Python

Covers: ais_ingest, ships_api, knowledge_graph, stargazer, trips_api, hikes services, buildbuddy_mcp, grimoire/extraction

```yaml
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: python
spec:
  exporter:
    endpoint: http://signoz-k8s-infra-otel-agent.signoz.svc.cluster.local:4317
  propagators:
    - tracecontext
    - baggage
  python:
    env:
      - name: OTEL_TRACES_EXPORTER
        value: otlp
      - name: OTEL_METRICS_EXPORTER
        value: none
      - name: OTEL_LOGS_EXPORTER
        value: none
```

### Node.js

Covers: ships_frontend, potentially todo

Same structure with `nodejs:` section.

### Go (eBPF)

Covers: grimoire/api, grimoire/ws-gateway

Same structure with `go:` section. Requires `manager.autoInstrumentation.go.enabled: true`.

**Security note:** The Go eBPF agent requires elevated privileges (`SYS_PTRACE` + `SYS_ADMIN` capabilities). The agent runs as a separate container — the app container remains non-root.

## Service Opt-In

Per-service annotation on Deployments:

```yaml
podAnnotations:
  instrumentation.opentelemetry.io/inject-python: "true"
```

Added to each service's `values.yaml` in their overlay directory.

## Coexistence with Manual SDK

Three services (knowledge_graph, stargazer, trips_api) already have manual OTEL SDK instrumentation. Auto-instrumentation layers on top:

- The OTEL SDK deduplicates instrumentors (e.g., `FastAPIInstrumentor` won't double-instrument)
- Auto-instrumentation catches libraries the manual SDK doesn't cover (httpx, redis, database drivers)
- No code changes needed in existing services

## Interaction with Existing Kyverno Policy

The Kyverno OTEL env var injection policy stays as-is. The `Instrumentation` CR's `spec.exporter.endpoint` takes precedence for auto-instrumented services. For non-auto-instrumented services, the Kyverno env vars remain available if they add their own SDK. No conflict.

## Out of Scope (YAGNI)

- Custom sampling configuration (use AlwaysOn defaults, tune later)
- Custom resource attributes (rely on built-in k8s resource detector)
- OTEL Collector changes (existing SigNoz collectors handle trace ingestion)
- Kyverno policy changes (existing OTEL env var injection stays)

## Target Namespaces

### Production

- trips
- knowledge-graph
- api-gateway
- mcp-servers
- todo

### Development

- grimoire
- marine
- stargazer

## Risks

1. **Go eBPF is experimental** — may cause issues, easy to disable per-service
2. **Privileged sidecar for Go** — conflicts with non-root convention but only affects the eBPF agent container
3. **Trace volume increase** — auto-instrumentation generates more spans; may need sampling later
