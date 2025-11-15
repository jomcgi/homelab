# Cloudflare Operator Design - Modern Routes API

## Architecture Overview

The operator manages Cloudflare tunnel ingress using three CRDs that work together:

1. **CloudflareAccessPolicy** - Reusable Zero Trust policies
2. **CloudflareAccessApplication** - Zero Trust applications (per hostname)
3. **CloudflarePublishedRoute** - Published routes (creates DNS + routing)

## Design Principles

- **Secure by default** - Zero Trust enabled unless explicitly disabled
- **Simple interfaces** - Annotations on Services create everything automatically
- **Reusable policies** - Create once, reference many times
- **Flexible policy sources** - Create new policies OR reference existing ones from Cloudflare

## CRD Definitions

### 1. CloudflareAccessPolicy

Manages Zero Trust access policies. Can either **create a new policy** or **reference an existing one**.

```yaml
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflareAccessPolicy
metadata:
  name: joe-only
spec:
  # Option 1: Create a new policy (mutually exclusive with externalID)
  name: "Joe Only"
  decision: allow  # allow, deny, non_identity, bypass
  rules:
    - name: "Allow @jomcgi.dev emails"
      emails_ending_in: ["@jomcgi.dev"]
    - name: "Allow specific IPs"
      ip_ranges: ["1.2.3.4/32"]

  # Option 2: Reference existing policy (mutually exclusive with rules)
  # externalID: "abc123def456"  # Policy UUID from Cloudflare dashboard

status:
  policyID: "abc123def456"  # Cloudflare policy UUID
  ready: true
  conditions: [...]
```

**Reconciliation logic:**
- If `spec.externalID` is set → Fetch policy from Cloudflare, validate it exists
- If `spec.rules` is set → Create/update policy via Cloudflare API
- Update `status.policyID` with Cloudflare UUID

---

### 2. CloudflareAccessApplication

Manages Zero Trust applications (self-hosted apps with policies attached).

```yaml
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflareAccessApplication
metadata:
  name: app-jomcgi-dev
spec:
  # Application configuration
  domain: app.jomcgi.dev
  name: "My App"  # Optional, defaults to domain
  type: self_hosted  # self_hosted, saas, ssh, vnc, etc.

  # Session configuration
  sessionDuration: "24h"  # Optional, default 24h

  # Policy references (can mix CRD refs and external IDs)
  policies:
    - policyRef:
        name: joe-only  # Reference to CloudflareAccessPolicy CRD
    - externalPolicyID: "xyz789"  # Reference to existing Cloudflare policy

  # CORS configuration (optional)
  corsHeaders:
    allowAllOrigins: false
    allowedOrigins: ["https://app.jomcgi.dev"]
    allowedMethods: ["GET", "POST"]
    allowCredentials: true

status:
  applicationID: "app-uuid-123"
  ready: true
  policyIDs: ["policy-uuid-1", "policy-uuid-2"]
  conditions: [...]
```

**Reconciliation logic:**
1. Resolve all policy references (CRD refs → status.policyID, external IDs → validate)
2. Create/update Access Application via Cloudflare API
3. Attach policies to application
4. Update `status.applicationID`

---

### 3. CloudflarePublishedRoute

Manages published application routes. **Automatically creates DNS records** and routes traffic.

```yaml
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflarePublishedRoute
metadata:
  name: app-jomcgi-dev-route
spec:
  # Route configuration
  hostname: app.jomcgi.dev
  service: http://my-service.default.svc:8080

  # Tunnel reference (defaults to default-daemon-tunnel in daemon mode)
  tunnelRef:
    name: default-daemon-tunnel  # Automatically set by operator

  # Zero Trust integration (optional)
  accessApplicationRef:
    name: app-jomcgi-dev  # Reference to CloudflareAccessApplication CRD

  # Path-based routing (optional)
  path: ""  # Default: all paths (*)

  # Advanced options (optional)
  noTLSVerify: false
  http2Origin: false
  httpHostHeader: ""  # Override Host header sent to origin

status:
  routeID: "route-uuid-123"
  dnsRecordID: "dns-uuid-456"  # Created automatically
  tunnelID: "tunnel-uuid-789"  # Resolved from tunnelRef
  ready: true
  conditions: [...]
```

**Reconciliation logic:**
1. Resolve tunnel reference → get tunnel ID and CNAME target
2. Resolve access application reference (if set) → get app ID
3. Create/update published route via Cloudflare API
   - **Route API automatically creates DNS CNAME**
   - Route links to access application (if provided)
4. Update `status.routeID` and `status.dnsRecordID`

---

## Annotation-Driven Workflow

### Simple Service (No Zero Trust)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-api
  annotations:
    cloudflare.ingress.hostname: api.jomcgi.dev
    cloudflare.zero-trust.enabled: "false"  # Disable Zero Trust
spec:
  selector:
    app: my-api
  ports:
    - port: 8080
```

**Operator creates:**
- ✅ CloudflarePublishedRoute only (DNS + routing)

---

### Secure Service (Zero Trust Enabled - Default)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-secure-app
  annotations:
    cloudflare.ingress.hostname: secure.jomcgi.dev
    cloudflare.zero-trust.policy: joe-only  # Reference to policy
spec:
  selector:
    app: my-secure-app
  ports:
    - port: 8080
```

**Operator creates:**
1. ✅ CloudflareAccessPolicy (if `joe-only` CRD doesn't exist, operator can auto-create from annotation or fail)
2. ✅ CloudflareAccessApplication (with policy attached)
3. ✅ CloudflarePublishedRoute (with access application, creates DNS)

---

### Inline Policy Definition

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
  annotations:
    cloudflare.ingress.hostname: app.jomcgi.dev
    cloudflare.zero-trust.policy-inline: |
      decision: allow
      rules:
        - emails: ["joe@jomcgi.dev"]
spec:
  selector:
    app: my-app
  ports:
    - port: 8080
```

**Operator creates:**
1. ✅ CloudflareAccessPolicy (auto-generated from inline YAML)
2. ✅ CloudflareAccessApplication (with auto-generated policy)
3. ✅ CloudflarePublishedRoute (with access application, creates DNS)

---

## Reconciliation Order

The operator must reconcile in dependency order:

```
1. CloudflareAccessPolicy
   ↓ (status.policyID available)
2. CloudflareAccessApplication
   ↓ (status.applicationID available)
3. CloudflarePublishedRoute
   ↓ (DNS + routing created)
```

### Controller Dependencies

Each controller watches its dependencies:

**AccessPolicyController:**
- No dependencies
- Watches: CloudflareAccessPolicy CRDs

**AccessApplicationController:**
- Depends on: CloudflareAccessPolicy (via `spec.policies[].policyRef`)
- Watches: CloudflareAccessApplication CRDs, CloudflareAccessPolicy CRDs
- Requeues when referenced policy's status changes

**PublishedRouteController:**
- Depends on: CloudflareTunnel, CloudflareAccessApplication
- Watches: CloudflarePublishedRoute CRDs, CloudflareTunnel CRDs, CloudflareAccessApplication CRDs
- Requeues when referenced tunnel/app status changes

**ServiceAnnotationController:**
- Watches: Services with `cloudflare.ingress.hostname` annotation
- Creates: CloudflareAccessPolicy, CloudflareAccessApplication, CloudflarePublishedRoute CRDs
- Uses owner references to link CRDs to Service

---

## Example Flows

### Flow 1: Manual CRD Creation

```yaml
# 1. Create reusable policy
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflareAccessPolicy
metadata:
  name: engineering-team
spec:
  name: "Engineering Team"
  decision: allow
  rules:
    - emails_ending_in: ["@company.com"]
    - github_users: ["jomcgi"]

---
# 2. Create access application
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflareAccessApplication
metadata:
  name: admin-dashboard
spec:
  domain: admin.jomcgi.dev
  policies:
    - policyRef:
        name: engineering-team

---
# 3. Create published route
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflarePublishedRoute
metadata:
  name: admin-dashboard-route
spec:
  hostname: admin.jomcgi.dev
  service: http://admin.default.svc:80
  tunnelRef:
    name: default-daemon-tunnel
  accessApplicationRef:
    name: admin-dashboard
```

**Result:**
- DNS CNAME: `admin.jomcgi.dev` → `<tunnel-uuid>.cfargotunnel.com`
- Traffic: `https://admin.jomcgi.dev` → tunnel → `http://admin.default.svc:80`
- Zero Trust: Login required (engineering team only)

---

### Flow 2: Service Annotation (Automatic)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
  annotations:
    cloudflare.ingress.hostname: app.jomcgi.dev
    cloudflare.zero-trust.policy: engineering-team
spec:
  selector:
    app: my-app
  ports:
    - port: 8080
```

**Operator automatically creates:**
```yaml
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflareAccessApplication
metadata:
  name: app-jomcgi-dev-auto
  ownerReferences:
    - apiVersion: v1
      kind: Service
      name: my-app
spec:
  domain: app.jomcgi.dev
  policies:
    - policyRef:
        name: engineering-team

---
apiVersion: tunnels.cloudflare.io/v1
kind: CloudflarePublishedRoute
metadata:
  name: app-jomcgi-dev-route-auto
  ownerReferences:
    - apiVersion: v1
      kind: Service
      name: my-app
spec:
  hostname: app.jomcgi.dev
  service: http://my-app.default.svc:8080
  tunnelRef:
    name: default-daemon-tunnel
  accessApplicationRef:
    name: app-jomcgi-dev-auto
```

**When Service is deleted:**
- Owner references ensure all CRDs are automatically deleted
- Operator reconciliation deletes DNS + routes from Cloudflare

---

## Supported Annotations

| Annotation | Required | Default | Description |
|------------|----------|---------|-------------|
| `cloudflare.ingress.hostname` | Yes | - | Hostname for ingress (e.g., `app.jomcgi.dev`) |
| `cloudflare.zero-trust.enabled` | No | `true` | Enable Zero Trust authentication |
| `cloudflare.zero-trust.policy` | No | - | Reference to CloudflareAccessPolicy CRD name |
| `cloudflare.zero-trust.policy-inline` | No | - | Inline policy definition (YAML) |
| `cloudflare.service.port` | No | First port | Service port to use |
| `cloudflare.service.protocol` | No | `http` | Protocol (`http`, `https`, `tcp`, `ssh`) |
| `cloudflare.tls.verify` | No | `true` | Verify TLS certificate on origin |

**Note:** The operator uses a single shared tunnel (`default-daemon-tunnel`) in daemon mode. Multi-tunnel support may be added in the future.

---

## Migration from Old Approach

### Old (TunnelConfiguration API)

```go
// Don't do this anymore
r.CFClient.UpdateTunnelConfiguration(ctx, accountID, tunnelID, cloudflare.TunnelConfiguration{
    Ingress: []cloudflare.UnvalidatedIngressRule{
        {Hostname: "app.jomcgi.dev", Service: "http://svc:8080"},
        {Service: "http_status:404"},
    },
})
```

### New (Published Routes API)

```go
// For each route, create a published route via API
route := cloudflare.TunnelRoute{
    Hostname: "app.jomcgi.dev",
    Service:  "http://svc:8080",
    TunnelID: tunnelID,
}
r.CFClient.CreateTunnelRoute(ctx, accountID, route)

// DNS CNAME is created automatically by the Routes API
```

---

## Implementation Tasks

### Phase 1: CRD Definitions
- [ ] Define CloudflareAccessPolicy API types
- [ ] Define CloudflareAccessApplication API types
- [ ] Define CloudflarePublishedRoute API types
- [ ] Generate CRD manifests and deepcopy code
- [ ] Update Helm chart with new CRDs

### Phase 2: Cloudflare Client
- [ ] Add Zero Trust Policy API methods
- [ ] Add Zero Trust Application API methods
- [ ] Add Published Routes API methods (replaces TunnelConfiguration)
- [ ] Add DNS record verification methods

### Phase 3: Controllers
- [ ] Implement AccessPolicyController
- [ ] Implement AccessApplicationController
- [ ] Implement PublishedRouteController
- [ ] Update CloudflareTunnelController to remove old config logic

### Phase 4: Service Annotation Controller
- [ ] Implement Service annotation watching
- [ ] Implement automatic CRD generation from annotations
- [ ] Add owner references for cleanup
- [ ] Add validation and error handling

### Phase 5: Testing & Documentation
- [ ] Integration tests for complete flow
- [ ] Update README with new architecture
- [ ] Add examples directory with common patterns
- [ ] Migration guide from old approach

---

## Open Questions

1. **Policy defaults** - Should we create a default "allow all authenticated" policy?
2. **Multi-path routes** - How to handle multiple paths for same hostname?
3. **Route priority** - Does Cloudflare support route ordering?
4. **Tunnel selection** - Support multiple tunnels per cluster?
5. **Validation webhooks** - Add admission webhooks to validate CRD fields?
