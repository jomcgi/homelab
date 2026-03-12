# Design: Trusted & Public HTTPRoute Tiers

**Date:** 2026-03-11
**Status:** Approved

## Goal

Introduce two HTTPRoute tiers — `trusted` and `public` — enforced via Envoy Gateway policies and testable in CI. Migrate all services from static cloudflared tunnel routes to HTTPRoutes through a single Envoy Gateway, with appropriate security policies per tier.

## Architecture

All traffic enters through cloudflared → single catch-all → Envoy Gateway. Each service declares its tier via an `ingress-tier` label on its HTTPRoute. A shared Helm library chart generates the correct resources per tier.

```
Internet → Cloudflare Edge (Access policies on trusted hostnames)
         → cloudflared tunnel (single catch-all)
         → Envoy Gateway (cloudflare-ingress)
         → HTTPRoute (ingress-tier: trusted | public)
         → SecurityPolicy (trusted) or BackendTrafficPolicy (public)
         → Backend Service
```

### Tunnel Simplification

The tunnel config collapses from 11 static hostname→service routes to a single catch-all:

```yaml
tunnel:
  ingress:
    routes: []
    catchAll:
      service: http://cloudflare-ingress.envoy-gateway-system.svc.cluster.local:80
```

Deprecated routes (`n8n`, `feeds`) are dropped entirely.

## Helm Library Chart

A library chart (`cf-ingress`) provides named templates that services include. Located at `projects/platform/cf-ingress-library/`.

### Usage

```yaml
# values.yaml
cfIngress:
  tier: trusted # or "public"
  hostname: grimoire.jomcgi.dev
  gateway:
    name: cloudflare-ingress
    namespace: envoy-gateway-system
  # Public tier overrides:
  # rateLimit:
  #   requests: 100
  #   unit: Minute
```

```yaml
# templates/httproute.yaml
{ { - include "cf-ingress.httproute" (dict "ctx" . "tier" "trusted") } }
```

### Generated Resources

**For `tier: trusted`:**

- HTTPRoute with `ingress-tier: trusted` label
- SecurityPolicy with JWT validation:
  - Provider: `cloudflare-access`
  - Issuer: `https://jomcgi.cloudflareaccess.com`
  - JWKS: `https://jomcgi.cloudflareaccess.com/cdn-cgi/access/certs`
  - Extracts from: `Cf-Access-Jwt-Assertion` header
  - Claims to headers: `email` → `X-Auth-Email`

**For `tier: public`:**

- HTTPRoute with `ingress-tier: public` label
- BackendTrafficPolicy with rate limiting (default: 100 req/min, overridable)

## Service Classification

| Service      | Hostname                | Tier    |
| ------------ | ----------------------- | ------- |
| ArgoCD       | `argocd.jomcgi.dev`     | trusted |
| Longhorn     | `longhorn.jomcgi.dev`   | trusted |
| SigNoz       | `signoz.jomcgi.dev`     | trusted |
| Grimoire     | `grimoire.jomcgi.dev`   | trusted |
| Todo Admin   | `todo-admin.jomcgi.dev` | trusted |
| Trips Images | `img.jomcgi.dev`        | public  |
| Ships        | `ships.jomcgi.dev`      | public  |
| Todo         | `todo.jomcgi.dev`       | public  |
| API Gateway  | `api.jomcgi.dev`        | public  |

## CI / Static Analysis

The `ingress-tier` label is a testable contract. Semgrep/Bazel tests assert:

1. Every HTTPRoute has an `ingress-tier` label
2. `ingress-tier: trusted` HTTPRoutes have a SecurityPolicy in the same namespace
3. `ingress-tier: public` HTTPRoutes have a BackendTrafficPolicy with rate limiting
4. `ingress-tier: public` services' pods have NetworkPolicies

## Migration Strategy

Incremental, service-by-service:

**Phase 1 — Library chart + PoC (this PR)**

- Create `cf-ingress` library chart
- Migrate `todo` (public) and `todo-admin` (trusted)
- Remove their static tunnel routes, add catch-all

**Phase 2 — Remaining public services**

- `ships`, `img`, `api`

**Phase 3 — Remaining trusted services**

- `argocd`, `longhorn`, `signoz`, `grimoire`

**Phase 4 — CI tests**

- Semgrep rules asserting `ingress-tier` contract

**Phase 5 — Cleanup**

- Remove all static tunnel routes (tunnel config becomes catch-all only)
- Drop deprecated `n8n` and `feeds` routes

## Key Decisions

1. **Single Gateway, per-service policies** — simpler tunnel config; SecurityPolicy/BackendTrafficPolicy colocated with each service's HTTPRoute
2. **Helm library chart** — standardizes the pattern; services declare tier + hostname, library generates correct resources
3. **`ingress-tier` label** — serves dual purpose: Envoy Gateway policy targeting and CI static analysis signal
4. **Incremental migration** — one service at a time, remove static route as HTTPRoute takes over
5. **JWT validation at Envoy Gateway** — validates `Cf-Access-Jwt-Assertion` against Cloudflare Access JWKS; defense-in-depth behind Cloudflare's edge enforcement
6. **Rate limiting for public tier** — sensible defaults (100 req/min), overridable per-service
