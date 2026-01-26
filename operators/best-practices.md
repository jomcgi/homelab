### Reconciliation Patterns

The reconciliation loop must be **idempotent and level-based**, deriving desired state from current specifications rather than reacting to events. Implement generation-based tracking to detect configuration drift:

```go
func (r *ResourceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    resource := &v1alpha1.MyResource{}
    if err := r.Get(ctx, req.NamespacedName, resource); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // Compare metadata.generation with status.observedGeneration
    if resource.Generation != resource.Status.ObservedGeneration {
        return r.reconcileResource(ctx, resource)
    }

    // Periodic drift detection for external resources
    return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}
```

### Lifecycle Management

Implement **multi-phase provisioning** for complex external resources, with proper finalizer management for cleanup:

```go
const MyResourceFinalizer = "myresource.example.com/finalizer"

func (r *ResourceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
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

### Error Handling

Classify errors as transient or permanent, implementing exponential backoff for transient failures and circuit breakers for external API protection. Controller-runtime provides automatic exponential backoff when returning errors.

## 3. Security Guardrails and RBAC

### Principle of Least Privilege

Grant operators only minimum required permissions, using namespace-scoped Roles over ClusterRoles when possible:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: operator-role
rules:
  - apiGroups: [""]
    resources: ["secrets", "configmaps"]
    verbs: ["get", "list", "create", "update"]
  - apiGroups: ["myoperator.example.com"]
    resources: ["resources", "resources/status", "resources/finalizers"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

### Container Security

Run operators with comprehensive security contexts:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

### Secret Management

- Use Kubernetes Secrets with encryption at rest
- Mount secrets as volumes, not environment variables
- Integrate with external secret managers (Vault, External Secrets Operator)
- Implement secret rotation mechanisms

### Complete Tracing Setup

Initialize OpenTelemetry with comprehensive configuration:

```go
func InitializeOpenTelemetry(ctx context.Context, cfg Config) (*sdktrace.TracerProvider, error) {
    exporter, err := otlptracegrpc.New(ctx,
        otlptracegrpc.WithEndpoint(cfg.CollectorURL),
        otlptracegrpc.WithInsecure(),
    )

    res, err := resource.Merge(
        resource.Default(),
        resource.NewWithAttributes(
            semconv.SchemaURL,
            semconv.ServiceName(cfg.ServiceName),
            semconv.ServiceVersion(cfg.ServiceVersion),
            attribute.String("k8s.operator.type", "custom-controller"),
        ),
    )

    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exporter),
        sdktrace.WithResource(res),
        sdktrace.WithSampler(sdktrace.ParentBased(
            sdktrace.TraceIDRatioBased(cfg.SampleRate),
        )),
    )

    otel.SetTracerProvider(tp)
    return tp, nil
}
```

### Trace Reconciliation Loops

Add comprehensive tracing to reconciliation:

```go
func (r *MyOperatorReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    ctx, span := r.tracer.Start(ctx, "reconcile",
        trace.WithAttributes(
            attribute.String("k8s.resource.name", req.Name),
            attribute.String("k8s.resource.namespace", req.Namespace),
        ),
    )
    defer span.End()

    // Reconciliation logic with span status updates
    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, "reconciliation failed")
        return ctrl.Result{}, err
    }

    span.SetStatus(codes.Ok, "reconciliation successful")
    return ctrl.Result{}, nil
}
```

## 6. Well-Written Operator Examples

**CloudNativePG** demonstrates excellence in PostgreSQL operator design:

- Direct Kubernetes API integration without StatefulSets
- Comprehensive backup and recovery
- Native streaming replication
- 5,000+ GitHub stars

**Strimzi Kafka Operator** showcases complex distributed system management:

- Complete Kafka ecosystem coverage
- Custom StrimziPodSet for pod management
- External access configuration
- Production-grade at scale

**AWS Controllers for Kubernetes (ACK)** provides patterns for cloud resource management:

- Service-specific controllers
- Direct AWS API integration
- IRSA authentication support
- Code generation from AWS APIs

### Testing

**Unit Tests** (80-90% coverage):

```go
func TestReconciler_Reconcile(t *testing.T) {
    scheme := runtime.NewScheme()
    client := fake.NewClientBuilder().
        WithScheme(scheme).
        WithObjects(existingObjects...).
        Build()

    reconciler := &MyReconciler{Client: client}
    _, err := reconciler.Reconcile(context.Background(), ctrl.Request{})
    assert.NoError(t, err)
}
```

**Integration Tests** with EnvTest:

```go
var _ = BeforeSuite(func() {
    testEnv = &envtest.Environment{
        CRDDirectoryPaths: []string{filepath.Join("..", "config", "crd", "bases")},
    }
    cfg, err = testEnv.Start()
    Expect(err).NotTo(HaveOccurred())
})
```

**E2E Tests** with Kind/K3s for complete validation including external integrations and upgrade scenarios.

### Implement Rate Limiting

Use golang.org/x/time/rate for client-side rate limiting:

```go
type RateLimitedClient struct {
    client  *http.Client
    limiter *rate.Limiter
}

func NewRateLimitedClient(rps rate.Limit, burst int) *RateLimitedClient {
    return &RateLimitedClient{
        client:  &http.Client{Timeout: 30 * time.Second},
        limiter: rate.NewLimiter(rps, burst),
    }
}

func (c *RateLimitedClient) Do(ctx context.Context, req *http.Request) (*http.Response, error) {
    if err := c.limiter.Wait(ctx); err != nil {
        return nil, err
    }
    return c.client.Do(req)
}
```

### Configure Controller Concurrency

```go
func (r *ExampleReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&examplev1.Example{}).
        WithOptions(controller.Options{
            MaxConcurrentReconciles: 5, // Based on external API limits
        }).
        Complete(r)
}
```

### Standard Condition Implementation

Follow Kubernetes conventions for status conditions:

```go
const (
    TypeReady       = "Ready"
    TypeProgressing = "Progressing"
    TypeDegraded    = "Degraded"
)

func (r *ResourceReconciler) updateConditions(ctx context.Context, resource *v1alpha1.MyResource) error {
    if r.isProgressing(resource) {
        r.setCondition(resource, TypeProgressing, "True", "Reconciling",
            "Resource is being reconciled")
    }

    if r.isHealthy(resource) && !r.isProgressing(resource) {
        r.setCondition(resource, TypeReady, "True", "Ready",
            "Resource is ready for use")
    }

    resource.Status.ObservedGeneration = resource.Generation
    return r.Status().Update(ctx, resource)
}
```
