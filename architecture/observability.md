# Observability Architecture

This document describes the automatic observability setup in the cluster.

## Overview

Every service gets automatic observability through two layers:

1. **OTEL Environment Variables** - Application-level instrumentation
2. **Linkerd Service Mesh** - Infrastructure-level tracing

## Automatic Observability (Kyverno Policies)

### 1. OTEL Environment Variables (Application-Level)

- **All workloads** receive OTEL env vars automatically
- `OTEL_EXPORTER_OTLP_ENDPOINT` → SigNoz collector
- `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`
- Applications with OTEL SDKs get automatic instrumentation
- Applications without OTEL SDKs ignore the vars (harmless)
- **Policy:** `charts/kyverno/templates/otel-injection-policy.yaml`

### 2. Linkerd Namespace Annotation (Infrastructure-Level)

- **All namespaces** automatically get `linkerd.io/inject=enabled`
- Linkerd webhook injects sidecars into all pods
- Captures ALL HTTP/HTTPS traffic (no SDK needed!)
- Automatic distributed tracing for everything
- **Policy:** `charts/kyverno/templates/linkerd-injection-policy.yaml`

## Observable by Default Philosophy

- New deployments → Get OTEL env vars + Linkerd sidecar
- Existing deployments → Get annotations/vars via background policies
- **Opt-out if needed** (see below)

## Opting Out

### Opt-out of OTEL injection

```yaml
metadata:
  labels:
    otel.instrumentation: "disabled"
```

### Opt-out of Linkerd injection

```yaml
# Namespace level
apiVersion: v1
kind: Namespace
metadata:
  name: my-namespace
  labels:
    linkerd.io/inject: "disabled"
```

## Configuration

- OTEL: `charts/kyverno/values.yaml` (otelInjection section)
- Linkerd: `charts/kyverno/values.yaml` (linkerdInjection section)

## Excluded Namespaces (both policies)

- System: kube-system, kube-public, kube-node-lease
- Infrastructure: linkerd, cert-manager, kyverno, argocd, longhorn-system, signoz

## Service Requirements

Every service must:

- [ ] Export Prometheus metrics on `/metrics`
- [ ] Provide health check endpoint
- [ ] Send structured logs
- [ ] Include OpenTelemetry tracing (for user-facing services)
