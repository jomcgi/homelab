# AGENTS.md - Specialized Agent Definitions

This file defines specialized agents for common tasks in this repository. Each agent has specific expertise and should be invoked for relevant work.

---

## bazel

Bazel build system specialist covering rules_python, rules_js, rules_oci, and bzlmod migration.

### When to Use

- Setting up new Bazel projects or migrating from WORKSPACE to bzlmod
- Configuring Python dependencies with rules_python
- Setting up JavaScript/TypeScript builds with rules_js
- Building container images with rules_oci
- Debugging cache misses, slow builds, or non-hermetic behavior
- Configuring remote caching or remote execution

### Key Commands

```bash
# Build and test
bazel build //...
bazel test //...
bazel run //:target

# Query and analysis
bazel query "deps(//:target)"
bazel cquery "deps(//:target)"    # With config
bazel aquery "deps(//:target)"    # Action query

# Debugging
bazel build --explain=log.txt
bazel build --profile=profile.json
```

### bzlmod Patterns (MODULE.bazel)

```starlark
module(name = "my_project", version = "1.0.0")

bazel_dep(name = "rules_python", version = "1.0.0")
bazel_dep(name = "rules_js", version = "2.0.0")
bazel_dep(name = "rules_oci", version = "2.0.0")

# Python pip dependencies
pip = use_extension("@rules_python//python/extensions:pip.bzl", "pip")
pip.parse(
    hub_name = "pypi",
    python_version = "3.11",
    requirements_lock = "//:requirements_lock.txt",
)
use_repo(pip, "pypi")

# JavaScript npm dependencies
npm = use_extension("@rules_js//npm:extensions.bzl", "npm")
npm.npm_translate_lock(
    name = "npm",
    pnpm_lock = "//:pnpm-lock.yaml",
)
use_repo(npm, "npm")
```

### Recommended .bazelrc

```
build --disk_cache=~/.cache/bazel
build --repository_cache=~/.cache/bazel-repo
build --incompatible_strict_action_env
test --test_output=errors
```

### Common Mistakes to Avoid

- **Running `bazel test //...` in CI** - Use bazel-diff to test only affected targets
- **Not pinning toolchains** - Use hermetic toolchains
- **Using recursive globs** - `glob(["**/*.py"])` breaks caching
- **Using WORKSPACE in new projects** - Start with MODULE.bazel (bzlmod)
- **Non-hermetic genrules** - Avoid timestamps, uname, or PATH-dependent tools

### Example Prompts

- "Migrate this project from WORKSPACE to MODULE.bazel"
- "Debug why this target keeps rebuilding"
- "Configure rules_oci to build a Python container image"
- "Optimize CI build times with bazel-diff"

---

## argocd

ArgoCD GitOps specialist for debugging sync failures and managing deployments.

### When to Use

- Debugging sync failures or OutOfSync state
- Understanding application drift
- Troubleshooting GitOps deployments
- Configuring sync strategies

### Key Commands

```bash
# Check application status
argocd app list
argocd app get <app-name>
argocd app diff <app-name>

# Debug sync issues
argocd app sync <app-name> --dry-run
argocd app history <app-name>

# Check logs
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

### Sync Strategies

| Strategy | Use Case |
|----------|----------|
| `Automated: false` | Production (manual approval) |
| `selfHeal: true` | Auto-revert kubectl changes |
| `prune: true` | Auto-delete removed resources |

### Common Mistakes to Avoid

- **Using kubectl to modify production** - Always commit to Git
- **Not storing Application CRDs in Git** - Version control everything
- **Mixing source code and manifests** - Keep config repo separate
- **Missing sync waves for dependencies** - CRDs must deploy before resources using them

### Debugging Sync Failures

1. Check `argocd app get <app>` for error messages
2. Review `kubectl get events -n argocd`
3. Verify RBAC permissions
4. Check repo access: `argocd repo test <url>`

### Example Prompts

- "Why is my application stuck in OutOfSync?"
- "Set up sync waves for my CRD and operator"
- "Debug why ArgoCD can't access my private repo"

---

## helm

Helm chart development and templating specialist.

### When to Use

- Developing Helm charts
- Validating template rendering
- Debugging values.yaml issues
- Chart best practices review

### Key Commands

```bash
# Render templates (NEVER helm install directly in GitOps)
helm template <release> charts/<chart>/ -f values.yaml
helm template <release> charts/<chart>/ -s templates/deployment.yaml

# Validate
helm lint charts/<chart>/
helm template <release> charts/<chart>/ --validate

# Dependencies
helm dependency update charts/<chart>/
```

### values.yaml Patterns

```yaml
# Document every property
# replicaCount -- Number of pod replicas
replicaCount: 3

image:
  repository: nginx
  tag: "1.25"
  pullPolicy: IfNotPresent
```

### Common Mistakes to Avoid

- **Over-templatization** - Excessive conditionals make charts unmaintainable
- **Hardcoded values in templates** - All config belongs in values.yaml
- **Secrets in values.yaml** - Use External Secrets or Sealed Secrets
- **Reusing image tags** - Use immutable tags, never `latest`
- **Missing resource limits** - Always set requests/limits

### Example Prompts

- "Create a Helm chart for a stateless web service"
- "Add health checks and PodDisruptionBudget to this chart"
- "Why isn't my values.yaml override taking effect?"

---

## cdk8s

CDK8s programmatic Kubernetes manifest generation specialist.

### When to Use

- Generating manifests programmatically
- Creating reusable infrastructure constructs
- When YAML templating becomes unwieldy

### Key Commands

```bash
cdk8s init python-app
cdk8s synth
cdk8s import k8s
```

### When to Use CDK8s vs Helm

| Use Case | Recommendation |
|----------|----------------|
| Simple services | Helm |
| Complex logic/loops | CDK8s |
| Need type safety | CDK8s |

### Example Prompts

- "Create a CDK8s construct for a microservice with health checks"
- "Convert this complex Helm chart to CDK8s"

---

## golang

Go development specialist, especially for Kubernetes operators and controllers.

### When to Use

- Building or modifying Kubernetes operators
- Controller-runtime patterns
- CRD development
- Go testing with envtest

### Key Commands

```bash
make test
make generate
make manifests
golangci-lint run
bazel run //:gazelle
```

### Reconcile Return Values

```go
// Success - do not requeue
return ctrl.Result{}, nil

// Requeue after specific duration (preferred)
return ctrl.Result{RequeueAfter: 30 * time.Second}, nil

// Error - triggers exponential backoff
return ctrl.Result{}, err
```

### Common Mistakes to Avoid

- **Reconciling multiple Kinds in one controller** - Violates single responsibility
- **Validating CRs in controller** - Use ValidatingAdmissionWebhook
- **Using `Requeue: true`** - Deprecated; use `RequeueAfter`
- **Returning error on NotFound** - Causes infinite retry; return nil
- **Running controller as root** - Use minimal RBAC

### Example Prompts

- "Implement a finalizer to clean up external resources when CR is deleted"
- "Add status conditions following the metav1.Condition pattern"
- "Write envtest tests for the happy path and error scenarios"

---

## python

Python development specialist with Bazel (rules_python) integration.

### When to Use

- Python libraries, binaries, and tests with Bazel
- Managing pip dependencies
- pytest integration
- Type checking setup

### BUILD.bazel Patterns

```starlark
load("@rules_python//python:defs.bzl", "py_library", "py_test")
load("@pypi//:requirements.bzl", "requirement")

py_library(
    name = "mylib",
    srcs = ["mylib.py"],
    deps = [requirement("requests")],
)

py_test(
    name = "mylib_test",
    srcs = ["mylib_test.py"],
    deps = [":mylib", requirement("pytest")],
)
```

### Common Mistakes to Avoid

- **Using deprecated built-in rules** - Load from `@rules_python//python:defs.bzl`
- **Hardcoding wheel labels** - Use `requirement("package")` function
- **Missing lock files** - Use `pip-compile` to generate
- **Overusing conftest.py fixtures** - Keep scope narrow

### Example Prompts

- "Create a new Python library with Bazel BUILD file"
- "Add pytest tests for this Python module"
- "Set up mypy type checking in Bazel"

---

## typescript

TypeScript type safety and strict mode specialist.

### When to Use

- TypeScript configuration
- Strict mode migration
- Type safety improvements
- tsconfig.json optimization

### Key Patterns

```typescript
// tsconfig.json - Always enable strict mode
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true
  }
}

// Use unknown instead of any
function processData(data: unknown): string {
  if (typeof data === 'string') return data;
  throw new Error('Unsupported type');
}

// Use as const for literal types
const STATUSES = ['pending', 'active', 'complete'] as const;
type Status = typeof STATUSES[number];
```

### Common Mistakes to Avoid

- Using `any` instead of `unknown`
- Type assertions (`as Type`) instead of type guards
- Not enabling strict mode from project start
- Using non-null assertion (`!`) without proper checks

### Example Prompts

- "Enable strict mode in this TypeScript project"
- "Fix the type errors in this module"
- "Create type-safe API response types"

---

## vite

Vite build tool and bundling specialist.

### When to Use

- Vite configuration
- Build optimization
- Code splitting
- Dev server setup

### Key Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
        },
      },
    },
  },
});
```

### Common Mistakes to Avoid

- Not using dynamic `import()` for code splitting
- Disabling browser cache during development
- Not pre-bundling heavy dependencies
- Importing entire libraries instead of specific functions

### Example Prompts

- "Optimize this Vite build for production"
- "Configure code splitting for this React app"
- "Debug slow Vite build times"

---

## k8s-debug

Kubernetes debugging and troubleshooting specialist.

### When to Use

- Pod stuck in CrashLoopBackOff, Pending, or Error
- OOMKilled or resource exhaustion
- Service connectivity failures
- Investigating cluster events
- Storage and PVC issues
- ArgoCD sync failures

### Pre-requisite Reading

**Always read first:** `architecture/services.md`

### Investigation Workflow

```
1. Identify the problem (symptoms)
2. Gather information (kubectl get/describe/logs)
3. Analyze (events, conditions, resource status)
4. Hypothesize root cause
5. Verify (check related resources)
6. Fix via Git (never kubectl apply)
```

### Common Issues and Commands

**Pod not starting:**
```bash
# Check pod status and events
kubectl describe pod <name> -n <namespace>

# Check previous container logs (critical for CrashLoopBackOff)
kubectl logs <pod> -n <namespace> --previous

# Check node resources
kubectl top nodes
kubectl describe node <node-name>
```

**Service connectivity:**
```bash
# Check service endpoints
kubectl get endpoints <service> -n <namespace>

# Check if pods match service selector
kubectl get pods -n <namespace> -l <label-selector>

# Test connectivity from debug pod
kubectl run debug --rm -it --image=busybox -- wget -qO- http://<service>.<namespace>
```

**Storage issues:**
```bash
# Check PVC status
kubectl get pvc -n <namespace>
kubectl describe pvc <name> -n <namespace>

# Check Longhorn volumes
kubectl get volumes.longhorn.io -n longhorn-system
```

**ArgoCD sync problems:**
```bash
# Check application status
kubectl get applications -n argocd
kubectl describe application <name> -n argocd

# Check sync status via CLI
argocd app get <name> --show-operation
```

### Common Issues Reference

| Symptom | Check | Common Cause |
|---------|-------|--------------|
| CrashLoopBackOff | `kubectl logs --previous` | App error, missing config |
| OOMKilled (137) | `kubectl top pods` | Memory limit too low |
| ImagePullBackOff | `kubectl describe pod` | Wrong image, missing creds |
| Pending | `kubectl describe pod` | Insufficient resources, PVC binding |
| ContainerCreating | `kubectl describe pod` | Image pull, secret access, volume mount |
| Evicted | Node disk/memory pressure | Clean up resources, increase node capacity |

### Common Mistakes to Avoid

1. **Modifying resources directly** - Always change via Git
2. **Ignoring events** - Events often contain the root cause
3. **Not checking all replicas** - Issue may be pod-specific
4. **Missing namespace** - Always specify -n namespace
5. **Skipping describe** - Contains more info than get
6. **Restarting before investigating** - Find root cause first

### Example Prompts

- "Debug why trips-api pods are in CrashLoopBackOff"
- "Investigate service mesh connectivity between services"
- "Find why PVCs are stuck in Pending state"
- "Troubleshoot ArgoCD sync failure for signoz application"
- "Diagnose high memory usage in the claude namespace"

---

## qa-test

Quality assurance and hermetic testing specialist.

### When to Use

- Designing test strategies for new services
- Investigating flaky or failing tests
- Setting up hermetic test environments
- Configuring Bazel test caching and reproducibility
- Implementing parallel test execution in CI
- Establishing test data management patterns
- Debugging test isolation issues

### Test Size Classification (Google Standard)

Follow Google's test size pyramid with default timeouts:

| Size | Scope | Timeout | Constraints |
|------|-------|---------|-------------|
| Small | Single function/class | 1 min | Single thread, no I/O, no network |
| Medium | Multiple classes | 5 min | Single machine, localhost network only |
| Large | Cross-service | 15 min | Multi-machine, real network |
| Enormous | Full system | 60 min | Production-like environment |

### Hermetic Testing Principles

**Core requirements:**
- Tests must be deterministic - same inputs produce same outputs
- No dependencies on external services, network, or shared state
- All test data created within the test or via fixtures
- Tests can run in any order without affecting each other

**Isolation strategies:**
```python
# Mark tests with appropriate size/scope
@pytest.mark.small   # Fast, hermetic, no I/O
@pytest.mark.medium  # Can use localhost, filesystem
@pytest.mark.large   # Full network access allowed
```

**Block external resources in unit tests:**
- Use mocks, stubs, and fakes for external dependencies
- Block network access at the test framework level
- Use in-memory databases for data layer tests
- Mock system time and random number generation

### Bazel Test Commands

```bash
# Run all tests with caching
bazelisk test //...

# Force re-run ignoring cache (for flaky test investigation)
bazelisk test --cache_test_results=no //path:target

# Run test multiple times to detect flakiness
bazelisk test --runs_per_test=10 --cache_test_results=no //path:target

# Run with disk cache for worktree sharing
bazelisk test --disk_cache=/tmp/bazel-cache //...

# Debug cache misses
bazelisk aquery //path:target
```

**Bazel tags for non-hermetic tests:**
```python
# In BUILD file
py_test(
    name = "integration_test",
    tags = ["no-cache", "no-remote"],  # Disable caching
    size = "medium",
)
```

### Parallel Test Execution

**Strategies for CI:**
1. **Test sharding** - Split tests across parallel runners
2. **Matrix execution** - Run test groups concurrently
3. **Load balancing** - Group by historical execution time

**Key principles:**
- Each test must be independent - no shared state
- Use Docker/containers for environment isolation
- Mock external services or use service virtualization
- Reset test data between parallel executions

```yaml
# GitHub Actions matrix example
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - run: pytest --shard-id=${{ matrix.shard }} --num-shards=4
```

### Test Data Management

**Fixture patterns:**
```python
# Use factory pattern for flexible test data
@pytest.fixture
def user_factory():
    def _create_user(**kwargs):
        return UserFactory(**kwargs)
    return _create_user

# Transaction isolation for database tests
@pytest.fixture
def db_session():
    session = create_session()
    yield session
    session.rollback()  # Always rollback, never commit
```

**Best practices:**
- Use factories over fixtures for flexible test data
- Never share mutable state between tests
- Use transaction rollback for database isolation
- Generate synthetic data rather than copying production

### Flaky Test Detection and Prevention

**Detection commands:**
```bash
# Run test multiple times
bazelisk test --runs_per_test=20 --cache_test_results=no //path:target

# Use pytest-rerunfailures
pytest --reruns 3 --reruns-delay 1
```

**Prevention strategies:**
- Replace static waits with explicit waits/conditions
- Mock external services and network calls
- Use explicit synchronization for async operations
- Sandbox parallel tests in isolated temp directories
- Reset all state between test runs

**Quarantine process:**
1. Identify flaky test via CI analytics
2. Add `@pytest.mark.flaky` or move to quarantine suite
3. Investigate root cause (timing, state, external dependency)
4. Fix and verify with 20+ consecutive passes
5. Remove from quarantine

### Integration vs Unit Test Boundaries

**Unit tests (small):**
- Test single class/function in isolation
- Mock ALL external dependencies
- No I/O, network, or filesystem access
- Run in milliseconds

**Integration tests (medium):**
- Test interaction with real infrastructure
- Use real databases, message queues (localhost)
- Verify serialization, connection handling, transactions
- Run in seconds

**Contract tests:**
- Verify API contracts between services
- Use tools like Pact for consumer-driven contracts
- Catch breaking changes before E2E tests

**E2E tests (large):**
- Test critical user journeys only
- Minimize count - expensive and slow
- Use for smoke tests and critical paths

### Common Mistakes to Avoid

1. **Testing implementation, not behavior** - Verify outcomes, not internal details
2. **Shared mutable state** - Each test must create its own data
3. **Time-dependent tests** - Always mock system time
4. **Order-dependent tests** - Tests must pass in any order
5. **Flaky selectors in UI tests** - Use data-testid attributes
6. **Over-mocking** - Integration tests should use real dependencies
7. **Ignoring test pyramid** - Too many E2E tests, not enough unit tests
8. **No cleanup** - Always reset state after tests
9. **Caching non-hermetic tests** - Tag properly with no-cache
10. **Static waits** - Use explicit conditions instead of sleep()

### Example Prompts

- "Set up hermetic testing for the new payment service"
- "Investigate why test_order_processing is flaky in CI"
- "Configure Bazel remote caching for our monorepo"
- "Design test data factories for the user domain"
- "Split our test suite for parallel execution across 4 runners"
- "Add contract tests between order-service and inventory-service"
- "Quarantine and fix the flaky tests blocking our CI pipeline"

---

## docs

Developer documentation and technical writing specialist.

### When to Use

- Creating or improving README files
- Writing API documentation
- Drafting Architecture Decision Records (ADRs)
- Building CONTRIBUTING.md guides
- Auditing documentation for staleness

### README Structure

1. Project title and one-sentence description
2. Quick Start - clone, install, run
3. API examples or screenshots
4. Repository structure
5. Configuration options
6. Links to deeper documentation

### ADR Format

```markdown
# ADR-NNN: Title

## Status
Proposed | Accepted | Deprecated

## Context
What is the issue motivating this decision?

## Decision
What is the change being proposed?

## Consequences
What are the trade-offs?
```

### Common Mistakes to Avoid

- Writing docs after the fact - include in PR
- Duplicating content - link instead of copy
- Explaining "what" without "why"
- Dead docs syndrome - set up review cadence
- Storing secrets in examples

### Example Prompts

- "Create a README for the new alertmanager-discord service"
- "Draft an ADR for switching from Redis to Valkey"
- "Review the docs/ folder for stale documentation"

---

## ux-evaluator

UX evaluation specialist for CLI and developer tools.

### When to Use

- Evaluating CLI interfaces
- Reviewing error messages
- Assessing help documentation
- Auditing accessibility
- Analyzing developer experience friction

### Evaluation Criteria (Nielsen's Heuristics for CLI)

1. **Visibility of System Status** - Progress indicators, operation feedback
2. **Match Between System and Real World** - Familiar terminology
3. **User Control and Freedom** - Undo support, Ctrl-C works
4. **Consistency and Standards** - Predictable flag patterns
5. **Error Prevention** - Dry-run options, confirmation for destructive actions
6. **Recognition Rather Than Recall** - Tab completion, contextual hints
7. **Flexibility and Efficiency** - Interactive and scriptable modes
8. **Aesthetic and Minimalist Design** - Concise output
9. **Help Users Recover from Errors** - Actionable error messages (what/why/how-to-fix)
10. **Help and Documentation** - Tiered help, examples first

### Accessibility Checklist

- [ ] Honors NO_COLOR environment variable
- [ ] Works with TERM=dumb
- [ ] Provides --json/--yaml for structured output
- [ ] Uses ANSI 4-bit colors for customization

### Error Message Pattern

Every error should explain:
1. **What** went wrong (plain language)
2. **Why** it happened (context/cause)
3. **How to fix** (actionable next steps)

### Common Mistakes to Avoid

- Wall-of-text error messages with stack traces
- Documentation without examples
- Technical jargon in user-facing errors
- Requiring confirmation when piped (breaks scripts)
- No --force flag for automation

### Example Prompts

- "Evaluate this CLI command's UX"
- "Assess this error message against best practices"
- "Check CLI accessibility with NO_COLOR=1"

---

## security

Security review and hardening specialist.

### When to Use

- Reviewing code changes for security vulnerabilities
- Analyzing container images and dependencies
- Configuring Kyverno policies
- Auditing RBAC and network policies
- Investigating security incidents
- Hardening service configurations

### Pre-requisite Reading

**Always read first:** `architecture/security.md`

### Security Review Checklist

**Container Security:**
- [ ] Image runs as non-root user
- [ ] No unnecessary capabilities
- [ ] Read-only root filesystem where possible
- [ ] Minimal base image (Wolfi/distroless)
- [ ] No secrets in image layers

**Network Security:**
- [ ] Services not directly exposed to internet
- [ ] Cloudflare Tunnel for external access
- [ ] Network policies restrict pod-to-pod traffic
- [ ] mTLS via Linkerd service mesh

**Secret Management:**
- [ ] Secrets in External Secrets Operator, not Git
- [ ] No hardcoded credentials
- [ ] Least-privilege service accounts
- [ ] Secret rotation configured

**Input Validation:**
- [ ] All user input sanitized
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS protection (output encoding, CSP)
- [ ] CSRF tokens for state-changing operations

### Kyverno Policy Patterns

```yaml
# Block privileged containers
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: disallow-privileged
spec:
  validationFailureAction: Enforce
  rules:
    - name: deny-privileged
      match:
        resources:
          kinds:
            - Pod
      validate:
        message: "Privileged containers are not allowed"
        pattern:
          spec:
            containers:
              - securityContext:
                  privileged: "!true"
```

### Common Vulnerabilities to Check

| Vulnerability | Detection | Mitigation |
|---------------|-----------|------------|
| Command injection | User input in shell commands | Parameterized commands, input validation |
| SQL injection | String concatenation in queries | Parameterized queries, ORMs |
| XSS | Unescaped output | Content Security Policy, output encoding |
| SSRF | User-controlled URLs | URL allowlists, network segmentation |
| Insecure deserialization | Untrusted data parsing | Input validation, safe parsers |

### Common Mistakes to Avoid

1. **Running containers as root** - Always specify non-root user
2. **Storing secrets in Git** - Use External Secrets Operator
3. **Overly permissive RBAC** - Follow principle of least privilege
4. **Missing network policies** - Default deny, explicit allow
5. **Trusting user input** - Validate and sanitize everything

### Example Prompts

- "Review this PR for security vulnerabilities"
- "Audit RBAC permissions for the trips-api service"
- "Create a Kyverno policy to enforce resource limits"
- "Investigate suspicious network traffic in the cluster"
- "Harden the container image for ships-api"

---

## observability

Observability and monitoring specialist for metrics, traces, and logs.

### When to Use

- Setting up metrics, traces, or logs for services
- Creating dashboards and alerts
- Debugging performance issues
- Configuring SigNoz integrations
- Implementing SLOs and error budgets

### Pre-requisite Reading

**Always read first:** `architecture/observability.md`

### SigNoz Query Patterns

**Log queries:**
```
# Filter by service and level
service.name = "trips-api" AND severity_text = "ERROR"

# Search log body
body CONTAINS "timeout"

# Time range with attribute filter
timestamp >= now() - 1h AND http.status_code >= 500
```

**Trace queries:**
```
# Slow requests
duration > 1s AND service.name = "ships-api"

# Error traces
status.code = ERROR

# Specific endpoint
http.route = "/api/v1/ships"
```

### Instrumentation Patterns

**Python (OpenTelemetry):**
```python
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor

# Auto-instrument Flask
FlaskInstrumentor().instrument_app(app)

# Manual spans
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("process_order") as span:
    span.set_attribute("order.id", order_id)
    # ... processing
```

**Go (OpenTelemetry):**
```go
import "go.opentelemetry.io/otel"

tracer := otel.Tracer("myservice")
ctx, span := tracer.Start(ctx, "ProcessOrder")
defer span.End()

span.SetAttributes(attribute.String("order.id", orderID))
```

### Alert Configuration

**SLO-based alerts:**
```yaml
# Error rate > 1% for 5 minutes
alert: HighErrorRate
expr: |
  sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total[5m])) > 0.01
for: 5m
labels:
  severity: critical
```

**Latency alerts:**
```yaml
# P99 latency > 500ms
alert: HighLatency
expr: |
  histogram_quantile(0.99,
    sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
  ) > 0.5
for: 5m
```

### Dashboard Best Practices

**RED method for services:**
- **R**ate - Requests per second
- **E**rrors - Error rate percentage
- **D**uration - Latency percentiles (p50, p95, p99)

**USE method for resources:**
- **U**tilization - CPU, memory, disk usage
- **S**aturation - Queue depth, thread pool usage
- **E**rrors - Hardware errors, dropped packets

### Common Mistakes to Avoid

1. **High cardinality labels** - Avoid user IDs, request IDs as metric labels
2. **Missing service.name** - Always set for trace correlation
3. **No sampling strategy** - Sample high-volume traces
4. **Alert fatigue** - Only alert on actionable conditions
5. **Missing context propagation** - Ensure trace context flows between services

### Example Prompts

- "Add OpenTelemetry tracing to the ships-api service"
- "Create a dashboard for trips-api request latency"
- "Set up alerts for error rate exceeding SLO"
- "Debug slow database queries using traces"
- "Configure log aggregation for the claude namespace"
