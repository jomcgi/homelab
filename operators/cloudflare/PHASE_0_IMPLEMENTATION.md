# Phase 0: Immediate Stability Fixes - Implementation Guide

**Estimated time**: 2-4 hours  
**Priority**: 🔥 CRITICAL - Do this BEFORE any other refactoring  
**Risk**: LOW - Small, focused changes with immediate benefit

---

## Task 1: Fix Rate Limiting (15 minutes)

### Step 1.1: Update rate limiter

**File**: `operators/cloudflare/internal/cloudflare/client.go`

**Line 82-83**: Change from 10 req/sec to 3 req/sec

```diff
 func NewTunnelClient(apiToken string) (*TunnelClient, error) {
     api, err := cloudflare.NewWithAPIToken(apiToken)
     if err != nil {
         return nil, fmt.Errorf("failed to create cloudflare client: %w", err)
     }

-    // Rate limiter: 10 requests per second with burst of 20
-    limiter := rate.NewLimiter(rate.Limit(10), 20)
+    // Rate limiter: 3 requests per second with burst of 10
+    // Source: https://developers.cloudflare.com/fundamentals/api/reference/limits/
+    // Cloudflare limit: 1200 req/5min = 4 req/sec average
+    // We use 3 req/sec to provide safety buffer
+    limiter := rate.NewLimiter(rate.Limit(3), 10)

     return &TunnelClient{
```

### Step 1.2: Test the change

```bash
cd operators/cloudflare
go test ./internal/cloudflare/... -v
```

**Expected**: All tests pass (no behavioral change, just slower API calls)

---

## Task 2: Add Circuit Breaker (1-2 hours)

### Step 2.1: Add gobreaker dependency

```bash
cd operators/cloudflare
go get github.com/sony/gobreaker@latest
go mod tidy
```

### Step 2.2: Update TunnelClient struct

**File**: `operators/cloudflare/internal/cloudflare/client.go`

**Add import** (around line 18):

```go
import (
    // ... existing imports ...
    "github.com/sony/gobreaker"
)
```

**Update struct** (around line 68):

```diff
 type TunnelClient struct {
     api     *cloudflare.API
     limiter *rate.Limiter
+    circuitBreaker *gobreaker.CircuitBreaker
     tracer  trace.Tracer
 }
```

### Step 2.3: Initialize circuit breaker in NewTunnelClient

**File**: `operators/cloudflare/internal/cloudflare/client.go`  
**Function**: `NewTunnelClient` (around line 76)

```diff
 func NewTunnelClient(apiToken string) (*TunnelClient, error) {
     api, err := cloudflare.NewWithAPIToken(apiToken)
     if err != nil {
         return nil, fmt.Errorf("failed to create cloudflare client: %w", err)
     }

     // Rate limiter: 3 requests per second with burst of 10
     limiter := rate.NewLimiter(rate.Limit(3), 10)

+    // Circuit breaker settings
+    cbSettings := gobreaker.Settings{
+        Name:        "cloudflare-api",
+        MaxRequests: 3,                    // Allow 3 requests in half-open state
+        Interval:    60 * time.Second,     // Reset failure count after 60s
+        Timeout:     30 * time.Second,     // Stay open for 30s before half-open
+        ReadyToTrip: func(counts gobreaker.Counts) bool {
+            // Open circuit after 5 consecutive failures
+            return counts.ConsecutiveFailures >= 5
+        },
+        OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
+            // Log state changes for debugging
+            fmt.Printf("Circuit breaker %s: %s -> %s\n", name, from, to)
+        },
+    }
+
     return &TunnelClient{
         api:     api,
         limiter: limiter,
+        circuitBreaker: gobreaker.NewCircuitBreaker(cbSettings),
         tracer:  telemetry.GetTracer("cloudflare-api-client"),
     }, nil
 }
```

### Step 2.4: Wrap CreateTunnel with circuit breaker

**File**: `operators/cloudflare/internal/cloudflare/client.go`  
**Function**: `CreateTunnel` (around line 92)

**Add helper type** (after TunnelClient struct definition):

```go
// tunnelWithSecret is a helper type for circuit breaker return values
type tunnelWithSecret struct {
    Tunnel *cloudflare.Tunnel
    Secret string
}
```

**Refactor CreateTunnel**:

```diff
 func (c *TunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
     ctx, span := c.tracer.Start(ctx, "cloudflare.CreateTunnel",
         trace.WithAttributes(
             attribute.String("account.id", accountID),
             attribute.String("tunnel.name", name),
         ),
     )
     defer span.End()

     if err := c.limiter.Wait(ctx); err != nil {
         span.RecordError(err)
         span.SetStatus(codes.Error, "rate limiter wait failed")
         return nil, "", err
     }

-    // Generate a random tunnel secret (32 bytes, base64 encoded)
-    secret := make([]byte, 32)
-    if _, err := rand.Read(secret); err != nil {
-        span.RecordError(err)
-        span.SetStatus(codes.Error, "failed to generate secret")
-        return nil, "", fmt.Errorf("failed to generate tunnel secret: %w", err)
-    }
-    tunnelSecret := base64.StdEncoding.EncodeToString(secret)
-
-    tunnel, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelCreateParams{
-        Name:   name,
-        Secret: tunnelSecret,
-    })
+    // Circuit breaker wraps the actual API call
+    result, err := c.circuitBreaker.Execute(func() (interface{}, error) {
+        return c.createTunnelInternal(ctx, accountID, name)
+    })
+
     if err != nil {
         span.RecordError(err)
         span.SetStatus(codes.Error, "cloudflare API call failed")
-        return nil, "", fmt.Errorf("failed to create tunnel %s: %w", name, err)
+        return nil, "", err
     }

-    span.SetAttributes(attribute.String("tunnel.id", tunnel.ID))
+    tunnelResult := result.(*tunnelWithSecret)
+    span.SetAttributes(attribute.String("tunnel.id", tunnelResult.Tunnel.ID))
     span.SetStatus(codes.Ok, "tunnel created")
-    return &tunnel, tunnelSecret, nil
+    return tunnelResult.Tunnel, tunnelResult.Secret, nil
 }
+
+// createTunnelInternal performs the actual API call (wrapped by circuit breaker)
+func (c *TunnelClient) createTunnelInternal(ctx context.Context, accountID, name string) (*tunnelWithSecret, error) {
+    // Generate a random tunnel secret (32 bytes, base64 encoded)
+    secret := make([]byte, 32)
+    if _, err := rand.Read(secret); err != nil {
+        return nil, fmt.Errorf("failed to generate tunnel secret: %w", err)
+    }
+    tunnelSecret := base64.StdEncoding.EncodeToString(secret)
+
+    tunnel, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelCreateParams{
+        Name:   name,
+        Secret: tunnelSecret,
+    })
+    if err != nil {
+        return nil, fmt.Errorf("failed to create tunnel %s: %w", name, err)
+    }
+
+    return &tunnelWithSecret{
+        Tunnel: &tunnel,
+        Secret: tunnelSecret,
+    }, nil
+}
```

### Step 2.5: Optionally wrap other API calls

**You can also wrap**:

- `GetTunnel`
- `ListTunnels`
- `DeleteTunnel`
- `UpdateTunnelConfiguration`
- `GetTunnelToken`

**Pattern** (same for all):

```go
// Before
result, err := c.api.SomeMethod(ctx, ...)

// After
result, err := c.circuitBreaker.Execute(func() (interface{}, error) {
    return c.api.SomeMethod(ctx, ...)
})
```

**Recommendation**: Start with just `CreateTunnel`, then add others if needed.

### Step 2.6: Test circuit breaker

```bash
cd operators/cloudflare
go test ./internal/cloudflare/... -v
```

**Manual test** (optional):

1. Create a Gateway
2. Check logs for "Circuit breaker cloudflare-api: closed -> open" during failures
3. Verify circuit opens after 5 consecutive failures
4. Verify circuit half-opens after 30 seconds

---

## Task 3: Remove Stale Documentation (5 minutes)

### Step 3.1: Delete obsolete files

```bash
cd operators/cloudflare
rm GATEWAY_API_MIGRATION_PLAN.md  # Already using Gateway API
rm DESIGN.md                        # Describes unimplemented architecture
```

### Step 3.2: Update README (optional)

**File**: `operators/cloudflare/README.md`

Remove any references to:

- "Gateway API migration"
- "Published Routes API" (not implemented)
- Old CloudflareTunnel CRD design

Keep:

- Current Gateway API usage
- Service annotation examples
- Deployment instructions

---

## Task 4: Commit Changes

```bash
cd /Users/jomcgi/repos/homelab

# Check what changed
git status
git diff

# Stage changes
git add operators/cloudflare/internal/cloudflare/client.go
git add operators/cloudflare/go.mod
git add operators/cloudflare/go.sum
git add operators/cloudflare/GATEWAY_API_MIGRATION_PLAN.md  # Deletion
git add operators/cloudflare/DESIGN.md                       # Deletion

# Commit with descriptive message
git commit -m "fix(cloudflare): Fix rate limiting and add circuit breaker

Critical stability fixes for Cloudflare operator:

1. Reduce rate limit from 10 req/sec to 3 req/sec
   - Cloudflare limit: 1200 req/5min = 4 req/sec average
   - Previous limit (10 req/sec) exceeded Cloudflare's limit by 2.5x
   - Caused HTTP 429 errors and 5-minute bans on all API calls
   - Source: https://developers.cloudflare.com/fundamentals/api/reference/limits/

2. Add circuit breaker using gobreaker library
   - Prevents cascading failures during Cloudflare API degradation
   - Opens after 5 consecutive failures
   - Half-opens after 30 seconds to test recovery
   - Resets failure count after 60 seconds

3. Remove obsolete documentation
   - Delete GATEWAY_API_MIGRATION_PLAN.md (already using Gateway API)
   - Delete DESIGN.md (describes unimplemented architecture)

Breaking changes: None
Backward compatible: Yes (faster rate limit, same API interface)"
```

---

## Task 5: Deploy and Verify

### Step 5.1: Build and test locally

```bash
cd operators/cloudflare

# Run tests
go test ./... -v

# Build operator
go build -o bin/manager ./cmd/main.go
```

### Step 5.2: Deploy to cluster

```bash
cd /Users/jomcgi/repos/homelab

# Render manifests
format

# Check for changes
git diff overlays/dev/cloudflare-operator/manifests/all.yaml

# Commit rendered manifests
git add overlays/dev/cloudflare-operator/manifests/all.yaml
git commit -m "build: Update cloudflare-operator manifests with rate limiting fix"

# Push to trigger ArgoCD sync
git push origin claude/review-cloudflare-operator-01JtXUrtUZUx4NTqQz1ZcLpD
```

### Step 5.3: Monitor deployment

```bash
# Watch operator pod restart
kubectl get pods -n cloudflare-system -w

# Check logs for circuit breaker messages
kubectl logs -n cloudflare-system -l app.kubernetes.io/name=cloudflare-operator -f | grep -i "circuit"

# Verify rate limiting (should see slower API calls)
kubectl logs -n cloudflare-system -l app.kubernetes.io/name=cloudflare-operator -f | grep -i "cloudflare.CreateTunnel"
```

### Step 5.4: Verify functionality

```bash
# Create a test Gateway
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: test-gateway
  namespace: default
spec:
  gatewayClassName: cloudflare
  listeners:
  - name: https
    protocol: HTTPS
    port: 443
EOF

# Check Gateway status
kubectl describe gateway test-gateway

# Verify no HTTP 429 errors in logs
kubectl logs -n cloudflare-system -l app.kubernetes.io/name=cloudflare-operator | grep -i "429"
```

---

## Success Criteria

✅ **Rate limiting fixed**:

- No HTTP 429 errors in logs
- API calls happen at 3 req/sec max (verify in logs)

✅ **Circuit breaker working**:

- Circuit breaker logs appear during failures
- Circuit opens after 5 consecutive failures
- Circuit half-opens after 30 seconds

✅ **Stale docs removed**:

- `GATEWAY_API_MIGRATION_PLAN.md` deleted
- `DESIGN.md` deleted

✅ **Tests pass**:

- `go test ./... -v` passes
- No compilation errors

✅ **Deployment successful**:

- Operator pod restarts cleanly
- Existing Gateways continue working
- New Gateways create tunnels successfully

---

## Rollback Plan

If something goes wrong:

```bash
# Option 1: Revert git commit
git revert HEAD
git push origin claude/review-cloudflare-operator-01JtXUrtUZUx4NTqQz1ZcLpD

# Option 2: Helm rollback (if deployed via Helm)
helm rollback cloudflare-operator -n cloudflare-system

# Option 3: Manual revert in client.go
# Change rate.NewLimiter(rate.Limit(3), 10) back to (10, 20)
# Remove circuit breaker code
```

---

## Next Steps After Phase 0

Once Phase 0 is complete and stable:

1. **Update PR description** - Document the rate limiting fix
2. **Monitor for 24-48 hours** - Ensure no regressions
3. **Proceed to Phase 1** - Enhanced CloudflareTunnel CRD (if desired)

**Or stop here** - Phase 0 alone significantly improves stability. The rest of the refactoring can wait until you have more time or encounter specific issues.

---

## Questions?

If you encounter issues:

1. **Check logs**: `kubectl logs -n cloudflare-system -l app.kubernetes.io/name=cloudflare-operator`
2. **Check circuit breaker state**: Look for "Circuit breaker cloudflare-api: " messages
3. **Verify rate limiting**: API calls should be ~3 seconds apart in logs
4. **Test with simple Gateway**: Create minimal Gateway to isolate issues

**The code changes are small and focused - this should be straightforward!**
