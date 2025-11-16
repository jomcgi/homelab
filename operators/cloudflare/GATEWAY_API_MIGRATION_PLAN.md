# Cloudflare Operator: Gateway API Migration Plan

**Architecture:** Gateway API with annotation-driven workflow

## Phase 1: Gateway API CRD Definitions & Installation

### 1.1 Install Gateway API CRDs
- Add Gateway API CRD dependency to operator Helm chart
- Version: v1.2.0+ (stable HTTPRoute, Gateway, GatewayClass)
- Document CRD installation in operator README

### 1.2 Define CloudflareAccessPolicy CRD
- Create API types in `api/v1/cloudflareaccesspolicy_types.go`
- Policy attachment pattern (targets HTTPRoute or Gateway)
- Spec: application config, policies (rules, decision), session duration
- Status: policyID, applicationID, ready conditions
- Generate CRD manifests and deepcopy code

### 1.3 Update Helm Chart
- Add CloudflareAccessPolicy CRD to chart
- Remove old CloudflareTunnel CRD (breaking change - document migration)
- Add GatewayClass resource with Cloudflare credentials reference

---

## Phase 2: Core Gateway API Controllers

### 2.1 GatewayClass Controller
- Watch: GatewayClass with `controllerName: github.com/jomcgi/homelab/operators/cloudflare`
- Reconcile: Validate credentials secret, set Ready condition
- Status: Mark as Accepted, set supportedFeatures

### 2.2 Gateway Controller
- Watch: Gateway resources with `gatewayClassName: cloudflare`
- Create: Cloudflare tunnel via API (using credentials from GatewayClass)
- Deploy: cloudflared Deployment/Service in Gateway namespace
- Manage: Tunnel lifecycle (create, monitor, delete with finalizers)
- Status: Update with tunnel ID, connection status, addresses

### 2.3 HTTPRoute Controller
- Watch: HTTPRoute resources with `parentRef` to Cloudflare Gateway
- Create: Published route in Cloudflare for each hostname
- Create: DNS CNAME record automatically (hostname → tunnel)
- Delete: Clean up DNS and routes (finalizers)
- Status: Update with route IDs, parent status, conditions

### 2.4 CloudflareAccessPolicy Controller
- Watch: CloudflareAccessPolicy CRDs
- Resolve: targetRef (HTTPRoute or Gateway)
- Create: Access Application for domain (from HTTPRoute hostname)
- Create: Access Policies via Cloudflare API
- Link: Application to published route
- Status: Update with policy/application IDs, ready conditions

---

## Phase 3: Service Annotation Controller (Annotation → Gateway API)

### 3.1 Service Annotation Watcher
- Watch: Services with `cloudflare.ingress.hostname` annotation
- Parse: All cloudflare.* annotations
- Generate: HTTPRoute, CloudflareAccessPolicy CRDs
- Owner references: Link generated resources to Service for cleanup

### 3.2 Annotation Mapping

**Service annotations:**
```yaml
cloudflare.ingress.hostname: app.jomcgi.dev  # Required
cloudflare.zero-trust.enabled: "true"        # Default true
cloudflare.zero-trust.policy: joe-only       # Policy name
cloudflare.service.port: "8080"              # Default: first port
```

**Generates Gateway API resources:**
```yaml
# Created once per cluster (or namespace)
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: cloudflare-gateway
spec:
  gatewayClassName: cloudflare
  listeners:
  - name: https
    protocol: HTTPS
    port: 443

---
# Created per Service
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app-route
  ownerReferences: [Service/my-app]
spec:
  parentRefs:
  - name: cloudflare-gateway
  hostnames:
  - app.jomcgi.dev
  rules:
  - backendRefs:
    - name: my-app
      port: 8080

---
# Created if zero-trust.enabled=true
apiVersion: tunnels.cloudflare.io/v1alpha1
kind: CloudflareAccessPolicy
metadata:
  name: my-app-access
  ownerReferences: [Service/my-app]
spec:
  targetRef:
    kind: HTTPRoute
    name: my-app-route
  policies:
  - policyRef:
      name: joe-only
```

### 3.3 Gateway Selection Strategy
- Default: Use cluster-wide `cloudflare-gateway` (create if doesn't exist)
- Namespace-scoped: Check for Gateway in Service namespace first
- Configurable: Add annotation `cloudflare.gateway.name` for explicit selection

---

## Phase 4: Cloudflare API Client Updates

### 4.1 Published Routes API
- Add `CreatePublishedRoute()` method
- Add `DeletePublishedRoute()` method
- Add `ListPublishedRoutes()` for reconciliation
- Update telemetry/tracing

### 4.2 DNS Management API
- Add `CreateDNSRecord()` (CNAME for tunnel)
- Add `DeleteDNSRecord()`
- Add `ListDNSRecords()` for cleanup

### 4.3 Access API
- Add `CreateAccessApplication()`
- Add `UpdateAccessApplication()`
- Add `DeleteAccessApplication()`
- Add `CreateAccessPolicy()`
- Add `LinkPolicyToApplication()`

---

## Phase 5: Migration & Documentation

### 5.1 Update DESIGN.md
- Document Gateway API architecture
- Show annotation → Gateway API mapping
- Provide examples for both annotations and direct Gateway API usage
- Migration guide from CloudflareTunnel CRD

### 5.2 Update Test Application
- Keep Service annotations (already done)
- Add example showing direct Gateway API usage (optional)
- Update README with new architecture

### 5.3 Breaking Changes
- CloudflareTunnel CRD → Gateway replacement
- Old UpdateTunnelConfiguration() API removed
- Provide migration script/documentation

---

## Phase 6: Validation & Testing

### 6.1 Integration Tests
- Test: Service annotation → HTTPRoute generation
- Test: HTTPRoute → Published route + DNS creation
- Test: CloudflareAccessPolicy → Access app creation
- Test: Service deletion → Cleanup (finalizers)

### 6.2 E2E Test
- Deploy test Services with annotations
- Verify DNS records created in Cloudflare
- Verify routes accessible via tunnel
- Verify Zero Trust login flow

---

## Implementation Order

1. **Install Gateway API CRDs** (dependency)
2. **Define CloudflareAccessPolicy CRD** (new API type)
3. **Implement GatewayClass controller** (foundation)
4. **Implement Gateway controller** (tunnel management)
5. **Implement HTTPRoute controller** (routing + DNS)
6. **Implement CloudflareAccessPolicy controller** (Zero Trust)
7. **Implement Service annotation controller** (convenience layer)
8. **Update Cloudflare client** (new API methods)
9. **Update documentation** (DESIGN.md, examples)
10. **Testing** (integration + e2e)

---

## Key Benefits

✅ **Standard Kubernetes API** - Gateway API is the future of ingress
✅ **Simple developer experience** - Annotations just work
✅ **Full power available** - Advanced users can use Gateway API directly
✅ **Automatic DNS management** - No manual CNAME creation
✅ **Secure by default** - Zero Trust enabled unless disabled
✅ **Proper cleanup** - Finalizers prevent orphaned resources

---

## Files to Create/Modify

### New Files
- `api/v1/cloudflareaccesspolicy_types.go`
- `internal/controller/gatewayclass_controller.go`
- `internal/controller/gateway_controller.go`
- `internal/controller/httproute_controller.go`
- `internal/controller/cloudflareaccesspolicy_controller.go`
- `internal/controller/service_controller.go` (annotation watcher)
- `internal/cloudflare/routes.go` (Published Routes API)
- `internal/cloudflare/dns.go` (DNS API)
- `internal/cloudflare/access.go` (Access API)

### Modified Files
- `operators/cloudflare/DESIGN.md` (Gateway API architecture)
- `operators/cloudflare/README.md` (update status, migration guide)
- `operators/cloudflare/helm/cloudflare-operator/values.yaml` (GatewayClass config)
- `operators/cloudflare/helm/cloudflare-operator/templates/` (add GatewayClass, remove CloudflareTunnel CRD)

### Deprecated/Removed
- `api/v1/cloudflaretunnel_types.go` (replaced by Gateway)
- `internal/controller/cloudflaretunnel_controller.go` (replaced by Gateway controller)

---

## Next Steps

Ready to start implementation?
