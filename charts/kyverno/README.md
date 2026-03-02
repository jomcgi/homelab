# Kyverno

Policy engine for Kubernetes with custom ClusterPolicies for automated observability and service mesh injection.

## Overview

Kyverno acts as a Kubernetes admission controller that mutates resources to enforce cluster-wide conventions. This chart wraps the upstream Kyverno chart and adds two custom ClusterPolicies that automatically inject OpenTelemetry configuration and Linkerd service mesh annotations into all workloads.

```mermaid
flowchart LR
    API[API Server] -->|admission webhook| KYV[Kyverno]

    subgraph Policies
        OTEL[OTel Injection Policy]
        LINK[Linkerd Injection Policy]
    end

    KYV --> OTEL
    KYV --> LINK
    OTEL -->|inject env vars| Workloads[Deployments / StatefulSets / DaemonSets]
    LINK -->|annotate| NS[Namespaces]
```

## Architecture

The chart deploys four Kyverno controllers plus two custom ClusterPolicies:

- **Admission Controller** - Intercepts API server requests to mutate and validate resources against policies
- **Background Controller** - Applies policies retroactively to existing resources (not just new ones)
- **Cleanup Controller** - Manages lifecycle of policy reports
- **Reports Controller** - Generates policy compliance reports

Custom policies included:

- **OTel Injection** (`inject-otel-env-vars`) - Mutates Deployments, StatefulSets, and DaemonSets to inject `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_PROTOCOL` environment variables
- **Linkerd Injection** (`inject-linkerd-namespace-annotation`) - Mutates Namespaces to add `linkerd.io/inject: enabled` annotation for automatic sidecar injection

## Key Features

- **Cluster-wide observability** - All workloads automatically get OTel configuration
- **Automatic mesh enrollment** - All namespaces get Linkerd sidecar injection by default
- **Opt-out model** - Label with `otel.instrumentation: disabled` or `linkerd.io/inject: disabled` to exclude
- **Background enforcement** - Policies apply to both existing and new resources
- **Audit mode** - Policies use `validationFailureAction: Audit` (non-blocking)
- **Policy exceptions** - Supports Kyverno PolicyExceptions for fine-grained overrides

## Configuration

| Value                                       | Description                                | Default                                               |
| ------------------------------------------- | ------------------------------------------ | ----------------------------------------------------- |
| `otelInjection.enabled`                     | Enable OTel env var injection policy       | `true`                                                |
| `otelInjection.endpoint`                    | OTel collector endpoint                    | `signoz-otel-collector.signoz.svc.cluster.local:4317` |
| `otelInjection.protocol`                    | OTel exporter protocol                     | `grpc`                                                |
| `otelInjection.targetKinds`                 | Resource kinds to inject into              | `[Deployment, StatefulSet, DaemonSet]`                |
| `linkerdInjection.enabled`                  | Enable Linkerd namespace injection policy  | `true`                                                |
| `linkerdInjection.excludeNamespaces`        | Namespaces excluded from Linkerd injection | System + infra namespaces                             |
| `kyverno.admissionController.replicas`      | Admission controller replicas              | `1`                                                   |
| `kyverno.features.policyExceptions.enabled` | Enable PolicyException CRD                 | `true`                                                |
