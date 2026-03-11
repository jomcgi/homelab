# Design: Combined cloudflare-gateway Chart

**Date:** 2026-03-10
**Status:** Approved

## Goal

Combine three separate ingress components into a single `cloudflare-gateway` Helm chart:

- `envoy-gateway` (upstream control plane wrapper)
- `cloudflare/ingress` (GatewayClass, Gateway, EnvoyProxy, Service)
- `cloudflare/tunnel` (cloudflared deployment)

## Architecture

Single chart at `projects/platform/cloudflare-gateway/` with the upstream `gateway-helm` as a subchart dependency.

```
projects/platform/cloudflare-gateway/
├── Chart.yaml                    # Dependencies: gateway-helm subchart
├── values.yaml                   # Default values (all components)
├── values-prod.yaml              # Prod overrides
├── application.yaml              # Single ArgoCD Application
├── kustomization.yaml            # ArgoCD discovery
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml           # cloudflared pods
│   ├── configmap.yaml            # tunnel config
│   ├── secret.yaml               # 1Password integration
│   ├── tunnel-service.yaml       # metrics service
│   ├── envoy-configmap.yaml      # envoy sidecar config (optional)
│   ├── gatewayclass.yaml         # conditional on gateway.enabled
│   ├── gateway.yaml              # conditional on gateway.enabled
│   ├── envoyproxy.yaml           # conditional on gateway.enabled
│   └── gateway-service.yaml      # conditional on gateway.enabled
└── charts/
    └── gateway-helm/             # upstream envoy-gateway subchart
```

## Values Structure

Top-level keys:

- `gateway-helm:` — passed through to upstream envoy-gateway subchart
- `gateway:` — Gateway API resources (GatewayClass, Gateway, EnvoyProxy, Service), toggleable via `gateway.enabled`
- `tunnel:` — cloudflared deployment config (re-keyed from current root-level values)

Subchart disabling via Chart.yaml `condition: envoyGateway.enabled`.

## Key Decisions

1. **Single ArgoCD Application** targeting `envoy-gateway-system` namespace
2. **Tunnel moves to `envoy-gateway-system`** — no more separate `ingress` namespace
3. **`gateway.enabled` flag** wraps GatewayClass, Gateway, EnvoyProxy, gateway Service
4. **`envoyGateway.enabled` condition** on subchart for environments without control plane
5. **ServerSideApply** retained for CRD compatibility
6. **`linkerd.io/inject: disabled`** namespace annotation preserved
7. **Migration strategy (B)** — swap apps directly, let ArgoCD reconcile (brief downtime acceptable)

## What Gets Deleted

- `projects/platform/envoy-gateway/` (entire directory)
- `projects/platform/cloudflare/ingress/` (entire directory)
- `projects/platform/cloudflare/tunnel/` (entire directory)
- 3 entries in `projects/platform/kustomization.yaml` replaced with 1
