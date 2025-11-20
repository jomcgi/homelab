# Cloudflare Operator Refactoring Plan

## Option A: CloudflareTunnel CRD as Internal State Storage

**Status**: 🚧 Planning
**Priority**: High
**Estimated Effort**: 5 weeks

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

    // DNSRecords tracks DNS records created for this tunnel
    // +optional
    DNSRecords []DNSRecord `json:"dnsRecords,omitempty"`

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

// DNSRecord represents a DNS record created for the tunnel
type DNSRecord struct {
    // Hostname is the DNS hostname
    Hostname string `json:"hostname"`

    // RecordID is the Cloudflare DNS record ID
    RecordID string `json:"recordID"`

    // ZoneID is the Cloudflare zone ID
    ZoneID string `json:"zoneID"`
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

#### 1.3 Fix Rate Limiting and Add Circuit Breaker (gobreaker)

**See Phase 0 above** - This is a critical stability fix that should be implemented FIRST.

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
import (
    apierrors "k8s.io/apimachinery/pkg/api/errors"
)

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
    // Use apierrors (not standard errors package)
    if !apierrors.IsAlreadyExists(err) {
        return ctrl.Result{}, err
    }
    // Tunnel CRD already exists, fetch it
    if err := r.Get(ctx, client.ObjectKeyFromObject(tunnelCRD), tunnelCRD); err != nil {
        return ctrl.Result{}, err
    }
}

// Wait for CloudflareTunnel to be ready
if !meta.IsStatusConditionTrue(tunnelCRD.Status.Conditions, "Ready") {
	// Requeue with fixed backoff - controller-runtime handles smart requeuing
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

// Helper: Build ingress rules from HTTPRoute
func buildIngressRules(route *gatewayv1.HTTPRoute) []tunnelsv1.IngressRule {
    var rules []tunnelsv1.IngressRule

    for _, hostname := range route.Spec.Hostnames {
        for _, rule := range route.Spec.Rules {
            for _, backendRef := range rule.BackendRefs {
                rules = append(rules, tunnelsv1.IngressRule{
                    Hostname: string(hostname),
                    Service:  fmt.Sprintf("http://%s.%s.svc.cluster.local:%d",
                        backendRef.Name, route.Namespace, *backendRef.Port),
                })
            }
        }
    }

    return rules
}
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

    // Clear existing DNS records to prevent duplicates on re-reconciliation
    newDNSRecords := []tunnelsv1.DNSRecord{}

    // Create/update DNS records for each hostname
    for _, hostname := range hostnames {
        record, err := r.ensureDNSRecord(ctx, tunnel, hostname)
        if err != nil {
            return err
        }

        // Add to new records list
        newDNSRecords = append(newDNSRecords, tunnelsv1.DNSRecord{
            Hostname: hostname,
            RecordID: record.ID,
            ZoneID:   record.ZoneID,
        })
    }

    // Replace status with new records (prevents duplicates)
    tunnel.Status.DNSRecords = newDNSRecords

    return nil
}

// Helper: Extract unique hostnames from ingress rules
func extractHostnames(ingress []tunnelsv1.IngressRule) []string {
    hostnameMap := make(map[string]struct{})
    var hostnames []string

    for _, rule := range ingress {
        if rule.Hostname != "" {
            if _, exists := hostnameMap[rule.Hostname]; !exists {
                hostnameMap[rule.Hostname] = struct{}{}
                hostnames = append(hostnames, rule.Hostname)
            }
        }
    }

    return hostnames
}

// Helper: Ensure DNS record exists (create or update)
func (r *CloudflareTunnelReconciler) ensureDNSRecord(
	ctx context.Context,
	tunnel *tunnelsv1.CloudflareTunnel,
	hostname string,
) (*cloudflare.DNSRecord, error) {
	// Determine zone ID from hostname
	zoneID, err := r.getZoneIDForHostname(ctx, hostname)
	if err != nil {
		return nil, fmt.Errorf("failed to get zone ID for %s: %w", hostname, err)
	}

	// Check if DNS record already exists
	existingRecord, err := r.findDNSRecord(ctx, zoneID, hostname)
	if err != nil && !cfclient.IsNotFoundError(err) {
		return nil, fmt.Errorf("failed to find DNS record: %w", err)
	}

	tunnelDNS := fmt.Sprintf("%s.cfargotunnel.com", tunnel.Status.TunnelID)

	if existingRecord != nil {
		// Update existing record if content changed
		if existingRecord.Content == tunnelDNS {
			return existingRecord, nil // No update needed
		}
		existingRecord.Content = tunnelDNS
		return r.CFClient.UpdateDNSRecord(ctx, zoneID, existingRecord.ID, existingRecord)
	}

	// Create new record
	return r.CFClient.CreateDNSRecord(ctx, zoneID, &cloudflare.DNSRecord{
		Type:    "CNAME",
		Name:    hostname,
		Content: tunnelDNS,
		TTL:     1, // Auto TTL
		Proxied: ptr.To(true),
	})
}

// Helper: Get zone ID from hostname (extracts root domain)
func (r *CloudflareTunnelReconciler) getZoneIDForHostname(ctx context.Context, hostname string) (string, error) {
	// Extract root domain from hostname
	// e.g., "app.jomcgi.dev" -> "jomcgi.dev"
	parts := strings.Split(hostname, ".")
	if len(parts) < 2 {
		return "", fmt.Errorf("invalid hostname: %s", hostname)
	}

	// Get last two parts as zone name
	zoneName := strings.Join(parts[len(parts)-2:], ".")

	// List zones and find matching zone
	zones, err := r.CFClient.ListZones(ctx, zoneName)
	if err != nil {
		return "", fmt.Errorf("failed to list zones: %w", err)
	}

	for _, zone := range zones {
		if zone.Name == zoneName {
			return zone.ID, nil
		}
	}

	return "", fmt.Errorf("zone not found for hostname %s (zone: %s)", hostname, zoneName)
}

// Helper: Find DNS record by hostname
func (r *CloudflareTunnelReconciler) findDNSRecord(ctx context.Context, zoneID, hostname string) (*cloudflare.DNSRecord, error) {
	// List DNS records for this zone with name filter
	records, err := r.CFClient.ListDNSRecords(ctx, zoneID, hostname)
	if err != nil {
		return nil, err
	}

	for _, record := range records {
		if record.Name == hostname || record.Name == hostname+"." {
			return &record, nil
		}
	}

	return nil, cfclient.NotFoundError("DNS record not found")
}
```

---

### Phase 4: Testing & Observability (Week 3)

**Goal**: Ensure reliability with comprehensive testing and observability

#### 4.1 Integration Tests

**File**: `internal/controller/cloudflaretunnel_controller_test.go`

```go
// Test tunnel creation with retry
func TestCloudflareTunnel_CreateWithRetry(t *testing.T) {
    // Mock Cloudflare API with transient failures
    // Verify exponential backoff
    // Verify eventual success
}

// Test tunnel deletion with cleanup
func TestCloudflareTunnel_DeleteWithFinalizer(t *testing.T) {
    // Create tunnel
    // Delete CloudflareTunnel CRD
    // Verify Cloudflare tunnel is deleted
    // Verify Secret is deleted
    // Verify finalizer is removed
}

// Test status sync
func TestCloudflareTunnel_StatusSync(t *testing.T) {
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
  replicas: 2 # High availability
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

// Helper: Validate hostname format (RFC 1123)
func isValidHostname(hostname string) bool {
    // Check length (max 253 characters)
    if len(hostname) > 253 {
        return false
    }

    // Check if empty
    if len(hostname) == 0 {
        return false
    }

    // Hostname regex: RFC 1123 compliant
    // - Labels separated by dots
    // - Each label: alphanumeric + hyphens (not at start/end)
    // - Max label length: 63 characters
    hostnameRegex := regexp.MustCompile(`^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$`)
    return hostnameRegex.MatchString(hostname)
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
    UseCloudflareTunnelCRD: false # Revert to old pattern
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

| Week  | Phase      | Deliverables                                                                                    |
| ----- | ---------- | ----------------------------------------------------------------------------------------------- |
| **1** | Foundation | Enhanced CloudflareTunnel CRD, controller improvements, rate limiting, circuit breaker, metrics |
| **2** | Refactor   | Gateway controller refactor, HTTPRoute controller updates, split large controllers              |
| **3** | Polish     | Tests (unit, integration, e2e), webhooks, leader election, documentation                        |
| **4** | Review     | Code review, testing in staging, migration planning                                             |
| **5** | Deploy     | Gradual rollout to production, monitoring, iteration                                            |

---

## Critical Decisions (Made)

### 1. Rate Limiting: Keep 3 req/sec (CORRECT)

**Source**: [Cloudflare API Rate Limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)

- Cloudflare limit: 1200 req/5min = **4 req/sec average**
- Current code (10 req/sec) **EXCEEDS** limit and will trigger 5-minute bans
- **Decision**: Use 3 req/sec with burst 10 (safe buffer under 4 req/sec)

### 2. Circuit Breaker: Use gobreaker library

- Custom implementation has bugs (no failure reset in closed state)
- **Decision**: Use `github.com/sony/gobreaker` (production-tested)

### 3. CloudflareTunnel CRD: Internal Implementation Detail

- Users interact with Gateway API only (Gateway + HTTPRoute)
- CloudflareTunnel CRD is operator state management (not user-facing)
- **Decision**: Document as internal, don't expose in examples

### 4. CRD Migration: Breaking Changes OK

- Not GA, can drop/recreate CRDs
- **Decision**: No backward compatibility, clean slate approach

### 5. Architecture: Gateway API → CloudflareTunnel CRD → Cloudflare API

```
User Layer:     Gateway API (Gateway + HTTPRoute)
                     ↓
Internal Layer: CloudflareTunnel CRD (operator state)
                     ↓
External API:   Cloudflare API (tunnels, DNS, routes)
```

---

## Deprecated / Removed

The following will be **deleted** in this refactoring:

1. **GATEWAY_API_MIGRATION_PLAN.md** - Already using Gateway API, plan is obsolete
2. **DESIGN.md** - Describes old Published Routes architecture, not implemented
3. **Annotation-based state storage** - Replace with CRD status fields
4. **Direct Cloudflare API calls from Gateway/HTTPRoute controllers** - Use CloudflareTunnel controller only
5. **Custom circuit breaker** - Replace with gobreaker
6. **UpdateTunnelConfiguration API** - Not used in current implementation

---

## Open Questions (RESOLVED)

1. ~~**Migration timeline**~~ → **Breaking changes OK, no backward compatibility**
2. ~~**Cloudflare API credentials**~~ → **Keep single token (works for homelab)**
3. ~~**DNS zone management**~~ → **Auto-detect from hostname (implement in Phase 2)**
4. ~~**Tunnel naming**~~ → **Use `<gateway-namespace>-tunnel` (already implemented)**

---

## Next Steps

1. ✅ **Review plan** - APPROVED for stability focus
2. ✅ **Breaking changes** - APPROVED (not GA)
3. 🚧 **Implementation** - Start with critical fixes:
   - Phase 0: Fix rate limiting + add gobreaker (immediate stability)
   - Phase 1: Enhanced CloudflareTunnel CRD
   - Phase 2: Refactor controllers to use CRD
   - Phase 3: Testing + observability
4. 📝 **Track progress** - Update status in this document

---

## Phase 0: Immediate Stability Fixes (Week 0 - PRIORITY)

**Goal**: Fix critical bugs that cause production instability NOW

### 0.1 Fix Rate Limiting (CRITICAL)

**File**: `internal/cloudflare/client.go`

```go
// BEFORE (WRONG - exceeds Cloudflare limit!)
limiter := rate.NewLimiter(rate.Limit(10), 20)

// AFTER (CORRECT - stays under 4 req/sec global limit)
// Source: https://developers.cloudflare.com/fundamentals/api/reference/limits/
// Cloudflare: 1200 req/5min = 4 req/sec average
// We use 3 req/sec to provide safety buffer
limiter := rate.NewLimiter(rate.Limit(3), 10)
```

### 0.2 Add Circuit Breaker (gobreaker)

**File**: `internal/cloudflare/client.go`

Add dependency:

```bash
cd operators/cloudflare
go get github.com/sony/gobreaker@latest
```

Update client:

```go
import "github.com/sony/gobreaker"

type TunnelClient struct {
    api            *cloudflare.API
    limiter        *rate.Limiter
    circuitBreaker *gobreaker.CircuitBreaker
    tracer         trace.Tracer
}

func NewTunnelClient(apiToken string) (*TunnelClient, error) {
    api, err := cloudflare.NewWithAPIToken(apiToken)
    if err != nil {
        return nil, fmt.Errorf("failed to create cloudflare client: %w", err)
    }

    // Rate limiter: 3 req/sec, burst 10 (under Cloudflare's 4 req/sec limit)
    limiter := rate.NewLimiter(rate.Limit(3), 10)

    // Circuit breaker settings
    cbSettings := gobreaker.Settings{
        Name:        "cloudflare-api",
        MaxRequests: 3,              // Allow 3 requests in half-open state
        Interval:    60 * time.Second,  // Reset failure count after 60s
        Timeout:     30 * time.Second,  // Stay open for 30s before half-open
        ReadyToTrip: func(counts gobreaker.Counts) bool {
            // Open circuit after 5 consecutive failures
            return counts.ConsecutiveFailures >= 5
        },
        OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
            log.Printf("Circuit breaker %s: %s -> %s", name, from, to)
        },
    }

    return &TunnelClient{
        api:            api,
        limiter:        limiter,
        circuitBreaker: gobreaker.NewCircuitBreaker(cbSettings),
        tracer:         telemetry.GetTracer("cloudflare-api-client"),
    }, nil
}

// Wrap API calls with circuit breaker + rate limiter
func (c *TunnelClient) CreateTunnel(ctx context.Context, accountID, name string) (*cloudflare.Tunnel, string, error) {
    ctx, span := c.tracer.Start(ctx, "cloudflare.CreateTunnel",
        trace.WithAttributes(
            attribute.String("account.id", accountID),
            attribute.String("tunnel.name", name),
        ),
    )
    defer span.End()

    // Rate limiting
    if err := c.limiter.Wait(ctx); err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, "rate limiter wait failed")
        return nil, "", err
    }

    // Circuit breaker
    result, err := c.circuitBreaker.Execute(func() (interface{}, error) {
        return c.createTunnelInternal(ctx, accountID, name)
    })

    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, "cloudflare API call failed")
        return nil, "", err
    }

    tunnel := result.(*tunnelWithSecret)
    span.SetAttributes(attribute.String("tunnel.id", tunnel.Tunnel.ID))
    span.SetStatus(codes.Ok, "tunnel created")
    return tunnel.Tunnel, tunnel.Secret, nil
}

type tunnelWithSecret struct {
    Tunnel *cloudflare.Tunnel
    Secret string
}

func (c *TunnelClient) createTunnelInternal(ctx context.Context, accountID, name string) (*tunnelWithSecret, error) {
    // Generate tunnel secret
    secret := make([]byte, 32)
    if _, err := rand.Read(secret); err != nil {
        return nil, fmt.Errorf("failed to generate tunnel secret: %w", err)
    }
    tunnelSecret := base64.StdEncoding.EncodeToString(secret)

    tunnel, err := c.api.CreateTunnel(ctx, cloudflare.AccountIdentifier(accountID), cloudflare.TunnelCreateParams{
        Name:   name,
        Secret: tunnelSecret,
    })
    if err != nil {
        return nil, fmt.Errorf("failed to create tunnel %s: %w", name, err)
    }

    return &tunnelWithSecret{
        Tunnel: &tunnel,
        Secret: tunnelSecret,
    }, nil
}
```

### 0.3 Remove Obsolete Documentation

```bash
# Delete obsolete files
rm operators/cloudflare/GATEWAY_API_MIGRATION_PLAN.md
rm operators/cloudflare/DESIGN.md
```

**Estimated Time**: 2-4 hours
**Impact**: Immediate stability improvement, prevents rate limit bans

---

**Questions or concerns?** This is NOT GA, we can move fast and break things!
