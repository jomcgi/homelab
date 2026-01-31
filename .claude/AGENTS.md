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

Kubernetes debugging specialist for troubleshooting specific known issues.

### When to Use

- Pod stuck in CrashLoopBackOff, Pending, or Error
- OOMKilled or resource exhaustion
- Service connectivity failures
- Investigating specific pod/deployment issues

### Investigation Workflow

1. **Check pod status and events**
   ```bash
   kubectl get pods -n <namespace>
   kubectl describe pod <pod-name> -n <namespace>
   kubectl get events -n <namespace> --field-selector involvedObject.name=<pod-name>
   ```

2. **Examine logs (including previous crashes)**
   ```bash
   kubectl logs <pod-name> -n <namespace>
   kubectl logs <pod-name> -n <namespace> --previous  # Critical for CrashLoopBackOff
   ```

3. **Check resource usage**
   ```bash
   kubectl top pods -n <namespace>
   ```

### Common Issues

| Symptom | Check | Common Cause |
|---------|-------|--------------|
| CrashLoopBackOff | `kubectl logs --previous` | App error, missing config |
| OOMKilled (137) | `kubectl top pods` | Memory limit too low |
| ImagePullBackOff | `kubectl describe pod` | Wrong image, missing creds |
| Pending | `kubectl describe pod` | Insufficient resources |

### Common Mistakes to Avoid

- **Restarting pods before investigating** - Find root cause first
- **Only checking current logs** - Use `--previous` for crash debugging
- **Editing resources directly** - In GitOps, modify Git instead

### Example Prompts

- "Pod nginx-abc123 is in CrashLoopBackOff, help me debug"
- "Service frontend can't connect to backend service"
- "Pods keep getting OOMKilled, how do I investigate?"

---

## cluster-health

Proactive cluster health assessment and discovery specialist.

### When to Use

- Routine cluster health checks
- Finding unknown problems before they cause incidents
- Pre-deployment validation
- Capacity planning and resource auditing
- Certificate and secret expiration checks

### Health Check Commands

```bash
# Find all non-running pods across cluster
kubectl get pods -A | grep -v Running | grep -v Completed

# Recent warning events (last hour)
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | head -50

# ArgoCD sync status - find out-of-sync apps
argocd app list -o wide | grep -v Synced

# Node health and pressure conditions
kubectl get nodes
kubectl describe nodes | grep -A5 "Conditions:"
kubectl top nodes

# Resource usage hotspots
kubectl top pods -A --sort-by=memory | head -20
kubectl top pods -A --sort-by=cpu | head -20

# PVC issues
kubectl get pvc -A | grep -v Bound

# Certificate expiration (cert-manager)
kubectl get certificates -A
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: {.status.notAfter}{"\n"}{end}'

# Pods with high restart counts
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: {.status.containerStatuses[0].restartCount}{"\n"}{end}' | awk -F: '$2 > 5'
```

### Health Assessment Checklist

- [ ] All pods Running/Completed (no CrashLoopBackOff, Pending, Error)
- [ ] No Warning events in last hour
- [ ] All ArgoCD applications Synced and Healthy
- [ ] Node CPU/memory below 80% utilization
- [ ] No PVCs stuck in Pending
- [ ] Certificates not expiring within 30 days
- [ ] No pods with excessive restarts (>5)

### Common Patterns

**Daily health check script:**
```bash
echo "=== Pod Issues ==="
kubectl get pods -A | grep -v Running | grep -v Completed

echo "=== Recent Warnings ==="
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -10

echo "=== ArgoCD Status ==="
argocd app list | grep -v Synced

echo "=== Node Resources ==="
kubectl top nodes
```

### Example Prompts

- "Run a health check across all namespaces"
- "Find all pods that have restarted more than 3 times"
- "Check for certificates expiring in the next 14 days"
- "Identify resource usage hotspots in the cluster"
- "What ArgoCD applications are out of sync?"

---

## qa-test

Quality assurance and hermetic testing specialist.

### When to Use

- Designing test strategies
- Investigating flaky tests
- Setting up hermetic test environments
- Configuring Bazel test caching
- Parallel test execution in CI

### Test Size Classification

| Size | Scope | Timeout | Constraints |
|------|-------|---------|-------------|
| Small | Single function | 1 min | No I/O, no network |
| Medium | Multiple classes | 5 min | Localhost only |
| Large | Cross-service | 15 min | Real network |

### Hermetic Testing Principles

- Tests must be deterministic
- No dependencies on external services
- All test data created within test or fixtures
- Tests can run in any order

### Flaky Test Detection

```bash
bazel test --runs_per_test=20 --cache_test_results=no //path:target
```

### Common Mistakes to Avoid

- Testing implementation, not behavior
- Shared mutable state between tests
- Time-dependent tests without mocking
- Order-dependent tests
- Caching non-hermetic tests

### Example Prompts

- "Set up hermetic testing for the new payment service"
- "Investigate why test_order_processing is flaky in CI"
- "Design test data factories for the user domain"

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

## dev-ux

Developer experience and CLI/API usability specialist.

### When to Use

- Evaluating CLI interfaces
- Reviewing error messages
- Assessing help documentation
- Auditing terminal accessibility
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

## frontend-ux

User-facing web application UX and accessibility specialist.

### When to Use

- Reviewing UI components for accessibility compliance
- Evaluating form designs and validation patterns
- Auditing responsive design and mobile-first implementations
- Checking color contrast, typography, and spacing
- Reviewing user flows and navigation patterns
- Assessing Core Web Vitals performance impact

### Accessibility (WCAG 2.2)

| Requirement | Standard |
|-------------|----------|
| Color contrast (text) | 4.5:1 minimum (AA) |
| Color contrast (large text) | 3:1 minimum |
| Touch targets | 44x44px minimum |
| Focus indicators | Visible, sufficient contrast |

### Form Design Best Practices

- Single-column layout reduces cognitive load
- Validate on blur, not while typing
- Specific error messages ("Password must be 8+ characters" not "Invalid")
- Never use placeholder-only labels
- Preserve user input when one field has an error

### Core Web Vitals

| Metric | Target | Impact |
|--------|--------|--------|
| LCP | < 2.5s | Largest Contentful Paint |
| INP | < 200ms | Interaction to Next Paint |
| CLS | < 0.1 | Cumulative Layout Shift |

### Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| Low contrast text | Use contrast checker; 4.5:1 minimum |
| Small touch targets | Minimum 44x44px |
| Placeholder-only labels | Always use visible, persistent labels |
| Validating while typing | Validate on blur or submit |
| Color-only error states | Combine color with icons and text |
| Layout shift on load | Reserve space for dynamic content |

### Example Prompts

- "Review this component for WCAG 2.2 AA compliance"
- "Evaluate this form's validation UX"
- "Check this page for Core Web Vitals issues"
- "Audit responsive behavior at mobile breakpoints"

---

## security

Kubernetes and cloud-native security specialist.

### When to Use

- Reviewing code changes for security vulnerabilities
- Auditing container images and dependencies for CVEs
- Configuring Pod Security Standards and Kyverno policies
- Designing RBAC and NetworkPolicy configurations
- Implementing secret management
- Supply chain security (SBOM, image signing)

### Pre-requisite Reading

**Always read first:** `architecture/security.md`

### Key Commands

```bash
# Container image scanning
trivy image <image:tag>
trivy image --severity HIGH,CRITICAL <image:tag>

# Kubernetes manifest scanning
trivy k8s --report summary cluster
checkov -d charts/

# Secret scanning
gitleaks detect --source .

# SBOM generation
trivy image --format spdx-json -o sbom.json <image:tag>

# Image signing
cosign sign --key cosign.key <image:tag>
cosign verify --key cosign.pub <image:tag>
```

### Pod Security Standards

```yaml
# Apply via namespace labels
metadata:
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

| Profile | Use Case |
|---------|----------|
| `privileged` | System components only |
| `baseline` | Development/staging |
| `restricted` | Production workloads |

### Secure Pod SecurityContext

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
```

### NetworkPolicy Pattern (Default Deny)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

### Common Mistakes to Avoid

1. **Running containers as root** - Always use `runAsNonRoot: true`
2. **Using `:latest` image tags** - Pin to digest or immutable tags
3. **Storing secrets in Git** - Use External Secrets Operator
4. **Wildcard RBAC permissions** - Specify exact resources and verbs
5. **No NetworkPolicies** - Apply default-deny in every namespace
6. **Missing resource limits** - Enables DoS via resource exhaustion

### Example Prompts

- "Review this PR for security vulnerabilities"
- "Scan the trips-api container image for CVEs"
- "Create a NetworkPolicy for the database namespace"
- "Audit RBAC permissions for the monitoring service account"
- "Set up image signing with Cosign in CI"

---

## pr-manager

Pull request lifecycle manager. A task is not complete until CI passes and PR is ready to merge.

### When to Use

- Creating and managing pull requests
- Monitoring CI status (BuildBuddy)
- Debugging CI failures
- Ensuring PRs meet merge criteria
- Reproducing CI failures locally

### PR Lifecycle

```
Code complete → Create PR → CI runs → Fix failures → CI green → Ready for review → Merge
```

**A task is ONLY complete when CI is green.**

### Creating PRs

```bash
# Create PR with proper description
gh pr create --title "feat: add X" --body "## Summary\n- Change 1\n- Change 2"

# Check PR status
gh pr status
gh pr checks

# View CI details
gh pr checks --watch
```

### CI Pipeline

```
git push → GitHub Actions → BuildBuddy (build + test) → PR status check
```

### Monitoring CI

```bash
# Watch CI status
gh pr checks --watch

# Get BuildBuddy invocation URL from checks
gh pr checks | grep buildbuddy

# Open BuildBuddy UI for detailed logs
# URL format: https://app.buildbuddy.io/invocation/<id>
```

### Reproducing CI Failures Locally

```bash
# Run with CI config
bazelisk test //... --config=ci

# Run specific failing target
bazelisk test //path:failing_target --config=ci

# Force no-cache to match fresh CI run
bazelisk test //path:target --cache_test_results=no

# Full clean rebuild
bazelisk clean --expunge && bazelisk test //...
```

### Common CI Failures

| Issue | Cause | Fix |
|-------|-------|-----|
| Passes locally, fails CI | Non-hermetic test | Remove hardcoded paths, timestamps, env vars |
| Flaky test | Race condition | Add synchronization, use `--runs_per_test=10` to verify |
| Missing dependency | Implicit dep | Add explicit dep to BUILD file |
| Timeout | Slow test | Optimize or increase timeout |
| Format check | Uncommitted format | Run `format` and commit |

### Merge Criteria Checklist

- [ ] All CI checks passing (green checkmark)
- [ ] No merge conflicts
- [ ] PR description complete
- [ ] Changes match PR scope (no unrelated changes)

### Common Mistakes to Avoid

1. **Declaring done before CI passes** - Always wait for green
2. **Ignoring flaky tests** - Fix them, don't re-run until green
3. **Not checking BuildBuddy logs** - Contains detailed failure info
4. **Pushing without local test** - Run `bazelisk test //...` first
5. **Large PRs** - Smaller PRs are easier to review and debug

### Example Prompts

- "Create a PR for my changes"
- "CI is failing, help me debug"
- "Check if my PR is ready to merge"
- "Reproduce the BuildBuddy failure locally"
- "Why is this test flaky in CI?"

---

## observability

Observability specialist for metrics, traces, logs, and alerting.

### When to Use

- Instrumenting services with OpenTelemetry
- Setting up structured logging
- Creating dashboards (RED/USE methods)
- Configuring alerts with runbooks
- Implementing SLOs and error budgets
- Debugging distributed tracing issues

### Pre-requisite Reading

**Always read first:** `architecture/observability.md`

### Dashboard Methods

- **RED** (services): Rate, Errors, Duration
- **USE** (resources): Utilization, Saturation, Errors

### Structured Logging

```json
{
  "timestamp": "2025-01-31T12:00:00Z",
  "level": "ERROR",
  "service": "trips-api",
  "trace_id": "abc123",
  "message": "Database connection timeout",
  "duration_ms": 5000
}
```

### OpenTelemetry Instrumentation (Go)

```go
tracer := otel.Tracer("myservice")
ctx, span := tracer.Start(ctx, "ProcessOrder")
defer span.End()

span.SetAttributes(
    attribute.String("order.id", orderID),
)
```

### SLO-Based Alerting

```yaml
# Burn rate alert - consuming error budget too fast
alert: HighErrorBudgetBurn
expr: |
  sli:request_success_rate:ratio_rate1h < 0.99
for: 2m
labels:
  severity: critical
annotations:
  runbook: https://runbooks.example.com/high-error-rate
```

### Runbook Template

```markdown
# Alert: HighErrorRate

## Impact
Users experiencing failed requests

## Investigation
1. Check traces: `status.code = ERROR AND service.name = "affected-service"`
2. Check recent deployments: `argocd app history <app>`

## Mitigation
1. If recent deploy: Roll back via Git revert
2. If dependency: Check upstream service health
```

### SigNoz Query Patterns

```sql
-- Logs: Errors in last hour
service.name = "trips-api" AND severity_text = "ERROR"

-- Traces: Slow requests
duration > 1s AND service.name = "ships-api"
```

### Common Mistakes to Avoid

1. **High cardinality labels** - Never use user IDs as metric labels
2. **Missing service.name** - Required for trace correlation
3. **No sampling strategy** - Sample high-volume traces
4. **Alert on symptoms, not causes** - Alert on error rate, not CPU
5. **Missing runbooks** - Alerts without runbooks increase MTTR

### Example Prompts

- "Add OpenTelemetry tracing to the ships-api service"
- "Create an SLO dashboard for trips-api"
- "Set up burn-rate alerting for the payment service"
- "Debug why traces are fragmented between services"
- "Configure structured logging for the Python service"
