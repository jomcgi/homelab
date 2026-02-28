# AGENTS.md - Specialized Agent Definitions

This file defines specialized agents for common tasks in this repository.
Agents duplicated by on-demand skills (`bazelisk`, `helm`, `kubectl`, `signoz`, `gh-pr`, `buildbuddy`) have been removed — use those skills instead.

---

## CRITICAL: All Tests Must Use Bazel

**NEVER run tests directly with `pytest`, `go test`, `vitest`, or `npm test`.** All tests in this repository MUST be run via Bazel:

```bash
bazel test //...                                    # Run all tests
bazel test //services/ships_api:ships_api_test      # Run specific target
bazel test //... --config=ci                        # CI mode (remote caching)
```

**When adding new tests:** create test files, add BUILD.bazel with test targets, use patterns from language-specific sections below.

---

## container

OCI container image building specialist using apko and rules_apko.

### When to Use

- Building container images with apko
- Configuring apko.yaml for new services
- Multi-arch builds (amd64/arm64)
- Distroless/minimal image optimization
- Debugging image build failures
- Lock file management

### Pre-requisite Reading

**Always read first:** `tools/oci/apko_image.bzl` (understand the macro patterns)

### apko.yaml Structure

```yaml
contents:
  repositories:
    - https://packages.wolfi.dev/os
  keyring:
    - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
  packages:
    - ca-certificates-bundle # Always include for HTTPS
    - tzdata # If timezone handling needed

archs:
  - x86_64 # Required: Intel/AMD
  - aarch64 # Required: ARM (M-series Mac, ARM nodes)

entrypoint:
  command: /opt/app # Use for Go binaries

work-dir: /app

# Non-root user (uid 65532 standard, 1000 if writable home needed)
accounts:
  groups:
    - groupname: appuser
      gid: 65532
  users:
    - username: appuser
      uid: 65532
      gid: 65532
  run-as: 65532

paths:
  - path: /app
    type: directory
    uid: 65532
    gid: 65532
    permissions: 0o755

environment:
  HOME: /home/appuser
```

### Key Commands

```bash
# Update lock file after modifying apko.yaml
bazel run @rules_apko//apko -- lock charts/<service>/image/apko.yaml

# Or run format to update ALL apko locks
format

# Build / push / run
bazel build //charts/<service>/image:image
bazel run //charts/<service>/image:image.push
bazel run //charts/<service>/image:image.run
```

### BUILD.bazel Patterns

This repo uses a custom `apko_image` macro from `//tools/oci:apko_image.bzl`:

```starlark
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")
load("//tools/oci:apko_image.bzl", "apko_image")

pkg_tar(
    name = "static_tar",
    srcs = ["//charts/myservice:static_files"],
    mode = "0644",
    owner = "65532.65532",
    package_dir = "/app/static",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@myservice_lock//:contents",
    repository = "ghcr.io/jomcgi/homelab/charts/myservice",
    tars = [":static_tar"],
    # multiarch_tars = [":binary_tar"],  # For arch-specific binaries
)
```

### Multi-arch Binary Pattern (Go)

```starlark
load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")

platform_transition_filegroup(
    name = "binary_amd64",
    srcs = ["//charts/myservice/cmd"],
    target_platform = "@rules_go//go/toolchain:linux_amd64",
)

tar(
    name = "binary_tar_amd64",
    srcs = [":binary_amd64"],
    mtree = ["./opt/app type=file content=$(execpath :binary_amd64)"],
)

# Repeat for arm64 with linux_arm64 target platform

apko_image(
    name = "image",
    config = "apko.yaml",
    contents = "@myservice_lock//:contents",
    multiarch_tars = [":binary_tar"],  # Macro uses _amd64/_arm64 suffixes
    repository = "ghcr.io/jomcgi/homelab/charts/myservice",
)
```

### MODULE.bazel Registration

```starlark
apko = use_extension("@rules_apko//apko:extensions.bzl", "apko")
apko.translate_lock(
    name = "myservice_lock",
    lock = "//charts/myservice/image:apko.lock.json",
)
use_repo(apko, "myservice_lock")
```

### Common Package Categories

| Use Case        | Packages                                   |
| --------------- | ------------------------------------------ |
| HTTPS/TLS       | `ca-certificates-bundle`                   |
| Timezone        | `tzdata`                                   |
| Git operations  | `git`, `openssh-client`                    |
| Node.js runtime | `nodejs-22`, `npm`                         |
| Bun runtime     | `bun`                                      |
| Go binary       | (no packages needed, just entrypoint)      |
| Python runtime  | `python-3.12`                              |
| Native builds   | `build-base`, `python-3.12` (for node-gyp) |
| Debugging       | `busybox`, `curl` (remove for production)  |

### Common Mistakes to Avoid

1. **Not updating lock file** — run `bazel run @rules_apko//apko -- lock <path>` after changing apko.yaml
2. **Missing architectures** — always include both `x86_64` and `aarch64`
3. **Missing CA certificates** — HTTPS calls fail without `ca-certificates-bundle`
4. **Running as root** — always set `run-as` to non-root uid
5. **Forgetting MODULE.bazel** — new locks must be registered with `apko.translate_lock`
6. **Using Dockerfiles** — this repo uses apko exclusively

### Debugging Image Issues

```bash
crane manifest ghcr.io/jomcgi/homelab/charts/myservice:latest | jq
crane export ghcr.io/jomcgi/homelab/charts/myservice:latest - | tar -tvf - | head -50
jq '.contents.packages[] | {name, version}' charts/myservice/image/apko.lock.json
```

---

## golang

Go development specialist, especially for Kubernetes operators and controllers.

### Pre-requisite Reading

**Always read first:** `operators/best-practices.md`

### When to Use

- Building or modifying Kubernetes operators
- Controller-runtime patterns
- CRD development
- Go testing with envtest

### Key Commands

```bash
bazel build //operators/...
bazel test //operators/...
bazel run //:gazelle          # Update BUILD files after adding imports
bazel run //operators/<name>/cmd:cmd
```

### Reconcile Return Values

```go
return ctrl.Result{}, nil                              // Success — do not requeue
return ctrl.Result{RequeueAfter: 30 * time.Second}, nil // Requeue after duration (preferred)
return ctrl.Result{}, err                              // Error — triggers exponential backoff
```

### Common Mistakes to Avoid

- **Reconciling multiple Kinds in one controller** — violates single responsibility
- **Validating CRs in controller** — use ValidatingAdmissionWebhook
- **Using `Requeue: true`** — deprecated; use `RequeueAfter`
- **Returning error on NotFound** — causes infinite retry; return nil
- **Running controller as root** — use minimal RBAC

---

## security

Kubernetes and cloud-native security specialist.

### Pre-requisite Reading

**Always read first:** `architecture/security.md`

### When to Use

- Reviewing code changes for security vulnerabilities
- Auditing container images and dependencies for CVEs
- Configuring Pod Security Standards and Kyverno policies
- Designing RBAC and NetworkPolicy configurations
- Implementing secret management
- Supply chain security (SBOM, image signing)

### Key Commands (Require Global Install)

```bash
trivy image --severity HIGH,CRITICAL <image:tag>     # CVE scanning
trivy k8s --report summary cluster                   # Manifest scanning
checkov -d charts/                                    # Policy scanning
gitleaks detect --source .                            # Secret scanning
cosign sign --key cosign.key <image:tag>              # Image signing
```

### Inspecting Kyverno Policies (This Repo)

```bash
kubectl get clusterpolicies
kubectl describe clusterpolicy inject-linkerd-namespace-annotation
helm template kyverno charts/kyverno/ -s templates/linkerd-injection-policy.yaml
helm template kyverno charts/kyverno/ -s templates/otel-injection-policy.yaml
```

### Pod Security Standards

| Profile      | Use Case               |
| ------------ | ---------------------- |
| `privileged` | System components only |
| `baseline`   | Development/staging    |
| `restricted` | Production workloads   |

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

### Secret Management (This Repo)

This repo uses **1Password Operator**, not External Secrets:

```yaml
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: my-secret
spec:
  itemPath: "vaults/homelab/items/my-secret"
```

### Common Mistakes to Avoid

1. **Running containers as root** — always use `runAsNonRoot: true`
2. **Using `:latest` image tags** — pin to digest or immutable tags
3. **Storing secrets in Git** — use 1Password Operator (OnePasswordItem CRD)
4. **Wildcard RBAC permissions** — specify exact resources and verbs
5. **No NetworkPolicies** — apply default-deny in every namespace

---

## argocd

ArgoCD GitOps specialist. Use the `kubectl` skill for general cluster debugging.

### When to Use

- Configuring sync strategies and retry policies
- Understanding Application.yaml patterns
- Debugging sync failures specific to ArgoCD configuration

### Application.yaml Pattern (This Repo)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <env>-<service> # e.g., prod-trips
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/<chart>
    targetRevision: HEAD
    helm:
      releaseName: <service>
      valueFiles:
        - values.yaml
        - ../../overlays/<env>/<service>/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: <namespace>
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

### Sync Strategies

| Strategy                   | Use Case                            |
| -------------------------- | ----------------------------------- |
| `automated.prune: true`    | Auto-delete removed resources       |
| `automated.selfHeal: true` | Auto-revert kubectl changes         |
| `ServerSideApply: true`    | Large resources, CRDs               |
| `sync-wave` annotation     | Order deployments (lower = earlier) |
| `retry` block              | Handle transient failures           |

### Common Mistakes to Avoid

- **Missing sync waves for dependencies** — CRDs must deploy before resources using them
- **Forgetting ServerSideApply for CRDs** — required for large or complex resources
- **No retry policy** — transient failures cause OutOfSync
- **Wrong valueFiles path** — use `../../overlays/<env>/<service>/values.yaml`

---

## python

Python development specialist with Bazel (aspect_rules_py) integration.

### BUILD.bazel Patterns

This repo uses **@aspect_rules_py** (NOT @rules_python) and references packages via **@pip//package**.

```starlark
load("@aspect_rules_py//py:defs.bzl", "py_library", "py_test")

py_library(
    name = "mylib",
    srcs = ["mylib.py"],
    deps = ["@pip//requests"],
)

py_test(
    name = "mylib_test",
    srcs = ["mylib_test.py"],
    deps = [":mylib", "@pip//pytest"],
)
```

| Pattern        | This Repo (aspect_rules_py)     | Standard rules_python            |
| -------------- | ------------------------------- | -------------------------------- |
| Load statement | `@aspect_rules_py//py:defs.bzl` | `@rules_python//python:defs.bzl` |
| Dependency     | `@pip//requests`                | `requirement("requests")`        |

---

## vite

Vite build tool specialist for the frontend apps in this repo.

### Stack Variations (This Repo)

**Note:** Most websites in this repo use JavaScript, not TypeScript.

| Project          | Stack                          | Language |
| ---------------- | ------------------------------ | -------- |
| trips.jomcgi.dev | Vite + React 19 + Tailwind     | JS       |
| ships.jomcgi.dev | Vite + React 19 + Tailwind     | JS       |
| jomcgi.dev       | Astro + React (not plain Vite) | JS       |

### Key Patterns

- Pre-bundle heavy dependencies with `optimizeDeps.include` (maplibre-gl, three)
- Dev server proxy needs `changeOrigin: true` for CORS and separate WebSocket proxy config
- Use dynamic `import()` for code splitting

---

## reviewer

Code review specialist for PR validation. Use with the `code-review` or `coderabbit` skills.

### Pre-requisite Reading (Context-dependent)

- **Security changes:** `architecture/security.md`
- **New services:** `architecture/contributing.md` + `architecture/services.md`
- **Observability changes:** `architecture/observability.md`

### Checklist by Change Type

**Helm Chart Changes:**

- [ ] `values.yaml` has sensible defaults
- [ ] Templates render: `helm template <release> charts/<chart>/`
- [ ] Resource limits set, health checks configured
- [ ] NetworkPolicy in place

**Operator/Controller Changes:**

- [ ] Single responsibility per controller
- [ ] Proper finalizer cleanup
- [ ] Status conditions updated, RBAC is minimal
- [ ] Reconcile returns correct (see `golang` agent)

**API Changes:**

- [ ] Backward compatible or versioned
- [ ] Input validation present
- [ ] Error responses structured

**GitOps Compliance:**

- [ ] No direct kubectl modifications
- [ ] Helm values follow existing patterns
- [ ] ArgoCD Application uses correct paths

---

## observability

Observability specialist. Use the `signoz` skill for querying logs, traces, and metrics via MCP.

### Pre-requisite Reading

**Always read first:** `architecture/observability.md`

### Auto-Instrumentation (This Repo)

Kyverno policies automatically inject OpenTelemetry instrumentation:

- Pods in labeled namespaces get OTEL sidecars injected
- Check policy: `kubectl describe clusterpolicy inject-otel-instrumentation`

### Key Patterns

- **Dashboard methods:** RED (Rate, Errors, Duration) for services; USE (Utilization, Saturation, Errors) for resources
- **High cardinality:** never use user IDs as metric labels
- **Structured logging:** always include `service`, `trace_id`, `level`, `timestamp`
- **Alerting:** alert on error rates (symptoms), not CPU; always include runbooks

### SigNoz Query Patterns

```sql
service.name = "trips-api" AND severity_text = "ERROR"   -- Logs: errors
duration > 1s AND service.name = "ships-api"              -- Traces: slow requests
```

---

## cloudflare

Cloudflare operator specialist for the custom operator in `operators/cloudflare/`.

### When to Use

- Building or modifying the Cloudflare tunnel operator
- Working with CloudflareTunnel or CloudflareAccessPolicy CRDs
- DNS record management, Zero Trust application configuration
- Debugging tunnel routing or state machine transitions

### Pre-requisite Reading

**Always read first:** `operators/cloudflare/README.md` and `operators/best-practices.md`

### Architecture

The operator manages cluster ingress via Cloudflare tunnels using a state machine pattern:

- **CRDs:** `CloudflareTunnel`, `CloudflareAccessPolicy` (in `api/v1/`)
- **State machine:** `internal/statemachine/` — phases, transitions, status calculation
- **Cloudflare client:** `internal/cloudflare/` — DNS, access policies, routes, tunnel management
- **Controllers:** `internal/controller/` — CloudflareTunnel, CloudflareAccessPolicy, GatewayClass

### Key Directories

```
operators/cloudflare/
├── api/v1/                    # CRD type definitions
├── internal/
│   ├── cloudflare/            # Cloudflare API client (dns, access, routes)
│   ├── controller/            # Reconciliation controllers
│   └── statemachine/          # Tunnel lifecycle state machine
├── helm/                      # Operator Helm chart
├── statemachines/             # State machine diagrams
└── test/e2e/                  # End-to-end tests
```

### Key Commands

```bash
bazel build //operators/cloudflare/...
bazel test //operators/cloudflare/...
bazel run //:gazelle                    # After adding Go imports

# Debug tunnel status
kubectl get cloudflaretunnels -A
kubectl describe cloudflaretunnel <name> -n <namespace>
kubectl get cloudflareaccesspolicies -A
```

### Common Mistakes to Avoid

- **Modifying Cloudflare state directly** — always go through the operator CRDs
- **Ignoring DNS propagation delays** — Cloudflare DNS changes take 2-5 minutes
- **Missing finalizers** — external Cloudflare resources must be cleaned up on CR deletion
- **Not reading the state machine diagrams** — check `statemachines/` before modifying transitions

---

## linkerd

Linkerd service mesh specialist for the mesh running in `cluster-critical`.

### When to Use

- Debugging mTLS or proxy injection issues
- Investigating inter-service connectivity through the mesh
- Configuring proxy log levels or resource tuning
- Understanding traffic routing and service profiles

### Key Configuration (This Repo)

- **Overlay:** `overlays/cluster-critical/linkerd/`
- **Chart:** `charts/linkerd/`
- **Injection:** Kyverno policy `inject-linkerd-namespace-annotation` auto-injects namespaces
- **Priority:** Control plane runs with `system-cluster-critical` priority class
- **Log level:** Set to `warn` to suppress benign connection-closed messages from health checks

### Key Commands

```bash
# Check mesh status
kubectl get pods -n linkerd
kubectl get pods -n linkerd-viz          # If viz extension installed

# Check proxy injection
kubectl get namespace -L linkerd.io/inject
kubectl describe clusterpolicy inject-linkerd-namespace-annotation

# Debug proxy for a specific pod
kubectl logs <pod> -n <namespace> -c linkerd-proxy
kubectl describe pod <pod> -n <namespace> | grep -A5 linkerd

# Check mTLS between services
kubectl get authorizationpolicies -A
kubectl get serverauthorizations -A
```

### Common Issues

| Symptom | Check | Common Cause |
| --- | --- | --- |
| Proxy not injected | `kubectl get ns -L linkerd.io/inject` | Namespace missing annotation |
| Connection refused | Proxy logs + `kubectl get endpoints` | Service not in mesh or port mismatch |
| TLS handshake errors | Proxy logs for both sides | Identity certificate issues |
| High latency through mesh | `kubectl top pods` on proxy containers | Proxy resource limits too low |

### Common Mistakes to Avoid

- **Disabling injection for debugging** — re-enable after; mesh gaps break mTLS
- **Ignoring proxy resource limits** — proxies consume memory; set appropriate limits in values.yaml
- **Not checking both sides** — mesh issues require checking both source and destination proxy logs
- **Bypassing the mesh for "performance"** — the overhead is minimal; breaking mTLS is a security regression
