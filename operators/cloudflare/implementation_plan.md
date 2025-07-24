# Cloudflare Tunnel Operator Implementation Plan

## Executive Summary

This plan outlines the development of a focused Cloudflare tunnel operator that creates and manages Cloudflare tunnels through Kubernetes CRDs. Unlike the comprehensive access policy operator described in the architecture guide, this implementation focuses on tunnel lifecycle management with proper cleanup and status reporting.

## Project Scope

**Goal**: Build a Kubernetes operator that creates Cloudflare tunnels via CRD specifications, maintains active/inactive status conditions, and provides complete cleanup when removed via Helm.

**Key Requirements**:
- Single tunnel per CRD (simpler lifecycle management)
- Minikube-based development with automated testing
- Helm chart deployment with proper RBAC
- Comprehensive test script for rapid iteration
- Active/Inactive status conditions matching Cloudflare's tunnel states

## Phase 1: Foundational Setup (Days 1-2)

### Project Structure
- Use operator-sdk to scaffold CloudflareTunnel operator
- Create proper Go module setup following [Operator SDK Documentation](https://sdk.operatorframework.io/docs/)
- Initialize with domain `tunnels.cloudflare.io`

### Core CRD Design
Define CloudflareTunnel custom resource:

```go
type CloudflareTunnelSpec struct {
    // +kubebuilder:validation:Required
    Name string `json:"name"`
    
    // +kubebuilder:validation:Required  
    AccountID string `json:"accountId"`
    
    // +kubebuilder:validation:Optional
    // +kubebuilder:default="cloudflare"
    ConfigSource string `json:"configSource,omitempty"`
    
    // +kubebuilder:validation:Optional
    Ingress []TunnelIngress `json:"ingress,omitempty"`
}

type TunnelIngress struct {
    Hostname string `json:"hostname,omitempty"`
    Service  string `json:"service"`
}

type CloudflareTunnelStatus struct {
    // Standard Kubernetes conditions
    Conditions []metav1.Condition `json:"conditions,omitempty"`
    
    // Tunnel-specific status
    TunnelID string `json:"tunnelId,omitempty"`
    Active   bool   `json:"active"`
    Ready    bool   `json:"ready"`
    
    ObservedGeneration int64 `json:"observedGeneration,omitempty"`
}
```

### Status Conditions
Following [Kubernetes API Conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md):

```go
const (
    TypeReady       = "Ready"
    TypeProgressing = "Progressing" 
    TypeDegraded    = "Degraded"
    TypeActive      = "Active"     // Tunnel is live in Cloudflare
    TypeInactive    = "Inactive"   // Tunnel exists but not connected
)
```

### Validation Checkpoints
- Verify operator-sdk scaffolding compiles
- Check CRD generation with proper validation rules
- Ensure status subresource is enabled

## Phase 2: Core Controller Implementation (Day 2)

### Controller Logic
Implement reconciliation following patterns from the architecture guide's [Controller Implementation](operators/cloudflare/architecture.md#phase-4-controller-implementation):

- Generation-based tracking for configuration drift
- Proper finalizer management for cleanup
- Rate limiting for Cloudflare API calls
- Error classification (transient vs permanent)

### Tunnel Lifecycle
1. **Creation**: Create tunnel via Cloudflare API
2. **Configuration**: Update tunnel ingress rules if specified
3. **Status Updates**: Report Active/Inactive based on Cloudflare tunnel status
4. **Cleanup**: Delete tunnel and remove finalizers

### Cloudflare Client Integration
Leverage the robust client wrapper from [Phase 3: Cloudflare Client Integration](operators/cloudflare/architecture.md#phase-3-cloudflare-client-integration):

- Rate limiting (10 requests/second, burst 20)
- Comprehensive error handling
- Proper authentication via API token

### Validation Checkpoints  
- Controller compiles and handles basic reconciliation
- Finalizer cleanup works correctly
- Status conditions update properly

## Phase 3: Helm Chart Development (Day 3)

### Chart Structure
Following [Helm Chart Best Practices](operators/research.md#5-helm-chart-best-practices):

```
cloudflare-tunnel-operator/
├── Chart.yaml
├── values.yaml
├── values.schema.json
├── crds/
│   └── tunnels.cloudflare.io_cloudflaretunnels.yaml
├── templates/
│   ├── deployment.yaml
│   ├── rbac.yaml
│   ├── service-account.yaml
│   └── secret.yaml
```

### RBAC Configuration
Minimal permissions following [Security Guardrails](operators/research.md#3-security-guardrails-and-rbac):

```yaml
rules:
- apiGroups: ["tunnels.cloudflare.io"]
  resources: ["cloudflaretunnels", "cloudflaretunnels/status", "cloudflaretunnels/finalizers"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list", "watch"]
```

### Production Values
```yaml
operator:
  replicas: 1  # Single replica for simplicity
  resources:
    limits: {cpu: 200m, memory: 128Mi}
    requests: {cpu: 50m, memory: 64Mi}

cloudflare:
  # API token provided via secret
  secretName: cloudflare-credentials
  
monitoring:
  enabled: true
  serviceMonitor: true
```

### Security Context
From [Container Security](operators/research.md#container-security):

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

### Validation Checkpoints
- Helm chart installs successfully
- CRDs are properly managed
- RBAC provides minimal required permissions

## Phase 4: Automated Testing Infrastructure (Day 4)

### Test Script Architecture
Create `scripts/test.sh` that provides complete lifecycle automation:

```bash
#!/bin/bash
# Single command: ./scripts/test.sh

set -e

CLUSTER_NAME="cf-tunnel-test"
NAMESPACE="cloudflare-tunnel-system" 
IMAGE_TAG="cf-tunnel-operator:dev"

cleanup_cloudflare() {
    # Fallback cleanup for orphaned tunnels
    echo "🧹 Cleaning up orphaned Cloudflare tunnels..."
    # Use CF API to list and delete test tunnels
}

main() {
    echo "🚀 Starting Cloudflare Tunnel Operator Test Cycle"
    
    # Build and test
    make docker-build IMG=$IMAGE_TAG
    
    # Minikube lifecycle
    minikube delete --profile $CLUSTER_NAME || true
    minikube start --profile $CLUSTER_NAME
    minikube image load $IMAGE_TAG --profile $CLUSTER_NAME
    
    # Deploy operator
    helm install cf-tunnel-operator ./charts/cloudflare-tunnel-operator \
        --namespace $NAMESPACE --create-namespace \
        --set image.repository=cf-tunnel-operator \
        --set image.tag=dev \
        --set cloudflare.apiToken="$CLOUDFLARE_API_TOKEN"
    
    # Run tests
    run_functionality_tests
    
    # Cleanup test
    test_helm_removal
    
    # Final cleanup
    minikube delete --profile $CLUSTER_NAME
    cleanup_cloudflare
    
    echo "✅ Test cycle completed successfully"
}
```

### Test Scenarios
1. **Tunnel Creation**: Verify tunnel appears in Cloudflare dashboard
2. **Status Updates**: Check Active/Inactive conditions update correctly  
3. **Configuration Changes**: Test ingress rule updates
4. **Helm Removal**: Ensure complete cleanup of tunnels
5. **Error Handling**: Test API failures and rate limiting

### Validation Framework
Based on [Testing Strategies](operators/research.md#7-comprehensive-testing-strategies):

```go
// Integration tests using envtest
func TestTunnelReconciliation(t *testing.T) {
    // Test tunnel creation lifecycle
    // Test status condition updates  
    // Test finalizer cleanup
}
```

### Validation Checkpoints
- Single command rebuilds and tests entire operator
- All test scenarios pass consistently
- Cleanup removes all external resources
- Test provides clear pass/fail summary

## Technical Implementation Details

### Rate Limiting Strategy
Following [Rate Limiting patterns](operators/research.md#8-rate-limiting-and-resource-management):

```go
type TunnelClient struct {
    api     *cloudflare.API
    limiter *rate.Limiter  // 10 RPS, burst 20
}
```

### Status Condition Management
Implement comprehensive status reporting:

```go
func (r *CloudflareTunnelReconciler) updateTunnelStatus(ctx context.Context, tunnel *tunnelv1.CloudflareTunnel) error {
    // Check tunnel status from Cloudflare API
    cfTunnel, err := r.cfClient.GetTunnel(ctx, tunnel.Spec.AccountID, tunnel.Status.TunnelID)
    
    // Update Active/Inactive condition based on tunnel connections
    if len(cfTunnel.Connections) > 0 {
        meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
            Type:   TypeActive,
            Status: metav1.ConditionTrue,
            Reason: "TunnelConnected", 
            Message: fmt.Sprintf("Tunnel has %d active connections", len(cfTunnel.Connections)),
        })
    } else {
        meta.SetStatusCondition(&tunnel.Status.Conditions, metav1.Condition{
            Type:   TypeActive,
            Status: metav1.ConditionFalse,
            Reason: "TunnelDisconnected",
            Message: "Tunnel exists but has no active connections",
        })
    }
}
```

### Error Handling Strategy
Classify errors for appropriate retry behavior:

```go
func (r *CloudflareTunnelReconciler) handleAPIError(err error) (ctrl.Result, error) {
    var cfErr *cloudflare.Error
    if errors.As(err, &cfErr) {
        switch cfErr.StatusCode {
        case http.StatusTooManyRequests:
            return ctrl.Result{RequeueAfter: 2 * time.Minute}, nil
        case http.StatusNotFound:
            // Resource doesn't exist, treat as success for deletion
            return ctrl.Result{}, nil
        default:
            return ctrl.Result{RequeueAfter: 30 * time.Second}, err
        }
    }
    return ctrl.Result{}, err
}
```

## Success Criteria

### Phase 1 Success
- [ ] Operator project scaffolded with proper Go modules
- [ ] CloudflareTunnel CRD defined with validation rules
- [ ] Basic controller compiles without errors

### Phase 2 Success  
- [ ] Controller creates tunnels via Cloudflare API
- [ ] Status conditions update based on tunnel state
- [ ] Finalizers ensure proper cleanup

### Phase 3 Success
- [ ] Helm chart installs operator successfully
- [ ] RBAC provides minimal required permissions
- [ ] Chart removal cleans up all resources

### Phase 4 Success
- [ ] Single test command validates entire operator
- [ ] Tests consistently pass with proper cleanup
- [ ] Minikube lifecycle fully automated

## Development Workflow

### Daily Iteration Cycle
```bash
# Make code changes
vim internal/controller/cloudflaretunnel_controller.go

# Test entire operator 
./scripts/test.sh

# Review results and iterate
```

### Key Commands
```bash
# Generate CRDs and manifests
make generate manifests

# Build container image
make docker-build IMG=cf-tunnel-operator:dev

# Run unit tests
make test

# Full integration test
./scripts/test.sh
```

## References

### Architecture Foundation
- [Building a Cloudflare Kubernetes Operator](operators/cloudflare/architecture.md) - Comprehensive patterns and best practices
- [Phase 3: Cloudflare Client Integration](operators/cloudflare/architecture.md#phase-3-cloudflare-client-integration) - Rate-limited API client implementation

### Development Best Practices  
- [Operator SDK Documentation](https://sdk.operatorframework.io/docs/) - Official scaffolding and development guide
- [Building Production-Ready Kubernetes Operators](operators/research.md) - Security, testing, and operational patterns
- [Kubebuilder Book](https://book.kubebuilder.io/) - Controller development patterns

### API References
- [Cloudflare API Documentation](https://developers.cloudflare.com/api/) - Tunnel management endpoints
- [Kubernetes API Conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md) - Status condition patterns

## Next Steps

After successful implementation of this focused tunnel operator:

1. **Observability**: Add Prometheus metrics for tunnel status and API calls
2. **Advanced Features**: Support for tunnel routing rules and load balancing  
3. **Integration**: Connect with ingress controllers for automatic tunnel creation
4. **Security**: Implement webhook validation for tunnel specifications
5. **Scaling**: Add support for multiple tunnels per operator instance

This focused approach ensures a working tunnel operator with comprehensive testing before expanding to more complex features like the full access policy implementation outlined in the architecture guide.