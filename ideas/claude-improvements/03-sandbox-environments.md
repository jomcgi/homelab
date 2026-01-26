# Kubernetes Sandbox Development Environments

## Overview

Provide Claude Code with isolated Kubernetes namespaces for testing and development, enabling safe experimentation without affecting production workloads.

## Architecture

### Custom Resource Definition (CRD)

```yaml
apiVersion: claude.jomcgi.dev/v1alpha1
kind: ClaudeDevEnvironment
metadata:
  name: claude-session-abc123
spec:
  sessionId: abc123
  owner: claude
  ttl: 24h
  resources:
    cpu: "2"
    memory: "4Gi"
    storage: "10Gi"
  capabilities:
    - deploy-services
    - create-configmaps
    - create-secrets
    - port-forward
  networking:
    allowInternalAPIs: true
    allowExternalEgress: false
status:
  namespace: claude-dev-abc123
  phase: Active
  expiresAt: "2024-01-20T12:00:00Z"
```

## Features

### 1. Session-Isolated Namespaces

- **Automatic Provisioning**: Create namespace on session start
- **Unique Naming**: `claude-dev-<session-id>` format
- **Resource Quotas**: Strict limits to prevent resource exhaustion
- **Priority Classes**: Low priority to ensure prod workloads take precedence

### 2. RBAC Configuration

```yaml
# Sandbox namespace permissions (full control)
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]
  namespaces: ["claude-dev-*"]

# Cluster-wide permissions (read-only)
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["get", "list", "watch"]
  namespaces: ["*"]
```

### 3. Resource Management

- **CPU Limit**: 2 cores per sandbox
- **Memory Limit**: 4Gi per sandbox
- **Storage**: 10Gi PVC per sandbox
- **Pod Count**: Maximum 10 pods
- **Priority**: -1000 (lower than production)

### 4. Network Policies

```yaml
# Allow internal service communication
- Allow pod-to-pod within sandbox namespace
- Allow access to cluster DNS
- Allow access to internal APIs (with rate limiting)
- Block external internet access by default
- Block access to production namespaces
```

### 5. Automatic Cleanup

- **TTL-based**: Delete after 24 hours of inactivity
- **Session-end**: Clean up when Claude session ends
- **Graceful Termination**: 5-minute warning before deletion
- **Data Persistence**: Option to save work to permanent storage

## Implementation

### Operator Components

#### 1. ClaudeDevEnvironment Controller

```go
type ClaudeDevEnvironmentController struct {
    client.Client
    Scheme *runtime.Scheme
}

func (r *ClaudeDevEnvironmentController) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    // 1. Create namespace with unique name
    // 2. Apply RBAC rules
    // 3. Set resource quotas
    // 4. Configure network policies
    // 5. Set TTL for cleanup
    // 6. Update status
}
```

#### 2. Garbage Collector

- Runs every 5 minutes
- Checks for expired environments
- Sends notifications before deletion
- Cleans up all resources

#### 3. Session Manager Integration

- Links Claude sessions to K8s environments
- Provides kubectl context configuration
- Manages credentials and access tokens
- Tracks resource usage

### Claude Integration

#### Environment Variables

```bash
KUBE_NAMESPACE=claude-dev-abc123
KUBE_CONTEXT=claude-sandbox
KUBECTL_ARGS="--namespace=claude-dev-abc123"
```

#### Available Commands

```bash
# Deploy a test service
kubectl apply -f deployment.yaml

# Check pod status
kubectl get pods

# Port forward for testing
kubectl port-forward svc/my-service 8080:80

# Run integration tests
kubectl run test --image=test-runner --rm -it

# Check resource usage
kubectl top pods
```

## Use Cases

### 1. Testing Deployments

- Deploy services before production
- Test configuration changes
- Validate Helm charts
- Run smoke tests

### 2. Development Workflows

- Iterate on Kubernetes manifests
- Test operators and controllers
- Debug networking issues
- Experiment with new services

### 3. Learning and Experimentation

- Safe environment for learning K8s
- Try new deployment patterns
- Test disaster recovery procedures
- Explore service mesh configurations

## Security Considerations

### Isolation Mechanisms

- **Namespace Isolation**: Kubernetes namespaces provide logical separation
- **Network Policies**: Strict ingress/egress rules
- **RBAC**: Fine-grained permission control
- **Resource Quotas**: Prevent resource exhaustion
- **Pod Security Standards**: Enforce security policies

### Attack Surface Mitigation

- No cluster-admin permissions
- No access to system namespaces
- No node-level access
- Audit logging for all actions
- Automatic cleanup reduces exposure time

## Monitoring and Observability

### Metrics

- Sandbox creation/deletion rate
- Resource utilization per sandbox
- Session duration statistics
- Error rates and types

### Logging

- All kubectl commands logged
- Resource creation/deletion events
- Access attempts to restricted resources
- Cleanup actions and reasons

### Alerts

- Resource quota exceeded
- Suspicious activity detected
- Cleanup failures
- Orphaned resources

## Benefits

- **Safe Experimentation**: No risk to production
- **Faster Development**: Test changes immediately
- **Better Learning**: Hands-on K8s experience
- **Reduced Conflicts**: Isolated environments
- **Cost Optimization**: Automatic cleanup

## Future Enhancements

- Template library for common scenarios
- Snapshot/restore capabilities
- Multi-user collaboration in same sandbox
- Integration with CI/CD pipelines
- Cost tracking per session
