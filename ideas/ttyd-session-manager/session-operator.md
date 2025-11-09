# Session Operator Proposal: CRD-Based Architecture

## Executive Summary

Refactor `ttyd-session-manager` from an imperative REST API that creates pods directly to a declarative operator-based architecture using Custom Resource Definitions (CRDs). This aligns with the homelab's GitOps philosophy and provides better lifecycle management, observability, and operational simplicity.

## Current Architecture Problems

### Imperative Pod Creation

The current implementation uses a REST API that directly creates pods:

```go
// charts/ttyd-session-manager/backend/main.go:122-153
func (sm *SessionManager) createSession(c *gin.Context) {
    config := NewPodConfig(sessionID, req.DisplayName, req.ImageTag, req.GitBranch)
    pod := BuildSessionPod(config)  // 493 lines of complex pod building logic

    createdPod, err := sm.clientset.CoreV1().Pods(namespace).Create(
        context.Background(),
        pod,
        metav1.CreateOptions{},
    )
    // ...
}
```

**Key Issues:**

1. **Not GitOps-friendly**: Cannot declare sessions in Git and let ArgoCD manage them
2. **No reconciliation**: If backend crashes during creation, session is orphaned
3. **No self-healing**: If a session pod dies unexpectedly, nothing recreates it
4. **Status scattered**: Must query pods directly to get session state
5. **Complex RBAC**: Backend needs cluster-wide pod create/delete permissions
6. **Architectural inconsistency**: Entire homelab is declarative GitOps, except this service

### Lifecycle Management Gaps

- **No retry logic**: Failed pod creation = lost session
- **Manual cleanup**: Pods can outlive their usefulness with no auto-cleanup
- **Orphaned resources**: Backend restart during creation leaves partial state
- **No finalizers**: Session deletion doesn't guarantee cleanup of related resources

### Observability Limitations

- Session state requires pod queries (expensive)
- No unified session status resource
- Kubernetes Events not tied to sessions
- Metrics require custom pod label selectors

## Proposed Architecture: Session Operator

### Core Design

Introduce a `Session` Custom Resource Definition (CRD) that represents a terminal session as a first-class Kubernetes resource. An operator controller watches Session resources and manages the lifecycle of associated pods.

### CRD Definition

```yaml
apiVersion: ttyd.jomcgi.dev/v1alpha1
kind: Session
metadata:
  name: homelab-dev-abc123
  namespace: ttyd-sessions
  annotations:
    ttyd.jomcgi.dev/created-by: "john@jomcgi.dev"
    ttyd.jomcgi.dev/description: "Working on ArgoCD configuration"
spec:
  # User-facing configuration
  displayName: "Homelab Development"

  # Image configuration
  imageTag: "main"  # Defaults to "main" if not specified

  # Git configuration
  gitBranch: "session-abc123"  # Auto-generated if not specified
  gitRemoteURL: "https://github.com/jomcgi/homelab.git"  # Defaults to homelab repo

  # Resource requests/limits (optional overrides)
  resources:
    requests:
      cpu: "100m"
      memory: "256Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"

  # Session lifecycle configuration
  ttl: "7d"  # Auto-delete after 7 days (optional)
  pauseAfterInactivity: "24h"  # Suspend after 24h idle (future feature)

  # Environment overrides (optional)
  env:
    - name: CUSTOM_VAR
      value: "custom-value"

status:
  # Overall session state
  state: Active  # Pending, Initializing, Active, Suspended, Failed, Terminating

  # Pod information
  podName: ttyd-session-abc123
  podPhase: Running

  # Git information
  gitBranch: session-abc123
  lastCommitSHA: "a1b2c3d4e5f6"
  lastPushTime: "2025-11-08T14:32:10Z"

  # Access information
  terminalURL: "/sessions/abc123"
  podIP: "10.42.1.45"

  # Usage metrics
  cpuUsage: "150m"
  memoryUsage: "256Mi"

  # Lifecycle metadata
  createdAt: "2025-11-08T10:00:00Z"
  lastActiveTime: "2025-11-08T14:30:00Z"
  ageDays: 0

  # Conditions (standard Kubernetes pattern)
  conditions:
  - type: Ready
    status: "True"
    lastTransitionTime: "2025-11-08T10:02:15Z"
    reason: PodRunning
    message: "Session pod is running and ready"

  - type: GitInitialized
    status: "True"
    lastTransitionTime: "2025-11-08T10:01:30Z"
    reason: BranchPushed
    message: "Git branch created and initial commit pushed"

  - type: NetworkReady
    status: "True"
    lastTransitionTime: "2025-11-08T10:02:00Z"
    reason: EnvoyHealthy
    message: "Envoy sidecar proxy is healthy"
```

### Controller Reconciliation Loop

```go
// Simplified controller structure
func (r *SessionReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    session := &ttydv1alpha1.Session{}
    if err := r.Get(ctx, req.NamespacedName, session); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // 1. Check if session is being deleted
    if !session.DeletionTimestamp.IsZero() {
        return r.handleDeletion(ctx, session)
    }

    // 2. Ensure finalizer is set
    if !controllerutil.ContainsFinalizer(session, sessionFinalizer) {
        controllerutil.AddFinalizer(session, sessionFinalizer)
        return ctrl.Result{}, r.Update(ctx, session)
    }

    // 3. Get or create the session pod
    pod := &corev1.Pod{}
    err := r.Get(ctx, types.NamespacedName{
        Name:      fmt.Sprintf("ttyd-session-%s", session.Name),
        Namespace: session.Namespace,
    }, pod)

    if apierrors.IsNotFound(err) {
        // Pod doesn't exist - create it
        pod = r.buildPod(session)  // Uses existing pod_builder.go logic
        if err := r.Create(ctx, pod); err != nil {
            return ctrl.Result{}, err
        }

        // Update session status
        session.Status.State = "Initializing"
        session.Status.PodName = pod.Name
        r.Status().Update(ctx, session)

        return ctrl.Result{RequeueAfter: 5 * time.Second}, nil
    } else if err != nil {
        return ctrl.Result{}, err
    }

    // 4. Update session status based on pod state
    r.updateSessionStatus(ctx, session, pod)

    // 5. Handle TTL-based cleanup
    if session.Spec.TTL != "" {
        if r.shouldDeleteDueToTTL(session) {
            return ctrl.Result{}, r.Delete(ctx, session)
        }
    }

    return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}
```

### Simplified Backend Architecture

The REST API becomes a thin wrapper around Session CRD operations:

```go
// New simplified backend
func (sm *SessionManager) createSession(c *gin.Context) {
    var req CreateSessionRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    sessionID := uuid.New().String()[:8]

    // Just create a Session CRD - operator handles the rest
    session := &ttydv1alpha1.Session{
        ObjectMeta: metav1.ObjectMeta{
            Name:      sessionID,
            Namespace: namespace,
            Annotations: map[string]string{
                "ttyd.jomcgi.dev/created-by": "api",
            },
        },
        Spec: ttydv1alpha1.SessionSpec{
            DisplayName: req.DisplayName,
            ImageTag:    req.ImageTag,
            GitBranch:   req.GitBranch,
        },
    }

    createdSession, err := sm.sessionClient.TTYDSessions(namespace).Create(
        context.Background(),
        session,
        metav1.CreateOptions{},
    )
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to create session: %v", err)})
        return
    }

    c.JSON(http.StatusCreated, SessionResponse{
        ID:       sessionID,
        Name:     req.DisplayName,
        State:    string(createdSession.Status.State),
        ImageTag: req.ImageTag,
    })
}

func (sm *SessionManager) listSessions(c *gin.Context) {
    // Query Session CRDs instead of pods
    sessions, err := sm.sessionClient.TTYDSessions(namespace).List(
        context.Background(),
        metav1.ListOptions{},
    )
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    // Status is already populated by controller
    response := make([]SessionResponse, len(sessions.Items))
    for i, session := range sessions.Items {
        response[i] = SessionResponse{
            ID:          session.Name,
            Name:        session.Spec.DisplayName,
            PodName:     session.Status.PodName,
            State:       string(session.Status.State),
            ImageTag:    session.Spec.ImageTag,
            Branch:      session.Status.GitBranch,
            CreatedAt:   session.Status.CreatedAt,
            LastActive:  session.Status.LastActiveTime,
            AgeDays:     session.Status.AgeDays,
            CPUUsage:    session.Status.CPUUsage,
            MemoryUsage: session.Status.MemoryUsage,
            TerminalURL: session.Status.TerminalURL,
        }
    }

    c.JSON(http.StatusOK, response)
}
```

**Lines of code reduction**: ~300 lines removed from backend (pod building, status polling, metrics collection)

## Benefits

### 1. Declarative GitOps Compatibility

**Before**: Cannot manage sessions via GitOps
```bash
# Must use REST API
curl -X POST http://api/sessions -d '{"name": "my-session"}'
```

**After**: Sessions can be declared in Git
```yaml
# git commit this file, ArgoCD syncs it
apiVersion: ttyd.jomcgi.dev/v1alpha1
kind: Session
metadata:
  name: persistent-dev-session
spec:
  displayName: "Long-running Dev Session"
  ttl: "30d"
```

### 2. Built-in Reconciliation & Self-Healing

The operator continuously ensures desired state matches actual state:

- **Session exists but pod deleted?** → Controller recreates pod
- **Pod failed to start?** → Controller retries with exponential backoff
- **Envoy sidecar crash?** → Controller detects and restarts pod
- **Backend crashes during creation?** → Controller completes the operation

### 3. Unified Status & Observability

**Before**: Status scattered across pods, annotations, metrics API
```bash
kubectl get pods -n ttyd-sessions -l session-id=abc123
kubectl describe pod ttyd-session-abc123
kubectl top pod ttyd-session-abc123
# Parse annotations manually
```

**After**: Single source of truth
```bash
kubectl get sessions
# NAME                   STATE    AGE   CPU     MEMORY   BRANCH
# homelab-dev-abc123     Active   2d    150m    256Mi    session-abc123

kubectl describe session homelab-dev-abc123
# Shows: status, conditions, events, lifecycle
```

### 4. Better RBAC & Security

**Before**: Backend needs cluster-wide pod create/delete permissions
```yaml
# Overly permissive
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["create", "delete", "list", "get"]
```

**After**: Users/services only need Session permissions
```yaml
# User RBAC
rules:
- apiGroups: ["ttyd.jomcgi.dev"]
  resources: ["sessions"]
  verbs: ["create", "list", "get", "delete"]

# Controller RBAC (restricted to operator)
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["create", "delete", "list", "get", "watch"]
  # Only controller has pod permissions
```

### 5. Advanced Lifecycle Management

Enable features that are hard/impossible with current architecture:

**TTL-based auto-cleanup:**
```yaml
spec:
  ttl: "7d"  # Auto-delete after 7 days
```

**Pause/resume (future feature):**
```yaml
spec:
  pauseAfterInactivity: "24h"
status:
  state: Suspended  # Controller scaled pod to 0
```

**Resource quotas:**
```yaml
# Limit total sessions per user
apiVersion: v1
kind: ResourceQuota
metadata:
  name: user-session-quota
spec:
  hard:
    count/sessions.ttyd.jomcgi.dev: "5"
```

### 6. Kubernetes-Native Observability

**Events:**
```bash
kubectl describe session homelab-dev-abc123
# Events:
#   Normal  Created        5m    session-controller  Created session pod
#   Normal  GitInitialized 4m30s session-controller  Git branch initialized
#   Normal  Ready          4m    session-controller  Session is ready
```

**Metrics (via controller-runtime):**
- `session_reconcile_duration_seconds` - Controller performance
- `session_reconcile_errors_total` - Reconciliation failures
- `sessions_by_state` - Active/suspended/failed sessions
- `session_lifecycle_duration_seconds` - Time in each state

**Traces (via OpenTelemetry):**
- Full session creation traced from API → CRD creation → pod start → readiness
- SigNoz can visualize entire lifecycle

### 7. Simplified Testing

**Controller testing** (table-driven, fast):
```go
func TestSessionReconciliation(t *testing.T) {
    tests := []struct {
        name           string
        session        *ttydv1alpha1.Session
        existingPod    *corev1.Pod
        expectedState  string
    }{
        {
            name: "creates pod when missing",
            session: &ttydv1alpha1.Session{
                Spec: ttydv1alpha1.SessionSpec{DisplayName: "test"},
            },
            existingPod:   nil,
            expectedState: "Initializing",
        },
        {
            name: "updates status when pod running",
            session: &ttydv1alpha1.Session{
                Spec: ttydv1alpha1.SessionSpec{DisplayName: "test"},
            },
            existingPod: &corev1.Pod{
                Status: corev1.PodStatus{Phase: corev1.PodRunning},
            },
            expectedState: "Active",
        },
    }
    // ...
}
```

### 8. Extensibility

Easy to add new features:

**Automatic backups:**
```go
// In reconciler
if time.Since(session.Status.LastBackupTime) > 1*time.Hour {
    r.createBackupJob(ctx, session)
}
```

**Resource monitoring:**
```go
// In reconciler
if session.Status.MemoryUsage > session.Spec.Resources.Limits.Memory {
    r.EventRecorder.Event(session, "Warning", "MemoryHigh", "Session using more memory than limit")
}
```

**Integration with external systems:**
```yaml
spec:
  webhooks:
    - url: "https://n8n.jomcgi.dev/webhook/session-created"
      events: ["created", "deleted"]
```

## Implementation Plan

### Phase 1: CRD & Controller Scaffolding (1-2 days)

1. **Initialize operator project:**
   ```bash
   cd operators/ttyd-session-manager
   kubebuilder init --domain jomcgi.dev --repo github.com/jomcgi/homelab
   kubebuilder create api --group ttyd --version v1alpha1 --kind Session
   ```

2. **Define CRD schema:**
   - Edit `api/v1alpha1/session_types.go`
   - Add spec/status fields from proposal above
   - Run `make generate` to update CRD manifests

3. **Basic controller:**
   - Move `pod_builder.go` logic into controller
   - Implement basic reconciliation loop
   - Add finalizer handling for cleanup

4. **RBAC:**
   - Generate RBAC manifests with kubebuilder markers
   - Create ServiceAccount for controller

### Phase 2: Status & Observability (1 day)

1. **Status updates:**
   - Implement pod status → session status mapping
   - Add condition types (Ready, GitInitialized, NetworkReady)
   - Update metrics collection to use session status

2. **Events:**
   - Add EventRecorder to controller
   - Emit events for lifecycle transitions

3. **Metrics:**
   - Expose controller-runtime metrics
   - Add custom session metrics (sessions_by_state, etc.)

### Phase 3: Backend Migration (1 day)

1. **Generate client:**
   ```bash
   make generate
   # Generates client code for Session CRD
   ```

2. **Update backend:**
   - Replace pod creation with Session CRD creation
   - Update list/get/delete endpoints to query Sessions
   - Remove pod-building code

3. **WebSocket proxy:**
   - Update to query Session resources for pod IP
   - Consider migrating to Envoy Gateway HTTPRoute (future)

### Phase 4: Advanced Features (1-2 days)

1. **TTL-based cleanup:**
   - Implement TTL parsing and validation
   - Add cleanup logic to reconciler

2. **Validation webhook:**
   ```bash
   kubebuilder create webhook --group ttyd --version v1alpha1 --kind Session --defaulting --programmatic-validation
   ```
   - Validate imageTag exists in registry
   - Validate resource requests/limits
   - Validate TTL format

3. **Conversion webhook (if needed):**
   - Support multiple CRD versions
   - Enable rolling upgrades

### Phase 5: Testing & Documentation (1 day)

1. **Unit tests:**
   - Controller reconciliation logic
   - Status update logic
   - TTL calculation

2. **Integration tests:**
   - envtest framework (runs real controller against API server)
   - Test full lifecycle: create → ready → delete

3. **Update documentation:**
   - Add operator architecture diagram
   - Document Session CRD schema
   - Update deployment guide

**Total estimated time**: 5-7 days

## Migration Path

### Backward Compatibility

Support both architectures during migration:

1. **Controller watches both:**
   - Session CRDs (new)
   - Pods with label `app=ttyd-session` (existing)

2. **Backend supports both:**
   - Create Session CRDs (new)
   - Fall back to direct pod creation if CRD not available (old)

3. **Gradual migration:**
   - Deploy operator alongside existing backend
   - New sessions use CRDs
   - Existing sessions continue using pods
   - Once all old sessions deleted, remove fallback code

### Data Migration

Migrate existing pod-based sessions to Session CRDs:

```bash
# Script to migrate existing sessions
kubectl get pods -n ttyd-sessions -l app=ttyd-session -o json | \
  jq -r '.items[] | @base64' | \
  while read pod; do
    # Extract session metadata from pod
    SESSION_ID=$(echo $pod | base64 -d | jq -r '.metadata.labels["session-id"]')
    DISPLAY_NAME=$(echo $pod | base64 -d | jq -r '.metadata.annotations["session-name"]')
    IMAGE_TAG=$(echo $pod | base64 -d | jq -r '.metadata.annotations["image-tag"]')

    # Create Session CRD
    kubectl apply -f - <<EOF
apiVersion: ttyd.jomcgi.dev/v1alpha1
kind: Session
metadata:
  name: $SESSION_ID
  namespace: ttyd-sessions
spec:
  displayName: "$DISPLAY_NAME"
  imageTag: "$IMAGE_TAG"
EOF
  done
```

## Alignment with Homelab Philosophy

From `CLAUDE.md`:

> **Project Philosophy**
> - **Simplicity over cleverness**
> - **Security by default**
> - **Observable, testable systems**
> - **Deep modules with clean interfaces**

### How This Proposal Aligns:

**Simplicity:**
- Session CRD is a simple interface hiding complex pod creation
- Backend becomes 300+ lines simpler
- Users interact with high-level Session resources, not low-level pods

**Security:**
- Better RBAC isolation (users can't create arbitrary pods)
- Validation webhooks prevent unsafe configurations
- Controller has minimal permissions (via service account)

**Observable:**
- Session status is a first-class resource
- Kubernetes Events provide lifecycle visibility
- Controller metrics integrate with SigNoz

**Deep Modules:**
- Session CRD = simple interface
- Controller = complex implementation (pod management, reconciliation, cleanup)
- Backend = thin API wrapper

**GitOps Consistency:**
- Every other service is declarative (ArgoCD Applications)
- Session operator makes sessions declarative too
- Enables IaC for development environments

## Alternative: Keep Current Architecture?

**When REST API approach makes sense:**
- Stateless workloads with no lifecycle
- External systems that can't use Kubernetes API
- Very simple resource creation (no reconciliation needed)

**Why it doesn't fit here:**
- Sessions have complex lifecycle (git init, running, auto-commit, cleanup)
- Need reconciliation (self-healing, status updates)
- Want GitOps compatibility
- Long-lived resources (not ephemeral)

## Conclusion

The Session Operator architecture provides:
- **Better operational simplicity** (reconciliation, self-healing)
- **GitOps compatibility** (declarative sessions)
- **Improved observability** (unified status, events, metrics)
- **Architectural consistency** (matches rest of homelab)
- **Future extensibility** (TTL, pause/resume, webhooks)

**Recommendation**: Proceed with operator implementation. The benefits significantly outweigh the 5-7 day development cost, and it aligns perfectly with the homelab's declarative, security-first philosophy.

## References

- [Kubernetes Operator Pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [Kubebuilder Book](https://book.kubebuilder.io/)
- [controller-runtime](https://github.com/kubernetes-sigs/controller-runtime)
- [ArgoCD Application CRD](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#applications) (similar pattern)
- Existing Cloudflare Operator: `operators/cloudflare/` (reference implementation)
