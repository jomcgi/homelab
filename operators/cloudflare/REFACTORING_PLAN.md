# Cloudflare Operator Refactoring Plan
## Option A: CloudflareTunnel CRD as Internal State Storage

**Status**: 🚧 Planning
**Priority**: High
**Estimated Effort**: 2-3 weeks

---

## Executive Summary

Refactor the Cloudflare operator to use `CloudflareTunnel` CRD as the **single source of truth** for tunnel state, with clear separation of concerns:

- **Gateway API (user-facing)**: Service annotations → HTTPRoute → Gateway
- **CloudflareTunnel CRD (internal)**: Cloudflare tunnel state management
- **Controllers**: Gateway creates CloudflareTunnel CRDs, CloudflareTunnel controller manages Cloudflare API

### Key Benefits

✅ **Single source of truth** - Tunnel state in protected CRD status (not annotations)
✅ **Separation of concerns** - Gateway logic separate from Cloudflare API logic
✅ **Automatic cleanup** - OwnerReferences ensure tunnels are deleted with Gateways
✅ **Better observability** - `kubectl get cloudflaretunnels` shows tunnel health
✅ **Reusable logic** - CloudflareTunnel controller can be used standalone
✅ **More resilient** - Protected status, proper reconciliation, retry logic

---

## Current Architecture (Problems)

```
Service (annotations)
    ↓
Service Controller
    ↓
Creates Gateway + HTTPRoute
    ↓
Gateway Controller → Cloudflare API (direct)
    ↓                   ↓
Stores tunnel ID    Creates tunnel
in annotations      (no K8s state!)
    ↓
HTTPRoute Controller → Cloudflare API (direct)
    ↓                   ↓
Stores DNS IDs      Creates DNS records
in annotations      (no K8s state!)
```

### Problems:
1. **Annotations are mutable** - Users can delete them, causing orphaned Cloudflare resources
2. **No K8s state tracking** - Tunnel exists in Cloudflare but not as a K8s resource
3. **Duplicate API logic** - Multiple controllers call Cloudflare API
4. **Race conditions** - Annotation updates can conflict
5. **Poor observability** - Can't `kubectl get` tunnel status
6. **Manual cleanup** - Finalizers must track Cloudflare resource IDs in annotations

---

## Target Architecture (Solution)

```
Service (annotations)
    ↓
Service Controller
    ↓
Creates Gateway + HTTPRoute
    ↓
Gateway Controller
    ↓
Creates CloudflareTunnel CRD (owned resource)
    ↓
CloudflareTunnel Controller (SINGLE Cloudflare API interface)
    ↓                           ↓
Updates CRD status          Cloudflare API
(tunnel ID, credentials,    (create/update/delete tunnel)
 connection status)
    ↑
    │ Watches status
    │
Gateway/HTTPRoute Controllers
    ↓
Update routes based on CloudflareTunnel status
```

### Benefits:
✅ **Protected state** - Status can't be modified by users
✅ **Single API interface** - Only CloudflareTunnel controller calls Cloudflare
✅ **Automatic cleanup** - K8s garbage collection via OwnerReferences
✅ **Observable** - `kubectl describe cloudflaretunnel` shows full state
✅ **Testable** - Mock CloudflareTunnel CRD instead of Cloudflare API
✅ **Resilient** - Proper retry logic, exponential backoff, circuit breaker

---

## Implementation Plan

### Phase 1: Foundation (Week 1)
**Goal**: Enhance CloudflareTunnel CRD and controller to be production-ready

#### 1.1 Update CloudflareTunnel CRD Status
**File**: `api/v1/cloudflaretunnel_types.go`

```go
// CloudflareTunnelStatus defines the observed state of CloudflareTunnel
type CloudflareTunnelStatus struct {
    // TunnelID is the Cloudflare tunnel ID
    // +optional
    TunnelID string `json:"tunnelID,omitempty"`

    // AccountID is the Cloudflare account ID
    // +optional
    AccountID string `json:"accountID,omitempty"`

    // SecretName is the name of the Secret containing tunnel credentials
    // +optional
    SecretName string `json:"secretName,omitempty"`

    // TunnelName is the name of the tunnel in Cloudflare
    // +optional
    TunnelName string `json:"tunnelName,omitempty"`

    // Connections tracks active tunnel connections
    // +optional
    Connections []TunnelConnection `json:"connections,omitempty"`

    // LastSyncTime is the last time the tunnel was synced with Cloudflare
    // +optional
    LastSyncTime *metav1.Time `json:"lastSyncTime,omitempty"`

    // Conditions represent the latest available observations of the tunnel's state
    // +optional
    // +patchMergeKey=type
    // +patchStrategy=merge
    Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`

    // ObservedGeneration reflects the generation of the most recently observed spec
    // +optional
    ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}

// TunnelConnection represents an active tunnel connection
type TunnelConnection struct {
    // ID is the connection ID
    ID string `json:"id"`

    // ColoName is the Cloudflare colo name (e.g., "SFO")
    // +optional
    ColoName string `json:"coloName,omitempty"`

    // IsConnected indicates if the connection is active
    IsConnected bool `json:"isConnected"`

    // ConnectedAt is when the connection was established
    // +optional
    ConnectedAt *metav1.Time `json:"connectedAt,omitempty"`
}
```

**Status Conditions**:
- `Ready` - Tunnel is created and ready to serve traffic
- `TunnelProvisioned` - Tunnel exists in Cloudflare
- `SecretsReady` - Credentials are generated and stored in Secret
- `ConfigurationValid` - Tunnel configuration is valid
- `Degraded` - Tunnel exists but has issues (no connections, API errors)

#### 1.2 Enhance CloudflareTunnel Controller
**File**: `internal/controller/cloudflaretunnel_controller.go`

**Changes**:
1. **Single responsibility**: Manage Cloudflare tunnel lifecycle only
2. **Robust error handling**: Circuit breaker, exponential backoff, rate limiting
3. **Status updates**: Keep CRD status in sync with Cloudflare state
4. **Secret management**: Generate and store tunnel credentials securely
5. **Observability**: Add metrics, tracing, structured logging

**Key reconciliation logic**:
```go
func (r *CloudflareTunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    // 1. Fetch CloudflareTunnel CRD
    // 2. Handle deletion (finalizer cleanup)
    // 3. Ensure tunnel exists in Cloudflare (create if missing)
    // 4. Generate credentials (if not exist)
    // 5. Store credentials in Secret
    // 6. Update tunnel configuration (if spec changed)
    // 7. Sync connection status
    // 8. Update CRD status
    // 9. Requeue periodically for status sync
}
```

#### 1.3 Fix Rate Limiting and Add Circuit Breaker
**File**: `internal/cloudflare/client.go`

```go
// Update rate limiter
limiter := rate.NewLimiter(rate.Limit(3), 10) // 3 req/sec, burst 10

// Add circuit breaker
type CircuitBreaker struct {
    mu            sync.RWMutex
    state         CircuitState
    failures      int
    lastFailTime  time.Time
    openUntil     time.Time

    // Config
    maxFailures   int           // Open after 5 failures
    timeout       time.Duration // Half-open after 30s
    resetAfter    time.Duration // Close after 60s success
}

// Wrap all Cloudflare API calls with circuit breaker
func (c *TunnelClient) CreateTunnel(ctx context.Context, ...) error {
    return c.circuitBreaker.Execute(func() error {
        return c.api.CreateTunnel(ctx, ...)
    })
}
```

#### 1.4 Add Custom Metrics
**File**: `internal/controller/cloudflaretunnel_controller.go`

```go
var (
    tunnelReconcileLatency = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "cloudflare_tunnel_reconcile_duration_seconds",
            Help: "Time taken to reconcile CloudflareTunnel",
        },
        []string{"namespace", "name", "result"},
    )

    cloudflareAPICallDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "cloudflare_api_call_duration_seconds",
            Help: "Cloudflare API call duration",
        },
        []string{"operation", "status"},
    )

    tunnelConnectionGauge = prometheus.NewGaugeVec(
        prometheus.GaugeOpts{
            Name: "cloudflare_tunnel_connections",
            Help: "Number of active tunnel connections",
        },
        []string{"namespace", "name", "tunnel_id"},
    )
)
```

---

### Phase 2: Gateway Controller Refactor (Week 2)
**Goal**: Gateway controller creates CloudflareTunnel CRDs instead of calling Cloudflare API directly

#### 2.1 Update Gateway Controller
**File**: `internal/controller/gateway_controller.go`

**Before** (current):
```go
// Direct Cloudflare API call
cfTunnel, err := cfClient.CreateTunnel(ctx, accountID, tunnelName, secret)

// Store in annotations (bad!)
gateway.Annotations[GatewayAnnotationTunnelID] = cfTunnel.ID
```

**After** (refactored):
```go
// Create CloudflareTunnel CRD (owned resource)
tunnelCRD := &tunnelsv1.CloudflareTunnel{
    ObjectMeta: metav1.ObjectMeta{
        Name:      fmt.Sprintf("%s-tunnel", gateway.Name),
        Namespace: gateway.Namespace,
        OwnerReferences: []metav1.OwnerReference{
            *metav1.NewControllerRef(gateway, gatewayv1.SchemeGroupVersion.WithKind("Gateway")),
        },
    },
    Spec: tunnelsv1.CloudflareTunnelSpec{
        AccountID:   accountID,
        Name:        tunnelName,
        // Configuration populated by HTTPRoute controller
    },
}

if err := r.Create(ctx, tunnelCRD); err != nil {
    if !errors.IsAlreadyExists(err) {
        return ctrl.Result{}, err
    }
    // Tunnel CRD already exists, fetch it
    if err := r.Get(ctx, client.ObjectKeyFromObject(tunnelCRD), tunnelCRD); err != nil {
        return ctrl.Result{}, err
    }
}

// Wait for CloudflareTunnel to be ready
if !meta.IsStatusConditionTrue(tunnelCRD.Status.Conditions, "Ready") {
    // Requeue until tunnel is ready
    return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
}

// Update Gateway status with tunnel address
gateway.Status.Addresses = []gatewayv1.GatewayStatusAddress{
    {
        Type:  ptr.To(gatewayv1.HostnameAddressType),
        Value: fmt.Sprintf("%s.cfargotunnel.com", tunnelCRD.Status.TunnelID),
    },
}
```

#### 2.2 Split Gateway Controller
**Goal**: Reduce complexity by splitting into focused components

**New structure**:
```
internal/controller/
├── gateway_controller.go          # Main reconciliation logic (15KB target)
├── gateway_tunnel_manager.go      # CloudflareTunnel CRD management
├── gateway_deployment_manager.go  # Cloudflared Deployment/HPA/PDB
└── gateway_secret_manager.go      # Secret lifecycle
```

**Benefits**:
- Each file has single responsibility
- Easier to test independently
- Clearer code organization
- Reduced cognitive load

#### 2.3 Add Watch for CloudflareTunnel Status
**File**: `internal/controller/gateway_controller.go`

```go
func (r *GatewayReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&gatewayv1.Gateway{}).
        Owns(&appsv1.Deployment{}).        // Cloudflared deployment
        Owns(&corev1.Secret{}).            // Tunnel secret
        Owns(&tunnelsv1.CloudflareTunnel{}). // ⭐ NEW: Watch owned tunnels
        Complete(r)
}
```

**Reconciliation trigger**:
- Gateway changes → Reconcile Gateway
- CloudflareTunnel status changes → Reconcile owning Gateway
- Ensures Gateway status stays in sync with tunnel state

---

### Phase 3: HTTPRoute Controller Updates (Week 2)
**Goal**: HTTPRoute controller updates CloudflareTunnel configuration instead of calling Cloudflare API

#### 3.1 Update HTTPRoute Controller
**File**: `internal/controller/httproute_controller.go`

**Before** (current):
```go
// Direct DNS API call
record, err := cfClient.CreateDNSRecord(ctx, zoneID, hostname, tunnelID)

// Store in annotations (bad!)
route.Annotations[fmt.Sprintf("dns-record-id.%s", hostname)] = record.ID
```

**After** (refactored):
```go
// Find owning Gateway
gateway := &gatewayv1.Gateway{}
if err := r.Get(ctx, gatewayRef, gateway); err != nil {
    return ctrl.Result{}, err
}

// Find CloudflareTunnel CRD owned by Gateway
tunnelCRD := &tunnelsv1.CloudflareTunnel{}
tunnelName := fmt.Sprintf("%s-tunnel", gateway.Name)
if err := r.Get(ctx, client.ObjectKey{Name: tunnelName, Namespace: gateway.Namespace}, tunnelCRD); err != nil {
    return ctrl.Result{}, err
}

// Wait for tunnel to be ready
if !meta.IsStatusConditionTrue(tunnelCRD.Status.Conditions, "Ready") {
    return ctrl.Result{RequeueAfter: 10 * time.Second}, nil
}

// Update CloudflareTunnel spec with ingress rules
tunnelCRD.Spec.Ingress = buildIngressRules(route)

if err := r.Update(ctx, tunnelCRD); err != nil {
    return ctrl.Result{}, err
}

// CloudflareTunnel controller will:
// 1. Update tunnel configuration in Cloudflare
// 2. Create/update DNS records
// 3. Update status with DNS record IDs
```

#### 3.2 CloudflareTunnel Controller DNS Management
**File**: `internal/controller/cloudflaretunnel_controller.go`

**New responsibilities**:
1. **Parse ingress rules** from CloudflareTunnel spec
2. **Create DNS records** for each hostname
3. **Update tunnel configuration** in Cloudflare
4. **Store DNS record IDs** in status
5. **Handle DNS conflicts** (duplicate hostnames)

```go
// In reconciliation logic
func (r *CloudflareTunnelReconciler) syncDNSRecords(ctx context.Context, tunnel *tunnelsv1.CloudflareTunnel) error {
    // Extract hostnames from ingress rules
    hostnames := extractHostnames(tunnel.Spec.Ingress)

    // Create/update DNS records for each hostname
    for _, hostname := range hostnames {
        record, err := r.ensureDNSRecord(ctx, tunnel, hostname)
        if err != nil {
            return err
        }

        // Store record ID in status
        tunnel.Status.DNSRecords = append(tunnel.Status.DNSRecords, DNSRecord{
            Hostname: hostname,
            RecordID: record.ID,
            ZoneID:   record.ZoneID,
        })
    }

    return nil
}
```

---

### Phase 4: Testing & Observability (Week 3)
**Goal**: Ensure reliability with comprehensive testing and observability

#### 4.1 Integration Tests
**File**: `internal/controller/cloudflaretunnel_controller_test.go`

```go
// Test tunnel creation with retry
func TestCloudfllareTunnel_CreateWithRetry(t *testing.T) {
    // Mock Cloudflare API with transient failures
    // Verify exponential backoff
    // Verify eventual success
}

// Test tunnel deletion with cleanup
func TestCloudfllareTunnel_DeleteWithFinalizer(t *testing.T) {
    // Create tunnel
    // Delete CloudflareTunnel CRD
    // Verify Cloudflare tunnel is deleted
    // Verify Secret is deleted
    // Verify finalizer is removed
}

// Test status sync
func TestCloudfllareTunnel_StatusSync(t *testing.T) {
    // Create tunnel
    // Verify status reflects Cloudflare state
    // Simulate connection changes
    // Verify status updates
}
```

**New test files needed**:
- `internal/controller/gateway_controller_test.go` (currently missing!)
- `internal/controller/httproute_controller_test.go` (currently missing!)
- `internal/controller/service_controller_test.go` (currently missing!)

#### 4.2 End-to-End Tests
**File**: `test/e2e/full_flow_test.go` (new)

```go
// Test complete user journey
func TestE2E_ServiceAnnotationToLiveTunnel(t *testing.T) {
    // 1. Create Service with cloudflare.io annotations
    // 2. Verify HTTPRoute is created
    // 3. Verify Gateway is created
    // 4. Verify CloudflareTunnel CRD is created
    // 5. Verify Cloudflare tunnel exists (via API)
    // 6. Verify DNS records exist
    // 7. Verify tunnel configuration is correct
    // 8. Send HTTP request through tunnel
    // 9. Verify request reaches Service

    // Cleanup:
    // 10. Delete Service
    // 11. Verify all resources are cleaned up
    // 12. Verify Cloudflare tunnel is deleted
}
```

#### 4.3 Enable Metrics by Default
**File**: `helm/cloudflare-operator/values.yaml`

```yaml
# Change from:
metrics:
  bindAddress: "0"  # Disabled

# To:
metrics:
  bindAddress: ":8443"
  enabled: true
  service:
    type: ClusterIP
    port: 8443
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/port: "8443"
```

**File**: `cmd/main.go`

```go
// Change default
flag.StringVar(&metricsAddr, "metrics-bind-address", ":8443", "...")
```

#### 4.4 Enable Leader Election
**File**: `helm/cloudflare-operator/values.yaml`

```yaml
controllerManager:
  replicas: 2  # High availability
  leaderElection:
    enabled: true
    leaseDuration: 15s
    renewDeadline: 10s
    retryPeriod: 2s
```

**File**: `cmd/main.go`

```go
// Change default
flag.BoolVar(&enableLeaderElection, "leader-elect", true, "...")
```

---

### Phase 5: Admission Webhooks (Week 3)
**Goal**: Validate CRDs before creation to prevent invalid state

#### 5.1 Add Validating Webhook for CloudflareTunnel
**File**: `api/v1/cloudflaretunnel_webhook.go` (new)

```go
// ValidateCreate validates the CloudflareTunnel on creation
func (r *CloudflareTunnel) ValidateCreate() (admission.Warnings, error) {
    var allErrs field.ErrorList

    // Validate name or metadata.name is set
    if r.Spec.Name == "" && r.ObjectMeta.Name == "" {
        allErrs = append(allErrs, field.Required(
            field.NewPath("spec", "name"),
            "tunnel name or metadata.name must be set",
        ))
    }

    // Validate AccountID
    if r.Spec.AccountID == "" {
        allErrs = append(allErrs, field.Required(
            field.NewPath("spec", "accountID"),
            "accountID is required",
        ))
    }

    // Validate ingress rules
    if err := r.validateIngressRules(); err != nil {
        allErrs = append(allErrs, err...)
    }

    if len(allErrs) == 0 {
        return nil, nil
    }

    return nil, apierrors.NewInvalid(
        schema.GroupKind{Group: GroupVersion.Group, Kind: "CloudflareTunnel"},
        r.Name,
        allErrs,
    )
}

// ValidateUpdate validates the CloudflareTunnel on update
func (r *CloudflareTunnel) ValidateUpdate(old runtime.Object) (admission.Warnings, error) {
    oldTunnel := old.(*CloudflareTunnel)

    var allErrs field.ErrorList

    // Immutable fields
    if r.Spec.AccountID != oldTunnel.Spec.AccountID {
        allErrs = append(allErrs, field.Forbidden(
            field.NewPath("spec", "accountID"),
            "accountID is immutable",
        ))
    }

    if len(allErrs) == 0 {
        return nil, nil
    }

    return nil, apierrors.NewInvalid(
        schema.GroupKind{Group: GroupVersion.Group, Kind: "CloudflareTunnel"},
        r.Name,
        allErrs,
    )
}

func (r *CloudflareTunnel) validateIngressRules() field.ErrorList {
    var allErrs field.ErrorList

    for i, rule := range r.Spec.Ingress {
        // Validate hostname format
        if rule.Hostname != "" {
            if !isValidHostname(rule.Hostname) {
                allErrs = append(allErrs, field.Invalid(
                    field.NewPath("spec", "ingress").Index(i).Child("hostname"),
                    rule.Hostname,
                    "must be a valid hostname",
                ))
            }
        }

        // Validate service URL
        if rule.Service == "" {
            allErrs = append(allErrs, field.Required(
                field.NewPath("spec", "ingress").Index(i).Child("service"),
                "service is required",
            ))
        }
    }

    return allErrs
}
```

#### 5.2 Register Webhooks
**File**: `cmd/main.go`

```go
if os.Getenv("ENABLE_WEBHOOKS") != "false" {
    if err = (&tunnelsv1.CloudflareTunnel{}).SetupWebhookWithManager(mgr); err != nil {
        setupLog.Error(err, "unable to create webhook", "webhook", "CloudflareTunnel")
        os.Exit(1)
    }
}
```

**File**: `config/webhook/manifests.yaml`

```yaml
# Webhook configuration for CloudflareTunnel
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: cloudflare-operator-validating-webhook
webhooks:
- name: validate-cloudflaretunnel.tunnels.cloudflare.io
  clientConfig:
    service:
      name: cloudflare-operator-webhook-service
      namespace: cloudflare-system
      path: /validate-tunnels-cloudflare-io-v1-cloudflaretunnel
  rules:
  - apiGroups: ["tunnels.cloudflare.io"]
    apiVersions: ["v1"]
    operations: ["CREATE", "UPDATE"]
    resources: ["cloudflaretunnels"]
```

---

## Migration Strategy

### For Existing Deployments

#### Step 1: Deploy New Operator Version (Backward Compatible)
- New operator supports **both** old and new patterns
- Gateway controller checks for existing annotations before creating CloudflareTunnel CRD
- If annotations exist → continue using old pattern (no disruption)
- If no annotations → use new pattern

```go
// Gateway controller reconciliation
func (r *GatewayReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    gateway := &gatewayv1.Gateway{}
    if err := r.Get(ctx, req.NamespacedName, gateway); err != nil {
        return ctrl.Result{}, err
    }

    // Check if gateway already has tunnel ID in annotations (old pattern)
    if tunnelID := gateway.Annotations[GatewayAnnotationTunnelID]; tunnelID != "" {
        // Use old pattern - don't create CloudflareTunnel CRD yet
        return r.reconcileOldPattern(ctx, gateway)
    }

    // Use new pattern - create/manage CloudflareTunnel CRD
    return r.reconcileNewPattern(ctx, gateway)
}
```

#### Step 2: Migration Tool (Optional)
Create a migration tool to convert existing Gateways:

```bash
# Migrate all gateways in namespace
kubectl cloudflare-migrate gateways --namespace prod

# Or manually for each gateway
kubectl cloudflare-migrate gateway my-gateway --namespace prod
```

**What it does**:
1. Reads tunnel ID from Gateway annotations
2. Creates CloudflareTunnel CRD with existing tunnel ID (adopt pattern)
3. Sets OwnerReference to Gateway
4. Waits for CloudflareTunnel to sync status
5. Removes annotations from Gateway
6. Gateway controller will now use new pattern

#### Step 3: Remove Old Pattern (Next Major Version)
After migration period (e.g., 6 months):
1. Remove backward compatibility code
2. Operator only supports CloudflareTunnel CRD pattern
3. Fail if Gateway has annotation but no CloudflareTunnel CRD

---

## Testing Strategy

### Unit Tests
- **CloudflareTunnel controller**: Create, update, delete, adoption, errors
- **Gateway controller**: CRD creation, ownership, status updates
- **HTTPRoute controller**: Ingress rule generation, DNS logic
- **Cloudflare client**: Rate limiting, circuit breaker, retries

### Integration Tests
- **Full reconciliation loops** with envtest
- **Multi-controller coordination** (Service → Gateway → CloudflareTunnel)
- **Error scenarios**: API failures, rate limits, conflicts
- **Finalizer cleanup**: Ensure resources are deleted properly

### End-to-End Tests
- **Real Cloudflare API** (staging environment)
- **Complete user journey**: Service annotation → live tunnel
- **DNS propagation**: Verify DNS records are created and resolvable
- **HTTP traffic**: Send requests through tunnel, verify routing

### Load Tests
- **High churn**: Create/delete 100 tunnels rapidly
- **Rate limiting**: Verify circuit breaker activates under load
- **Leader election**: Kill leader pod, verify failover

---

## Rollback Plan

### If Issues Are Found

#### Option 1: Feature Flag Rollback
Add feature flag to disable new pattern:

```yaml
# helm values
controllerManager:
  featureGates:
    UseCloudflareTunnelCRD: false  # Revert to old pattern
```

#### Option 2: Helm Rollback
```bash
# Rollback to previous operator version
helm rollback cloudflare-operator -n cloudflare-system

# Verify old version is running
kubectl get pods -n cloudflare-system
```

#### Option 3: Manual Cleanup
If CloudflareTunnel CRDs cause issues:
```bash
# Delete all CloudflareTunnel CRDs (keeps Cloudflare tunnels via finalizer skip)
kubectl delete cloudflaretunnels --all -A --wait=false

# Patch to remove finalizers
kubectl patch cloudflaretunnels <name> -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Critical**: Existing Cloudflare tunnels will NOT be deleted (they were created before refactor). Only new tunnels created by CRDs will be affected.

---

## Success Criteria

### Functional
- ✅ All existing tunnels continue working without disruption
- ✅ New tunnels are created via CloudflareTunnel CRD
- ✅ Gateway status reflects tunnel state accurately
- ✅ Tunnel deletion cleans up Cloudflare resources
- ✅ DNS records are created and updated correctly
- ✅ HTTPRoute changes update tunnel configuration

### Reliability
- ✅ Circuit breaker activates during Cloudflare API outages
- ✅ Rate limiting prevents 429 errors
- ✅ Leader election enables HA (2 replicas)
- ✅ Admission webhooks reject invalid CRDs
- ✅ Finalizers ensure no orphaned Cloudflare resources

### Observability
- ✅ Metrics exported on :8443/metrics
- ✅ `kubectl get cloudflaretunnels` shows tunnel health
- ✅ `kubectl describe cloudflaretunnel` shows detailed status
- ✅ Status conditions reflect tunnel state
- ✅ OpenTelemetry traces show reconciliation flow

### Testing
- ✅ Unit tests for all controllers (>80% coverage)
- ✅ Integration tests for reconciliation loops
- ✅ E2E test for full user journey
- ✅ Load test passes (100 tunnels, <30s reconciliation)

---

## Timeline

| Week | Phase | Deliverables |
|------|-------|-------------|
| **1** | Foundation | Enhanced CloudflareTunnel CRD, controller improvements, rate limiting, circuit breaker, metrics |
| **2** | Refactor | Gateway controller refactor, HTTPRoute controller updates, split large controllers |
| **3** | Polish | Tests (unit, integration, e2e), webhooks, leader election, documentation |
| **4** | Review | Code review, testing in staging, migration planning |
| **5** | Deploy | Gradual rollout to production, monitoring, iteration |

---

## Open Questions

1. **Migration timeline**: How long should we support backward compatibility?
   - **Recommendation**: 2 releases (6 months) before deprecation

2. **Cloudflare API credentials**: Should we use a shared client or per-namespace secrets?
   - **Current**: Single API token (limited to account)
   - **Future**: Per-namespace tokens for multi-tenancy?

3. **DNS zone management**: Should CloudflareTunnel controller auto-detect zones?
   - **Current**: Requires zone ID annotation
   - **Future**: Lookup zone by hostname?

4. **Tunnel naming**: Should we allow custom tunnel names or always use `<gateway-name>-tunnel`?
   - **Current**: Uses Gateway name
   - **Future**: Allow override via annotation?

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Get approval** for breaking changes (if any)
3. **Create feature branch**: `feature/cloudflaretunnel-crd-refactor`
4. **Start Phase 1**: Update CloudflareTunnel CRD and controller
5. **Track progress**: Update this document with completion status

---

**Questions or concerns?** Please raise them before starting implementation!
