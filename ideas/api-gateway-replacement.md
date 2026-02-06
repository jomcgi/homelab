# API Gateway Replacement: Migrate to Cloudflare Operator + Standalone Services

## Executive Summary

Replace the monolithic `api-gateway` (nginx + collector sidecar) with:

1. **HTTPRoute resources** managed by the Cloudflare operator for routing
2. **Standalone cluster-info service** for metrics aggregation
3. **Cloudflare Transform Rules** for edge caching headers

This eliminates the nginx middleman, reduces complexity, and leverages native Kubernetes Gateway API patterns.

---

## Current Architecture

```
Cloudflare Edge
       │
       v
Cloudflare Tunnel (api.jomcgi.dev)
       │
       v
api-gateway Deployment (nginx + collector sidecar)
       │
       ├── /trips/*        → trips-nginx:80 (WebSocket headers, path preserved)
       ├── /stargazer/*    → stargazer-api:80 (path stripped)
       ├── /cluster-info   → local file (served by nginx)
       ├── /status.json    → local file (served by nginx)
       └── /health         → "ok"
```

### Problems with Current Design

1. **Unnecessary indirection**: nginx is just proxying requests that Cloudflare Tunnel can route directly
2. **Mixed concerns**: Routing + metrics collection in one deployment
3. **Nginx configuration complexity**: WebSocket headers, CORS, caching - all in ConfigMap
4. **Not using Gateway API**: Manual ingress config instead of declarative HTTPRoute

---

## Proposed Architecture

```
Cloudflare Edge (Transform Rules for Cache-Control)
       │
       v
Cloudflare Tunnel (managed by Gateway CRD)
       │
       ├── HTTPRoute: trips.jomcgi.dev/*     → trips-nginx:80
       ├── HTTPRoute: stargazer.jomcgi.dev/* → stargazer-api:80
       └── HTTPRoute: api.jomcgi.dev/*       → cluster-info:80
```

### Key Changes

| Component       | Before                 | After                              |
| --------------- | ---------------------- | ---------------------------------- |
| Routing         | nginx proxy_pass       | HTTPRoute CRDs                     |
| DNS             | Manual + Tunnel config | Automatic via HTTPRoute controller |
| Cluster metrics | Collector sidecar      | Standalone cluster-info service    |
| Caching headers | nginx add_header       | Cloudflare Transform Rules         |
| Path stripping  | nginx rewrite          | Backend handles full path          |
| WebSocket       | nginx upgrade headers  | Cloudflare Tunnel native           |

---

## Implementation Plan

### Phase 1: Create Standalone cluster-info Service

The collector sidecar functionality becomes its own deployment.

**New chart: `charts/cluster-info/`**

```yaml
# values.yaml
image:
  repository: ghcr.io/jomcgi/cluster-info
  tag: latest

service:
  port: 80

# Polling interval for metrics collection
collector:
  interval: 30s

# CORS origins
cors:
  allowedOrigins:
    - "*.jomcgi.dev"
    - "localhost:*"

# Cache settings (response headers)
cache:
  maxAge: 30
  staleWhileRevalidate: 300
```

**Implementation options:**

| Option                | Pros                                  | Cons                  |
| --------------------- | ------------------------------------- | --------------------- |
| **A: Go service**     | Type-safe, efficient, good k8s client | Build complexity      |
| **B: Python FastAPI** | Quick to build, matches stargazer     | Heavier runtime       |
| **C: Shell + nginx**  | Reuse existing collector script       | Fragile, hard to test |

**Recommendation**: Option B (Python FastAPI) - consistent with stargazer-api, easy CORS/caching.

**Endpoints:**

- `GET /` - Full cluster info JSON
- `GET /health` - Health check
- `GET /status.json` - Legacy compatibility (redirect or alias)

**Data collected:**

- Node counts (control-plane, GPU)
- CPU/memory from metrics-server
- Pod status list
- GPU metrics from DCGM exporter
- ArgoCD application sync status

### Phase 2: Update Backend Services

#### Stargazer-api Changes

Currently expects requests at `/best`, `/locations`, etc. Needs to handle `/stargazer/*` prefix.

**Option A: FastAPI path prefix**

```python
app = FastAPI()
router = APIRouter(prefix="/stargazer")
# ... mount all routes on router
```

**Option B: Strip prefix in HTTPRoute** (if operator supports it)

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
spec:
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /stargazer
      filters:
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
```

**Recommendation**: Option A - simpler, no operator changes needed.

#### Trips-nginx Changes

Verify WebSocket requirements:

- [ ] Check if trips-api actually uses WebSockets
- [ ] If yes, verify Cloudflare Tunnel handles upgrade natively
- [ ] If no, remove unnecessary nginx WebSocket config

### Phase 3: Create HTTPRoute Resources

Replace nginx routing with declarative HTTPRoute CRDs.

**`overlays/prod/trips/httproute.yaml`:**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: trips
  namespace: trips
spec:
  parentRefs:
    - name: cloudflare-gateway
      namespace: cloudflare-tunnel
  hostnames:
    - "api.jomcgi.dev"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /trips
      backendRefs:
        - name: trips-nginx
          port: 80
```

**`overlays/prod/stargazer/httproute.yaml`:**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: stargazer
  namespace: stargazer
spec:
  parentRefs:
    - name: cloudflare-gateway
      namespace: cloudflare-tunnel
  hostnames:
    - "api.jomcgi.dev"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /stargazer
      backendRefs:
        - name: stargazer-api
          port: 80
```

**`overlays/prod/cluster-info/httproute.yaml`:**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: cluster-info
  namespace: cluster-info
spec:
  parentRefs:
    - name: cloudflare-gateway
      namespace: cloudflare-tunnel
  hostnames:
    - "api.jomcgi.dev"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /cluster-info
        - path:
            type: Exact
            value: /status.json
      backendRefs:
        - name: cluster-info
          port: 80
```

### Phase 4: Cloudflare Transform Rules

Add caching headers at the edge instead of in nginx.

**Cloudflare Dashboard → Rules → Transform Rules → Modify Response Headers:**

| Rule Name         | Match                          | Action                                                       |
| ----------------- | ------------------------------ | ------------------------------------------------------------ |
| API Cache Headers | `hostname eq "api.jomcgi.dev"` | Add `Cache-Control: s-maxage=30, stale-while-revalidate=300` |

Alternatively, manage via Terraform/Pulumi if infrastructure-as-code is preferred.

### Phase 5: Deprecate api-gateway

1. Deploy cluster-info service
2. Deploy HTTPRoute resources
3. Verify routing works via new path
4. Update Cloudflare Tunnel to remove api-gateway route
5. Delete `charts/api-gateway/` and overlay

---

## Cloudflare Operator Enhancements Needed

The current operator may need these additions:

| Feature                          | Status     | Required For                            |
| -------------------------------- | ---------- | --------------------------------------- |
| HTTPRoute path rewriting         | ❌ Missing | Stargazer (if not fixing backend)       |
| Cross-namespace backendRefs      | ❓ Check   | Routing to services in other namespaces |
| Multiple hostnames per HTTPRoute | ❓ Check   | api.jomcgi.dev with path-based routing  |

### Path Rewriting Implementation (if needed)

Add URLRewrite filter support to HTTPRoute controller:

```go
// internal/controller/httproute_controller.go
func (r *HTTPRouteReconciler) buildIngressRule(rule gatewayv1.HTTPRouteRule) IngressRule {
    for _, filter := range rule.Filters {
        if filter.Type == gatewayv1.HTTPRouteFilterURLRewrite {
            // Apply path rewrite to ingress config
        }
    }
}
```

---

## Migration Checklist

### Pre-Migration

- [ ] Create cluster-info chart
- [ ] Build and push cluster-info image
- [ ] Update stargazer-api to handle /stargazer prefix
- [ ] Verify trips-nginx WebSocket requirements
- [ ] Test HTTPRoute resources in dev environment

### Migration

- [ ] Deploy cluster-info service to prod
- [ ] Deploy HTTPRoute resources
- [ ] Add Cloudflare Transform Rule for caching
- [ ] Update tunnel config to route via HTTPRoutes
- [ ] Verify all endpoints work:
  - [ ] `api.jomcgi.dev/trips/*`
  - [ ] `api.jomcgi.dev/stargazer/*`
  - [ ] `api.jomcgi.dev/cluster-info`
  - [ ] `api.jomcgi.dev/status.json`

### Post-Migration

- [ ] Monitor for errors in SigNoz
- [ ] Remove api-gateway from ArgoCD
- [ ] Delete `charts/api-gateway/`
- [ ] Delete `overlays/*/api-gateway/`
- [ ] Update architecture docs

---

## Rollback Plan

If issues arise:

1. Re-add api-gateway route to tunnel config
2. HTTPRoute resources can coexist (lower priority)
3. No data loss - all changes are routing only

---

## Benefits

1. **Simpler architecture**: No nginx middleman
2. **Declarative routing**: HTTPRoute CRDs instead of ConfigMaps
3. **Better separation of concerns**: Metrics collection is standalone
4. **Native Gateway API**: Standard Kubernetes patterns
5. **Fewer moving parts**: One less deployment to maintain
6. **Edge caching**: Cloudflare handles headers natively

## Risks

| Risk                   | Mitigation                                                 |
| ---------------------- | ---------------------------------------------------------- |
| HTTPRoute feature gaps | Test thoroughly in dev; keep api-gateway as fallback       |
| WebSocket breakage     | Verify Cloudflare Tunnel handles upgrades before migration |
| Collector data gaps    | Test cluster-info service independently before cutover     |
| Path routing conflicts | Careful ordering of HTTPRoute rules by specificity         |

---

## Timeline Estimate

| Phase   | Scope                                   |
| ------- | --------------------------------------- |
| Phase 1 | cluster-info service chart + deployment |
| Phase 2 | Backend path handling updates           |
| Phase 3 | HTTPRoute resources + testing           |
| Phase 4 | Cloudflare Transform Rules              |
| Phase 5 | Cutover + cleanup                       |

---

## Open Questions

1. **Should cluster-info be its own subdomain?** (e.g., `status.jomcgi.dev` instead of `api.jomcgi.dev/cluster-info`)
2. **Do we need the legacy `/status.json` endpoint?** Or can we break that?
3. **Should caching be per-endpoint?** Different TTLs for /trips vs /cluster-info?

---

## References

- Current api-gateway: `charts/api-gateway/`
- Cloudflare operator: `operators/cloudflare/`
- Gateway API spec: https://gateway-api.sigs.k8s.io/
- Cloudflare Transform Rules: https://developers.cloudflare.com/rules/transform/
