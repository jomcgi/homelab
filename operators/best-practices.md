# Kubernetes Operator Development Best Practices

## Reconciliation Patterns

### State Machine

```
┌──────────────────────────────────────────────────────┐
│ Reconciliation State Machine                          │
│                                                       │
│  ┌─────────┐     ┌──────────┐     ┌──────────┐     │
│  │ Pending │────►│Provision │────►│  Ready   │     │
│  └─────────┘     └──────────┘     └──────────┘     │
│       │               │                 │           │
│       └───────┬───────┴─────────────────┘           │
│               ▼                                     │
│         ┌──────────┐                                │
│         │  Error   │                                │
│         └────┬─────┘                                │
│              └───► Retry (exponential backoff)     │
└──────────────────────────────────────────────────────┘
```

Reconciliation must be **idempotent and level-based**:

```go
func (r *ResourceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    resource := &v1alpha1.MyResource{}
    if err := r.Get(ctx, req.NamespacedName, resource); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // Generation-based drift detection
    if resource.Generation != resource.Status.ObservedGeneration {
        return r.reconcileResource(ctx, resource)
    }

    // Periodic drift check
    return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}
```

## Lifecycle Management

### Finalizer Lifecycle

```
┌─────────────────────────────────────────────────────┐
│  Create ─►│Resource│─ Add finalizer ─►│Resource │  │
│           │(no fin)│                   │ (fin)   │  │
│                                           │         │
│  Delete ──────────────────────────────────┤         │
│                                           ▼         │
│                                   │DeletionTime│    │
│                                           │         │
│                           Cleanup external│         │
│                                           ▼         │
│                                   │Remove fin  │    │
│                                           │         │
│                                           ▼         │
│                                      │Deleted│      │
└─────────────────────────────────────────────────────┘
```

**Implementation**:

```go
const MyResourceFinalizer = "myresource.example.com/finalizer"

func (r *ResourceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    resource := &v1alpha1.MyResource{}
    if err := r.Get(ctx, req.NamespacedName, resource); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    if resource.DeletionTimestamp.IsZero() {
        if !controllerutil.ContainsFinalizer(resource, MyResourceFinalizer) {
            controllerutil.AddFinalizer(resource, MyResourceFinalizer)
            return ctrl.Result{}, r.Update(ctx, resource)
        }
    } else {
        if controllerutil.ContainsFinalizer(resource, MyResourceFinalizer) {
            if err := r.cleanupExternalResources(ctx, resource); err != nil {
                return ctrl.Result{}, err
            }
            controllerutil.RemoveFinalizer(resource, MyResourceFinalizer)
            return ctrl.Result{}, r.Update(ctx, resource)
        }
    }
    return r.reconcileNormal(ctx, resource)
}
```

## Error Handling

### Error Classification

```
┌─────────────────────────────────────────────────────┐
│           Error Occurred                            │
│                 │                                   │
│          ┌──────┴──────┐                           │
│          ▼             ▼                           │
│     Transient     Permanent                        │
│      (network)    (invalid)                        │
│          │             │                           │
│    ┌─────┴─────┐      └──────► Update status      │
│    ▼           ▼                                   │
│  Return    Circuit                                 │
│  error     breaker                                 │
└─────────────────────────────────────────────────────┘
```

Controller-runtime provides automatic backoff. Classify errors and return appropriately:

```go
func (r *ResourceReconciler) reconcileResource(ctx context.Context, resource *v1alpha1.MyResource) (ctrl.Result, error) {
    if err := r.externalAPI.Provision(resource); err != nil {
        if isTransient(err) {
            return ctrl.Result{}, err // Automatic backoff
        }
        r.updateStatusError(ctx, resource, err)
        return ctrl.Result{}, nil
    }
    return ctrl.Result{}, nil
}

// Rate limiting for external APIs
type RateLimitedClient struct {
    client  *http.Client
    limiter *rate.Limiter
}
```

## Security

**RBAC - least privilege**:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
rules:
  - apiGroups: ["myoperator.example.com"]
    resources: ["resources", "resources/status", "resources/finalizers"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

**Container security**:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

**Secrets**: Mount as volumes, use encryption at rest, integrate Vault/ESO, implement rotation.

## Observability

**OpenTelemetry tracing**:

```go
func (r *MyOperatorReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    ctx, span := r.tracer.Start(ctx, "reconcile",
        trace.WithAttributes(
            attribute.String("k8s.resource.name", req.Name),
            attribute.String("k8s.resource.namespace", req.Namespace),
        ),
    )
    defer span.End()

    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, "failed")
        return ctrl.Result{}, err
    }
    span.SetStatus(codes.Ok, "success")
    return ctrl.Result{}, nil
}
```

## Well-Written Examples

- **CloudNativePG**: Direct K8s API, comprehensive backup/recovery
- **Strimzi Kafka**: Custom pod management, production-scale
- **AWS ACK**: Service-specific controllers, code generation

## Testing

**Unit tests** (80-90% coverage):

```go
func TestReconciler(t *testing.T) {
    client := fake.NewClientBuilder().WithObjects(objects...).Build()
    reconciler := &MyReconciler{Client: client}
    _, err := reconciler.Reconcile(ctx, req)
    assert.NoError(t, err)
}
```

**Integration** (EnvTest), **E2E** (Kind/K3s).

## Configuration

**Concurrency**:

```go
func (r *ExampleReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&examplev1.Example{}).
        WithOptions(controller.Options{MaxConcurrentReconciles: 5}).
        Complete(r)
}
```

**Status conditions**:

```go
const (
    TypeReady       = "Ready"
    TypeProgressing = "Progressing"
    TypeDegraded    = "Degraded"
)

func (r *ResourceReconciler) updateConditions(ctx context.Context, resource *v1alpha1.MyResource) error {
    if r.isProgressing(resource) {
        r.setCondition(resource, TypeProgressing, "True", "Reconciling", "Resource reconciling")
    }
    if r.isHealthy(resource) {
        r.setCondition(resource, TypeReady, "True", "Ready", "Resource ready")
    }
    resource.Status.ObservedGeneration = resource.Generation
    return r.Status().Update(ctx, resource)
}
```
