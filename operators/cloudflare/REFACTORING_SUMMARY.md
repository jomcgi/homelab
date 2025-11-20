# Cloudflare Operator Refactoring - Summary & Next Steps

**Status**: ✅ Plan Reviewed - Ready for Implementation  
**Priority**: 🔥 Phase 0 (Immediate Stability Fixes) should be implemented FIRST  
**Breaking Changes**: ✅ Approved (not GA, can move fast)

---

## Executive Summary

### Critical Finding: Rate Limiting Bug 🚨

**Your current code EXCEEDS Cloudflare's rate limit and will cause cascading failures!**

- **Cloudflare Limit**: 1200 req/5min = **4 req/sec average** ([Source](https://developers.cloudflare.com/fundamentals/api/reference/limits/))
- **Current Code**: 10 req/sec (operators/cloudflare/internal/cloudflare/client.go:83)
- **Impact**: Triggers HTTP 429 errors → **5-minute ban on ALL API calls**
- **Fix**: Reduce to 3 req/sec with burst 10 (safety buffer under 4 req/sec)

**This should be fixed IMMEDIATELY before any other refactoring work.**

---

## Architecture Decision

### User-Facing vs Internal

✅ **APPROVED**: CloudflareTunnel CRD is an **internal implementation detail**

```
┌─────────────────────────────────────────────────────────────┐
│ USER LAYER (Gateway API - Kubernetes standard)             │
│   - Gateway (creates tunnel)                                │
│   - HTTPRoute (creates routes + DNS)                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ INTERNAL LAYER (CloudflareTunnel CRD - operator state)     │
│   - Single source of truth for tunnel lifecycle            │
│   - Protected status fields (not user-modifiable)          │
│   - Automatic cleanup via OwnerReferences                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ EXTERNAL API (Cloudflare)                                  │
│   - Tunnel management                                       │
│   - DNS records                                             │
│   - Published routes                                        │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Users only interact with Gateway API** - Standard Kubernetes ingress patterns
2. **CloudflareTunnel CRD is hidden** - Don't document in user examples
3. **No backward compatibility needed** - Breaking changes OK (not GA)
4. **Stability over features** - Fix bugs first, refactor second

---

## Implementation Plan

### Phase 0: Immediate Stability Fixes (2-4 hours) 🔥 PRIORITY

**Goal**: Fix critical bugs causing production instability

#### Task 0.1: Fix Rate Limiting

**File**: `operators/cloudflare/internal/cloudflare/client.go:82-83`

```go
// BEFORE (WRONG!)
limiter := rate.NewLimiter(rate.Limit(10), 20)

// AFTER (CORRECT)
limiter := rate.NewLimiter(rate.Limit(3), 10)  // 3 req/sec, burst 10
```

**Why**: Current limit exceeds Cloudflare's 4 req/sec average, causes 5-minute bans.

---

#### Task 0.2: Add Circuit Breaker (gobreaker)

**File**: `operators/cloudflare/internal/cloudflare/client.go`

**Add dependency**:

```bash
cd operators/cloudflare
go get github.com/sony/gobreaker@latest
```

**Update TunnelClient struct**:

```go
import "github.com/sony/gobreaker"

type TunnelClient struct {
    api            *cloudflare.API
    limiter        *rate.Limiter
    circuitBreaker *gobreaker.CircuitBreaker  // NEW
    tracer         trace.Tracer
}
```

**Circuit breaker settings**:

```go
cbSettings := gobreaker.Settings{
    Name:        "cloudflare-api",
    MaxRequests: 3,                    // Allow 3 requests in half-open state
    Interval:    60 * time.Second,     // Reset failure count after 60s
    Timeout:     30 * time.Second,     // Stay open for 30s before half-open
    ReadyToTrip: func(counts gobreaker.Counts) bool {
        return counts.ConsecutiveFailures >= 5  // Open after 5 failures
    },
    OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
        log.Printf("Circuit breaker %s: %s -> %s", name, from, to)
    },
}

circuitBreaker := gobreaker.NewCircuitBreaker(cbSettings)
```

**Wrap all API calls**:

```go
func (c *TunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
    // Rate limiting
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, "", err
    }

    // Circuit breaker
    result, err := c.circuitBreaker.Execute(func() (interface{}, error) {
        return c.createTunnelInternal(ctx, accountID, name)
    })

    if err != nil {
        return nil, "", err
    }

    tunnel := result.(*tunnelWithSecret)
    return tunnel.Tunnel, tunnel.Secret, nil
}
```

**Why**: Prevents cascading failures when Cloudflare API is degraded. Production-tested library.

---

#### Task 0.3: Remove Obsolete Documentation

```bash
cd operators/cloudflare
rm GATEWAY_API_MIGRATION_PLAN.md  # Already using Gateway API
rm DESIGN.md                        # Describes unimplemented architecture
```

**Why**: Stale docs cause confusion. Current implementation already uses Gateway API correctly.

---

### Phase 1: Enhanced CloudflareTunnel CRD (Week 1)

**Goal**: Add comprehensive status tracking to CloudflareTunnel CRD

#### Changes to `api/v1/cloudflaretunnel_types.go`:

**Add to status**:

```go
type CloudflareTunnelStatus struct {
    Conditions         []metav1.Condition `json:"conditions,omitempty"`
    TunnelID           string             `json:"tunnelId,omitempty"`
    AccountID          string             `json:"accountID,omitempty"`        // NEW
    SecretName         string             `json:"secretName,omitempty"`       // NEW
    TunnelName         string             `json:"tunnelName,omitempty"`       // NEW
    Connections        []TunnelConnection `json:"connections,omitempty"`      // NEW
    DNSRecords         []DNSRecord        `json:"dnsRecords,omitempty"`       // NEW - CRITICAL
    LastSyncTime       *metav1.Time       `json:"lastSyncTime,omitempty"`     // NEW
    Active             bool               `json:"active"`
    Ready              bool               `json:"ready"`
    ObservedGeneration int64              `json:"observedGeneration,omitempty"`
}

type TunnelConnection struct {
    ID          string       `json:"id"`
    ColoName    string       `json:"coloName,omitempty"`
    IsConnected bool         `json:"isConnected"`
    ConnectedAt *metav1.Time `json:"connectedAt,omitempty"`
}

type DNSRecord struct {
    Hostname string `json:"hostname"`
    RecordID string `json:"recordID"`
    ZoneID   string `json:"zoneID"`
}
```

**Status Conditions**:

- `Ready` - Tunnel is created and ready to serve traffic
- `TunnelProvisioned` - Tunnel exists in Cloudflare
- `SecretsReady` - Credentials are generated and stored
- `ConfigurationValid` - Tunnel configuration is valid
- `Degraded` - Tunnel exists but has issues

**CRD Upgrade Strategy**:
Since you're OK with breaking changes:

1. Delete existing CloudflareTunnel CRDs: `kubectl delete cloudflaretunnels --all -A`
2. Apply new CRD with updated schema
3. Gateways will recreate tunnels automatically (OwnerReferences)

---

### Phase 2: Refactor Controllers (Week 2)

**Goal**: Move Cloudflare API calls to CloudflareTunnel controller only

#### Gateway Controller Changes:

- **REMOVE**: Direct Cloudflare API calls
- **ADD**: Create/manage CloudflareTunnel CRD
- **ADD**: Watch CloudflareTunnel status changes

```go
func (r *GatewayReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&gatewayv1.Gateway{}).
        Owns(&appsv1.Deployment{}).
        Owns(&corev1.Secret{}).
        Owns(&tunnelsv1.CloudflareTunnel{}).  // NEW: Watch owned tunnels
        Complete(r)
}
```

#### HTTPRoute Controller Changes:

- **REMOVE**: Direct DNS API calls
- **ADD**: Update CloudflareTunnel.Spec.Ingress with routes
- **ADD**: Watch CloudflareTunnel status for DNS record IDs

#### CloudflareTunnel Controller Changes:

- **Single responsibility**: Manage Cloudflare API only
- **Parse Spec.Ingress**: Extract hostnames, create DNS records
- **Update Status**: Store DNS record IDs, connection status
- **Handle finalizers**: Clean up Cloudflare resources

---

### Phase 3: Testing & Observability (Week 3)

**Goal**: Ensure reliability and debuggability

#### Testing:

- Unit tests for all controllers
- Integration tests with envtest
- E2E test: Service → Gateway → CloudflareTunnel → Cloudflare API

#### Observability:

- Enable metrics by default (`:8443/metrics`)
- Enable leader election for HA (2 replicas)
- Add Prometheus metrics:
  - `cloudflare_tunnel_reconcile_duration_seconds`
  - `cloudflare_api_call_duration_seconds`
  - `cloudflare_tunnel_connections` (gauge)

#### Admission Webhooks:

- Validate CloudflareTunnel on create/update
- Prevent invalid ingress rules
- Check hostname format (RFC 1123)

---

## Key Files to Modify

### Immediate (Phase 0):

- ✅ `internal/cloudflare/client.go` - Fix rate limiting + add gobreaker
- ✅ Delete `GATEWAY_API_MIGRATION_PLAN.md`
- ✅ Delete `DESIGN.md`

### Week 1 (Phase 1):

- `api/v1/cloudflaretunnel_types.go` - Add status fields
- `internal/controller/cloudflaretunnel_controller.go` - Enhanced reconciliation

### Week 2 (Phase 2):

- `internal/controller/gateway_controller.go` - Create CloudflareTunnel CRDs
- `internal/controller/httproute_controller.go` - Update tunnel ingress
- `internal/cloudflare/dns.go` (NEW) - DNS management methods

### Week 3 (Phase 3):

- `internal/controller/*_test.go` - Unit + integration tests
- `test/e2e/full_flow_test.go` (NEW) - E2E test
- `api/v1/cloudflaretunnel_webhook.go` (NEW) - Admission webhooks
- `helm/cloudflare-operator/values.yaml` - Enable metrics + leader election

---

## Migration Strategy

### Breaking Changes (Acceptable):

1. CloudflareTunnel CRD schema change (add DNSRecords field)
2. Remove annotation-based state storage
3. Remove backward compatibility code
4. Delete obsolete docs

### Upgrade Path:

```bash
# 1. Delete old CRDs
kubectl delete cloudflaretunnels --all -A

# 2. Deploy new operator version
helm upgrade cloudflare-operator ./helm/cloudflare-operator

# 3. Gateways automatically recreate tunnels
# (OwnerReferences trigger reconciliation)
```

**Rollback Plan**:

```bash
# Revert to previous Helm release
helm rollback cloudflare-operator -n cloudflare-system
```

---

## Success Criteria

### Phase 0 (Immediate):

- ✅ No more HTTP 429 errors from Cloudflare
- ✅ Circuit breaker prevents cascading failures
- ✅ Stale documentation removed

### Phase 1:

- ✅ CloudflareTunnel CRD has comprehensive status
- ✅ `kubectl describe cloudflaretunnel` shows all state
- ✅ DNS records tracked in CRD status

### Phase 2:

- ✅ Only CloudflareTunnel controller calls Cloudflare API
- ✅ Gateway/HTTPRoute controllers use CRD only
- ✅ Automatic cleanup via OwnerReferences

### Phase 3:

- ✅ Unit test coverage >80%
- ✅ E2E test passes (Service → live tunnel)
- ✅ Metrics exported and queryable
- ✅ Leader election works (2 replicas)

---

## Open Questions (RESOLVED)

1. ~~Rate limiting too aggressive?~~ → **NO - Current limit EXCEEDS Cloudflare's, must reduce**
2. ~~Use custom circuit breaker?~~ → **NO - Use gobreaker (production-tested)**
3. ~~Support backward compatibility?~~ → **NO - Breaking changes OK (not GA)**
4. ~~Gradual rollout?~~ → **NO - Fast iteration, fix bugs quickly**

---

## Next Action

**START HERE** → Implement Phase 0 (Immediate Stability Fixes)

```bash
# 1. Fix rate limiting
cd operators/cloudflare
# Edit internal/cloudflare/client.go line 82-83
# Change: rate.NewLimiter(rate.Limit(10), 20)
# To:     rate.NewLimiter(rate.Limit(3), 10)

# 2. Add gobreaker
go get github.com/sony/gobreaker@latest
# Add circuit breaker to TunnelClient (see detailed code above)

# 3. Delete stale docs
rm GATEWAY_API_MIGRATION_PLAN.md DESIGN.md

# 4. Test
go test ./internal/cloudflare/...

# 5. Commit
git add -A
git commit -m "fix: Reduce rate limiting to 3 req/sec and add circuit breaker

- Fix rate limit (10 req/sec exceeds Cloudflare's 4 req/sec limit)
- Add gobreaker for circuit breaking (prevents cascading failures)
- Remove obsolete documentation (GATEWAY_API_MIGRATION_PLAN.md, DESIGN.md)

Source: https://developers.cloudflare.com/fundamentals/api/reference/limits/
Cloudflare limit: 1200 req/5min = 4 req/sec average
Our limit: 3 req/sec (safety buffer)"
```

**Estimated time**: 2-4 hours for Phase 0

---

## References

- [Cloudflare API Rate Limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)
- [gobreaker Documentation](https://github.com/sony/gobreaker)
- [Kubernetes Operator Best Practices](https://sdk.operatorframework.io/docs/best-practices/)
- [Gateway API Specification](https://gateway-api.sigs.k8s.io/)
