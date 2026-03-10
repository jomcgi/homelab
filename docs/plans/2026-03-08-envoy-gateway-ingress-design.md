# Envoy Gateway Ingress Design

**Date:** 2026-03-08
**Status:** Approved
**Relates to:** [ADR 001: Reduce Cloudflare Operator Scope via Envoy Gateway](../../docs/decisions/networking/001-cloudflare-envoy-gateway.md)

## Problem

The cloudflare-tunnel Helm chart has 12 hardcoded hostname-to-service routes in a ConfigMap. Adding or changing a route requires editing shared infra config (`overlays/prod/cloudflare-tunnel/values.yaml`). There is no in-cluster routing layer -- the tunnel proxies directly to backend Services.

The previous attempt (PR #877) tried to migrate individual routes through Envoy Gateway, but this duplicated routing config across two systems without simplifying anything.

## Decision

Deploy Envoy Gateway as the in-cluster routing layer with a single `cloudflare-ingress` Gateway. Wire the tunnel's catch-all to Envoy Gateway. Do not migrate any existing routes in this PR -- just establish the infrastructure so that future route migrations only require adding an HTTPRoute and removing a tunnel entry.

## Architecture

### Traffic flow (after this change)

```
Internet -> Cloudflare -> cloudflared tunnel
  |-- argocd.jomcgi.dev     -> argocd-server (direct, unchanged)
  |-- signoz.jomcgi.dev     -> signoz (direct, unchanged)
  |-- ... 10 more ...       -> direct backends (unchanged)
  +-- anything else         -> Envoy Gateway -> 404
```

### Traffic flow (after future route migration)

```
Internet -> Cloudflare -> cloudflared tunnel (catch-all only)
  +-- all traffic           -> Envoy Gateway -> HTTPRoutes -> backends
```

## Components

### 1. Envoy Gateway control plane

- **Chart:** `charts/envoy-gateway/` -- wrapper for upstream `gateway-helm` (OCI: `oci://docker.io/envoyproxy`, v1.3.2)
- **Overlay:** `overlays/cluster-critical/envoy/` -- ArgoCD Application
- **Namespace:** `envoy-gateway-system` (created by ArgoCD)
- **Config:** `system-cluster-critical` priority, `readOnlyRootFilesystem: true`, Linkerd injection disabled (iptables/QUIC interference)

### 2. Cloudflare ingress Gateway

- **Chart:** `charts/cloudflare-ingress/` -- local chart containing:
  - `GatewayClass` named `cloudflare-ingress` with `parametersRef` to `EnvoyProxy` CRD
  - `EnvoyProxy` CRD `cloudflare-ingress-proxy` in `envoy-gateway-system` -- conservative resources (50m CPU / 64Mi memory), `readOnlyRootFilesystem: true`
  - `Gateway` named `cloudflare-ingress` in `envoy-gateway-system`, HTTP:80, `allowedRoutes.namespaces.from: All`
  - `Service` named `cloudflare-ingress` (stable ClusterIP) -- selects Envoy proxy pods via `gateway.envoyproxy.io/owning-gateway-name: cloudflare-ingress` labels, giving the tunnel a predictable target regardless of Envoy Gateway's auto-generated Service naming
- **Overlay:** `overlays/prod/cloudflare-ingress/` -- ArgoCD Application
- **No HTTPRoutes** -- Envoy returns 404 for all unmatched requests

### 3. Tunnel catch-all change

In `overlays/prod/cloudflare-tunnel/values.yaml`:

```yaml
ingress:
  routes:
    # ... all 12 existing routes unchanged ...
  catchAll:
    service: http://cloudflare-ingress.envoy-gateway-system.svc.cluster.local:80
```

Replaces the current `http_status:404` catch-all. Behaviour is identical (404) since no HTTPRoutes exist yet, but traffic now flows through Envoy Gateway.

## Stable Service naming

Envoy Gateway auto-creates a Service named `envoy-{namespace}-{gateway-name}-{uid-hash}` which is unpredictable. The `cloudflare-ingress` chart includes a stable `Service` that selects the Envoy proxy pods by their well-known labels:

```yaml
selector:
  gateway.envoyproxy.io/owning-gateway-name: cloudflare-ingress
  gateway.envoyproxy.io/owning-gateway-namespace: envoy-gateway-system
```

This decouples the tunnel config from Envoy Gateway's internal naming.

## What this enables next

1. **Migrate a route:** Create an HTTPRoute in the backend's namespace, remove the hostname entry from tunnel values
2. **HTTPRoute helm library:** A shared chart/template for creating HTTPRoutes attached to the `cloudflare-ingress` Gateway
3. **NetworkPolicy enforcement:** A Kyverno policy asserting that any pod reachable from the public internet has strict NetworkPolicies limiting lateral movement
4. **Full migration:** Once all routes are HTTPRoutes, the tunnel config collapses to just the catch-all

## What does NOT change

- All 12 existing tunnel hostname routes remain untouched
- No new namespaces beyond `envoy-gateway-system` (already created for the control plane)
- No HTTPRoutes in this PR
- No DNS changes
