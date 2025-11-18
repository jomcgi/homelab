# Linkerd Service Mesh

**Automatic distributed tracing for all pod-to-pod communication**

## Overview

Linkerd is a lightweight service mesh that automatically:
- Injects sidecar proxies into all pods (via admission webhook)
- Captures and traces all HTTP/HTTPS traffic
- Exports OTEL traces to SigNoz
- Provides mTLS between all services
- Adds reliability features (retries, timeouts, circuit breaking)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Meshed Pod                                                    │
│ ┌────────────────┐           ┌──────────────────────┐        │
│ │ App Container  │←────────→ │ Linkerd Proxy        │───────→│ → SigNoz
│ │                │           │ - Traces all traffic │        │   OTEL
│ │                │           │ - Mutual TLS         │        │   Collector
│ └────────────────┘           └──────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

## Prerequisites

**IMPORTANT:** Linkerd requires a trust anchor certificate. This is handled automatically by cert-manager.

### Automatic Certificate Management

This chart uses **cert-manager** to automatically generate and rotate certificates:

1. **cert-manager** is deployed first (defined in `cluster-critical/cert-manager`)
2. **Linkerd trust anchor** is auto-generated (10-year root CA)
3. **Identity issuer** is auto-generated (1-year intermediate CA, auto-renewed)
4. **No manual certificate management required!**

The certificates are managed by these resources (automatically created):
- `ClusterIssuer/linkerd-trust-anchor-selfsigned` - Self-signed root issuer
- `Certificate/linkerd-trust-anchor` - 10-year root CA
- `Issuer/linkerd-trust-anchor` - CA issuer for identity certificates
- `Certificate/linkerd-identity-issuer` - 1-year intermediate CA (auto-renewed)

## Deployment

**Zero manual steps required!** ArgoCD automatically:
1. Deploys cert-manager
2. Creates trust anchor and identity certificates
3. Deploys Linkerd with certificates

## Meshing Applications

### Automatic Injection (Enabled by Default!)

**All namespaces automatically get Linkerd injection enabled** via Kyverno policy:
- New namespaces → Automatically annotated with `linkerd.io/inject=enabled`
- Existing namespaces → Automatically annotated (via background policy)
- Pods → Linkerd webhook injects sidecars when they're created/restarted

**You don't need to do anything!** Just deploy your applications normally.

### Opt-Out (If Needed)

To disable injection for a specific namespace:

```bash
# Label the namespace to opt-out
kubectl label namespace <namespace> linkerd.io/inject=disabled

# Or set the annotation explicitly
kubectl annotate namespace <namespace> linkerd.io/inject=disabled --overwrite
```

### Per-Pod Injection Override

You can also control injection at the pod level:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    metadata:
      annotations:
        linkerd.io/inject: disabled  # Skip this deployment
    spec:
      containers:
      - name: app
        image: my-app:latest
```

### Excluded Namespaces (Never Meshed)

These namespaces are excluded via Kyverno policy:
- `kube-system`, `kube-public`, `kube-node-lease` - System namespaces
- `linkerd`, `linkerd-cni` - Linkerd control plane
- `cert-manager` - Certificate management
- `kyverno` - Policy engine
- `argocd` - GitOps controller
- `longhorn-system` - Storage system
- `signoz` - Observability platform (to avoid circular tracing)

## Verification

Check that Linkerd is working:

```bash
# Check control plane status
linkerd check

# Verify proxy injection
kubectl get pods -n <namespace> -o jsonpath='{.items[*].spec.containers[*].name}'
# Should see: <your-container> linkerd-proxy

# View live traces in SigNoz
# Navigate to SigNoz UI → Traces
```

## Tracing Configuration

Linkerd is configured to send all traces to SigNoz:
- **Endpoint:** `signoz-otel-collector.signoz.svc.cluster.local:4317`
- **Protocol:** OTLP/gRPC
- **Format:** OpenTelemetry

All HTTP/HTTPS traffic is automatically traced with:
- Request duration
- Response status codes
- Service-to-service calls (distributed trace)
- Proxy overhead metrics

## Resource Usage

Per-pod overhead (approximate):
- **CPU:** 100m request, 1000m limit
- **Memory:** 20Mi request, 250Mi limit

For a cluster with 50 pods, expect ~5 CPU cores and ~10GB memory for proxies.

## Troubleshooting

### Proxy Not Injecting

```bash
# Check webhook is running
kubectl get mutatingwebhookconfiguration linkerd-proxy-injector-webhook-config

# Check namespace annotation
kubectl get namespace <namespace> -o yaml | grep linkerd.io/inject

# Check pod logs
kubectl logs <pod-name> -c linkerd-proxy -n <namespace>
```

### Traces Not Appearing in SigNoz

```bash
# Verify collector endpoint is reachable
kubectl run -it --rm debug --image=busybox --restart=Never -- \
  nc -zv signoz-otel-collector.signoz.svc.cluster.local 4317

# Check proxy logs for OTEL errors
kubectl logs <pod-name> -c linkerd-proxy -n <namespace> | grep -i otel
```

### mTLS Issues

```bash
# Check certificates are valid
linkerd identity check

# View certificate details
kubectl get secret -n linkerd linkerd-identity-issuer -o yaml
```

## Architecture Decision: Why Linkerd?

**Chosen over:**
- **Custom Envoy + Kyverno:** Too complex, lots of edge cases to handle
- **Istio:** Too heavy, complex configuration
- **No mesh:** Missing automatic tracing for internal traffic

**Linkerd advantages:**
- Lightweight (smallest resource footprint)
- Simple operations (just works)
- Automatic tracing built-in
- Battle-tested in production
- Integrates perfectly with existing Cloudflare Tunnel + Gateway API setup

## References

- [Linkerd Documentation](https://linkerd.io/2-edge/)
- [Distributed Tracing Guide](https://linkerd.io/2-edge/tasks/distributed-tracing/)
- [OpenTelemetry Integration](https://linkerd.io/2025/09/09/linkerd-with-opentelemetry/)
