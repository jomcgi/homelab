# CLAUDE.md - Secure Kubernetes Homelab

## Project Philosophy

> **Complexity is the silent killer of engineering velocity and reliability.**

-- _"A Philosophy of Software Design by John Ousterhout_

Every decision in this codebase prioritizes:
- **Simplicity over cleverness**
- **Security by default**
- **Observable, testable systems**
- **Deep modules with clean interfaces**

## CRITICAL: Use OpenCode for Token-Heavy Tasks

**You MUST use `opencode run` instead of doing work yourself for these task types:**

| Task Type | Command |
|-----------|---------|
| Research across many files | `opencode run --agent cheap-local-tokens "<prompt>" -f "src/**/*.ts"` |
| Generate boilerplate/tests | `opencode run --agent cheap-local-tokens "<prompt>" -f <file>` |
| Summarize documents/code | `opencode run --agent cheap-local-tokens "<prompt>"` |
| Analyze 100+ files at once | `opencode run --agent long-context-window-tasks "<prompt>"` |

**Why:** Qwen3-Coder runs locally on the cluster GPU - it's FREE. Using Claude tokens for bulk work wastes money.

**When to use Claude (yourself) instead:**
- Quick questions about current conversation context
- Complex multi-step reasoning requiring judgment
- Tasks that need your tool access (file editing, kubectl, etc.)

See `.claude/skills/opencode/SKILL.md` for full documentation.

## Architecture Overview

This is a **security-first Kubernetes homelab** running K3s, designed for:
- **Zero direct internet exposure** - All ingress via Cloudflare Tunnel
- **Meaningful integration testing** - We test actual deployments, not mocks
- **Operational simplicity** - If it's hard to operate, it's wrong

### Core Infrastructure

```
External Ingress        Service Mesh              Observability
┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
│ Cloudflare      │    │ Linkerd Mesh      │    │ SigNoz          │
│ Tunnel          │───>│ - Auto tracing    │───>│ - Metrics       │
│ (Zero Trust)    │    │ - mTLS            │    │ - Logs          │
│ + Gateway API   │    │ - All pod-to-pod  │    │ - Traces        │
└─────────────────┘    └───────────────────┘    └─────────────────┘
```

**Traffic Flow:**
1. **Internet → Cloudflare Tunnel** - TLS termination, DDoS protection
2. **Tunnel Pod → Services** - Gateway API routing (via Cloudflare Operator)
3. **Service → Pods** - Automatically meshed by Linkerd
4. **Pod ↔ Pod** - All traffic traced and exported to SigNoz

**Key Design:** After Cloudflare Tunnel terminates external traffic, ALL communication is pod-to-pod within the cluster. Linkerd automatically meshes this traffic for complete observability.

## Directory Structure

```
charts/                     # Helm charts
├── api-gateway/            # API Gateway for external service routing
├── argocd/                 # ArgoCD GitOps controller
├── argocd-image-updater/   # Automatic image updates for ArgoCD
├── cert-manager/           # X.509 certificate management
├── claude/                 # Claude Code deployment
├── cloudflare-tunnel/      # Cloudflare tunnel chart
├── coredns/                # CoreDNS for internal DNS resolution
├── gh-arc-controller/      # GitHub Actions Runner Controller
├── gh-arc-runners/         # GitHub Actions Runners
├── kyverno/                # Policy engine for Kubernetes
├── linkerd/                # Linkerd service mesh for automatic tracing
├── longhorn/               # Distributed persistent storage
├── nats/                   # NATS messaging system
├── nvidia-gpu-operator/    # NVIDIA GPU operator for GPU workloads
├── seaweedfs/              # SeaweedFS distributed storage
├── signoz/                 # SigNoz observability platform
├── stargazer/              # Stargazer service
├── trips/                  # Trips management service
└── vllm/                   # vLLM inference server for LLMs

clusters/                   # Cluster entry points
└── homelab/                # Production cluster
    └── kustomization.yaml  # References overlays (dev, prod, cluster-critical)

operators/                  # Custom Kubernetes operators
└── cloudflare/             # Cloudflare operator
    ├── helm/               # Operator Helm chart
    └── README.md           # Operator documentation

overlays/                   # Environment-based deployments
├── cluster-critical/       # Critical infrastructure
│   ├── kustomization.yaml
│   ├── argocd/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── argocd-image-updater/
│   ├── cert-manager/       # Certificate management (required for Linkerd)
│   ├── coredns/            # CoreDNS for cluster DNS
│   ├── kyverno/            # Policy engine
│   ├── linkerd/            # Linkerd service mesh
│   ├── longhorn/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── nvidia-gpu-operator/
│   └── signoz/             # SigNoz observability stack
├── prod/                   # Production services
│   ├── kustomization.yaml
│   ├── cloudflare-tunnel/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── gh-arc-controller/  # GitHub Actions Runner Controller
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── gh-arc-runners/     # GitHub Actions Runners with persistent cache
│   ├── api-gateway/        # API Gateway service
│   ├── nats/               # NATS messaging system
│   ├── seaweedfs/          # SeaweedFS distributed storage
│   ├── trips/              # Trips management service
│   └── vllm/               # vLLM inference server
└── dev/                    # Development services
    ├── kustomization.yaml
    ├── claude/             # Claude Code deployment
    ├── cloudflare-operator/# Cloudflare operator deployment
    └── stargazer/          # Stargazer service

pkg/                        # Shared Go libraries

services/                   # Backend services
└── hikes/                  # Hikes data scraping and processing
    ├── scrape_walkhighlands/
    └── update_forecast/

websites/                   # Static websites
├── hikes.jomcgi.dev/       # Hiking route finder (static)
└── jomcgi.dev/             # Personal website (Astro-based)

```

## Security Model

### Network Security
- **No direct internet exposure** - All traffic via Cloudflare Tunnel
- **Least privilege** - Services run as non-root with read-only filesystems
- **Network policies** - Microsegmentation where needed
- **Secret management** - 1Password operator with OnePasswordItem CRDs

### Container Security
Every container follows these principles:
```yaml
securityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

## Deployment Strategy

### GitOps with ArgoCD
- **Declarative deployments** via Helm charts and Kustomize overlays
- **Automated sync** with ArgoCD Applications pointing to Git repository
- **Self-healing** deployments with automatic drift detection
- **Health checks** and **readiness probes** on everything
- **Resource limits** prevent resource exhaustion

**Application Discovery Pattern:**
Services are organized by environment in `overlays/<env>/<service>/`:
- `application.yaml` - ArgoCD Application manifest pointing to the Helm chart
- `kustomization.yaml` - Makes the application discoverable by ArgoCD
- `values.yaml` - Environment-specific Helm value overrides

ArgoCD automatically discovers and deploys applications by syncing `clusters/homelab/kustomization.yaml`,
which references environment overlays (cluster-critical, prod, dev). Each overlay's kustomization.yaml
lists the services in that environment.

### Testing Philosophy
We test **actual behavior**, not implementation details:

✅ **Good Tests:**
- Deploy the actual service to a test cluster
- Verify the service responds correctly via HTTP
- Confirm metrics are exported and observable
- Test the complete user journey

❌ **Bad Tests:**
- Unit tests that mock everything
- Tests that verify internal implementation
- Tests that don't exercise real deployment paths

## Key Services

### Core Infrastructure (cluster-critical)

#### ArgoCD
- **GitOps controller** for declarative cluster management
- **Self-healing deployments** with automatic drift detection
- **Application discovery** via Kustomize overlays
- **Deployed via**: ArgoCD Application (bootstrapped)

#### ArgoCD Image Updater
- **Automatic image updates** for ArgoCD-managed applications
- **Git-based workflow** for version tracking
- **Deployed via**: ArgoCD Application

#### cert-manager
- **X.509 certificate management** for Kubernetes
- **Automatic certificate generation** for Linkerd trust anchor
- **Certificate rotation** with automatic renewal
- **Required by**: Linkerd (generates mTLS certificates)
- **Deployed via**: ArgoCD Application

#### CoreDNS
- **Cluster DNS resolution** for Kubernetes services
- **Custom DNS zones** for internal domain resolution
- **Service discovery** via Kubernetes DNS
- **Deployed via**: ArgoCD Application

#### Linkerd Service Mesh
- **Automatic distributed tracing** for all pod-to-pod traffic
- **Mutual TLS** between all services
- **OTEL trace export** to SigNoz
- **Zero-config observability** - just annotate namespaces
- **Lightweight** - smallest resource footprint of any service mesh
- **Deployed via**: ArgoCD Application

#### Kyverno
- **Policy engine** for Kubernetes resource validation
- **Security policies** enforced at admission time
- **Mutation and validation** of resources
- **Automatic OTEL injection** - All workloads get OTEL env vars for tracing
- **Automatic Linkerd injection** - All namespaces get meshed by default
- **Observable by default** - Opt-out if needed
- **Deployed via**: ArgoCD Application

#### Longhorn Storage
- **Distributed persistent storage** for Kubernetes
- **Automated backups** and **disaster recovery**
- **High availability** with replica management
- **Deployed via**: ArgoCD Application

#### NVIDIA GPU Operator
- **GPU support** for Kubernetes workloads
- **Automatic driver installation** and device plugin management
- **Required for**: vLLM inference workloads
- **Deployed via**: ArgoCD Application

#### SigNoz Observability Platform
- **Self-hosted observability** - metrics, logs, traces
- **OpenTelemetry-native** with ClickHouse backend
- **Unified observability** for all cluster services
- **Deployed via**: ArgoCD Application

#### 1Password Operator
- **Secret management** via OnePasswordItem CRDs
- **Secure credential storage** in 1Password vaults
- **Automatic secret synchronization** to Kubernetes secrets
- **Bootstrapped manually** during cluster setup

### Production Services

#### Cloudflare Tunnel
- **Zero Trust ingress** - No open firewall ports
- **Automatic HTTPS** with Cloudflare certificates
- **DDoS protection** and **WAF** built-in
- **Deployed via**: ArgoCD Application with Helm chart

#### GitHub Actions Self-Hosted Runners
- **gh-arc-controller**: Actions Runner Controller for managing runner lifecycle
- **gh-arc-runners**: Self-hosted runners with Docker-in-Docker and persistent cache for builds
- **Scalable CI/CD** infrastructure within the cluster (1-10 runners)
- **Deployed via**: ArgoCD Applications

#### API Gateway
- **External service routing** with advanced traffic management
- **Rate limiting** and **authentication** for APIs
- **Protocol translation** and **request transformation**
- **Deployed via**: ArgoCD Application

#### NATS
- **High-performance messaging system** for microservices
- **Pub/sub messaging** and **request-reply patterns**
- **Persistent streams** with JetStream
- **Deployed via**: ArgoCD Application

#### SeaweedFS
- **Distributed object storage** system
- **S3-compatible API** for application integration
- **High-performance** blob storage
- **Deployed via**: ArgoCD Application

#### Trips
- **Trip management service** for travel planning
- **Integration with mapping** and **weather services**
- **Data persistence** via Longhorn
- **Deployed via**: ArgoCD Application

#### vLLM Inference Server
- **LLM inference server** for serving large language models
- **GPU-accelerated** via NVIDIA GPU Operator
- **High-throughput inference** with continuous batching
- **Model**: Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit (30B coding model, 4-bit quantized)
- **Context window**: 24k tokens (24,576)
- **Features**: Function calling enabled for OpenCode integration
- **Deployed via**: ArgoCD Application

### Development Services

#### Claude
- **Claude Code deployment** for AI-assisted development
- **Integrated with cluster services** for development workflows
- **Deployed via**: ArgoCD Application

#### Cloudflare Operator
- **Custom Kubernetes operator** for Cloudflare resource management
- **Automated tunnel provisioning** and **DNS management**
- **Deployed via**: ArgoCD Application referencing operators/cloudflare/helm/

#### Stargazer
- **Experimental service** for testing new features
- **Development sandbox** environment
- **Deployed via**: ArgoCD Application

### Static Websites

#### Personal Website (jomcgi.dev)
- **Astro-based static site** for personal content
- **Hosted on Cloudflare Pages** with automatic deployments
- **Fast and modern** web framework

#### Hikes Route Finder (hikes.jomcgi.dev)
- **Pure static site** hosted on Cloudflare Pages
- **Cloudflare R2 backend** for data storage
- **No server-side dependencies** - maximum simplicity
- **Comprehensive Playwright testing** for reliability

## Design Principles

### 1. Deep Modules
Services have **simple interfaces** that hide **complex implementations**:
- Cloudflare Tunnel: Simple config → Complex networking
- External Secrets: Simple CRD → Complex secret synchronization
- Longhorn: Simple PVC → Complex distributed storage

### 2. Obvious Code
- **Descriptive names** over clever abbreviations
- **Clear configuration** over implicit behavior
- **Explicit dependencies** in manifests

### 3. Error Handling
We **define errors out of existence** where possible:
- Idempotent deployments (apply the same config multiple times safely)
- Graceful degradation (services work without optional dependencies)
- Automatic retries with exponential backoff

## Common Tasks

### CLI Tools
- **Directory tree viewer**: Use `lstr -L <depth> <path>` instead of `tree`. `lstr` is a fast Rust-based tree viewer.
  - Example: `lstr -L 2 charts/` to view 2 levels deep
  - Use `-d` for directories only, `--icons` for file icons

### Rendering Manifests

To render Helm manifests and verify changes before committing:

```bash
format
```

This command:
- **Renders all Helm charts** to `overlays/<env>/<service>/manifests/all.yaml`
- **Validates apko configurations** (container image definitions)
- **Formats code** (Go, Python, JavaScript, Shell, etc.)
- **Runs in parallel** using Bazel for fast builds
- **Caches results** for incremental builds

**When to use:**
- After modifying Helm chart templates or values
- Before committing changes (to verify manifests render correctly)
- To debug ArgoCD sync issues (compare rendered vs. deployed manifests)

**What gets rendered:**
- All services in `overlays/cluster-critical/`, `overlays/prod/`, and `overlays/dev/`
- Output saved to `<service>/manifests/all.yaml` for each service
- Manifests are committed to Git for transparency and review

**Example workflow:**
1. Modify chart values: `overlays/prod/n8n/values.yaml`
2. Run `format` to render manifests
3. Review changes: `git diff overlays/prod/n8n/manifests/all.yaml`
4. Commit and push - ArgoCD auto-syncs the changes

### Kubernetes Operations (kubectl)

**CRITICAL: This cluster is managed via GitOps. kubectl is READ-ONLY except for specific cases.**

#### GitOps-Only Modifications
- **NEVER use `kubectl patch`** to modify resources
- **NEVER use `kubectl edit`** to modify resources
- **NEVER use `kubectl apply`** to modify resources directly
- **ALL modifications** must go through Git → ArgoCD workflow

**Why?** Direct modifications create configuration drift between Git (source of truth) and cluster (runtime state). ArgoCD will either:
- Revert your changes (if auto-sync is enabled)
- Show your cluster as "OutOfSync" indefinitely

#### Acceptable kubectl Usage

✅ **Read-only operations** (always safe):
```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
kubectl top pods -n <namespace>
kubectl get events -n <namespace>
```

✅ **Triggering jobs** (idempotent operations):
```bash
kubectl create job --from=cronjob/<name> <job-name> -n <namespace>
```

✅ **Port forwarding** for debugging:
```bash
kubectl port-forward svc/<service-name> 8080:80 -n <namespace>
```

✅ **Temporary debugging pods** (will be cleaned up):
```bash
kubectl run debug --image=busybox --rm -it -- sh
```

❌ **FORBIDDEN operations**:
```bash
kubectl patch deployment ...    # NO - modify Git instead
kubectl edit configmap ...       # NO - modify Git instead
kubectl scale deployment ...     # NO - modify Git instead
kubectl set image ...            # NO - modify Git instead
kubectl delete deployment ...    # NO - remove from Git instead
```

#### How to Make Changes (GitOps Workflow)
1. **Modify** the appropriate files in Git:
   - Helm chart values: `overlays/<env>/<service>/values.yaml`
   - Chart templates: `charts/<service>/templates/`
   - ArgoCD config: `overlays/<env>/<service>/application.yaml`
2. **Commit and push** to Git
3. **Wait for ArgoCD auto-sync** (5-10 seconds)
4. **Verify** the change with read-only kubectl commands

**Note:** Do NOT manually trigger ArgoCD sync with kubectl or the ArgoCD CLI. Auto-sync is fast enough and prevents unnecessary intervention.

**Exception:** Emergency repairs during outages may require direct kubectl operations, but these MUST be followed by a Git commit to restore GitOps consistency.

### Adding a New Service
1. Create Helm chart in `charts/<name>/` with default values
2. Choose the appropriate overlay environment:
   - `overlays/cluster-critical/` - Core infrastructure (argocd, longhorn, monitoring)
   - `overlays/prod/` - Production services
   - `overlays/dev/` - Development/experimental services
3. Create service directory in `overlays/<env>/<name>/` with:
   - `application.yaml` - ArgoCD Application pointing to your chart
     ```yaml
     valueFiles:
       - values.yaml  # Chart defaults
       - ../../overlays/<env>/<name>/values.yaml  # Environment overrides
     ```
   - `kustomization.yaml` - Reference to application.yaml
   - `values.yaml` - Environment-specific Helm value overrides
4. Add the service to `overlays/<env>/kustomization.yaml` resources list
5. Add health checks and observability to the chart
6. Test the complete deployment path:
   - `helm template <service> charts/<service>/ --namespace <namespace>` to verify rendering
   - Commit and push to Git
   - ArgoCD automatically discovers and syncs the new application to the cluster

### Security Review Checklist
- [ ] Service runs as non-root user
- [ ] Read-only root filesystem
- [ ] No privilege escalation
- [ ] Resource limits defined
- [ ] Network policies applied (if needed)
- [ ] Secrets managed via 1Password OnePasswordItem CRDs
- [ ] Ingress via Cloudflare Tunnel only

### Observability Requirements
Every service must:
- [ ] Export Prometheus metrics on `/metrics`
- [ ] Provide health check endpoint
- [ ] Send structured logs
- [ ] Include OpenTelemetry tracing (for user-facing services)

#### Automatic Observability (Kyverno)

**Two-layer automatic observability** via Kyverno policies:

**1. OTEL Environment Variables (Application-Level)**
- **All workloads** receive OTEL env vars automatically
- `OTEL_EXPORTER_OTLP_ENDPOINT` → SigNoz collector
- `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`
- Applications with OTEL SDKs get automatic instrumentation
- Applications without OTEL SDKs ignore the vars (harmless)
- **Policy:** `charts/kyverno/templates/otel-injection-policy.yaml`

**2. Linkerd Namespace Annotation (Infrastructure-Level)**
- **All namespaces** automatically get `linkerd.io/inject=enabled`
- Linkerd webhook injects sidecars into all pods
- Captures ALL HTTP/HTTPS traffic (no SDK needed!)
- Automatic distributed tracing for everything
- **Policy:** `charts/kyverno/templates/linkerd-injection-policy.yaml`

**Observable by Default Philosophy:**
- New deployments → Get OTEL env vars + Linkerd sidecar
- Existing deployments → Get annotations/vars via background policies
- **Opt-out if needed** (see below)

**To opt-out of OTEL injection:**
```yaml
metadata:
  labels:
    otel.instrumentation: "disabled"
```

**To opt-out of Linkerd injection:**
```yaml
# Namespace level
apiVersion: v1
kind: Namespace
metadata:
  name: my-namespace
  labels:
    linkerd.io/inject: "disabled"
```

**Configuration:**
- OTEL: `charts/kyverno/values.yaml` (otelInjection section)
- Linkerd: `charts/kyverno/values.yaml` (linkerdInjection section)

**Excluded namespaces (both policies):**
- System: kube-system, kube-public, kube-node-lease
- Infrastructure: linkerd, cert-manager, kyverno, argocd, longhorn-system, signoz

## Development Workflow

1. **Make changes** in feature branch
2. **Test locally**
3. **Verify deployment** works end-to-end in local environment
4. **Check observability** - metrics, logs, traces (when available)
5. **Create PR** - GitHub Actions runs integration tests
6. **Merge** - ArgoCD automatically syncs changes to production cluster

## Anti-Patterns to Avoid

### Complexity Sources
- **Cargo-culting** Kubernetes best practices without understanding why
- **Over-engineering** simple services
- **Premature optimization** before measuring
- **Magic configuration** that's hard to understand

### Security Anti-Patterns
- **Default passwords** or weak secrets
- **Running as root** unnecessarily
- **Overprivileged** service accounts
- **Direct internet exposure** bypassing Cloudflare

## Why This Design Works

This architecture prioritizes **operational simplicity**:
- **Fewer moving parts** = fewer failure modes
- **Clear interfaces** = easier troubleshooting
- **Secure by default** = less security debt
- **Observable everything** = faster incident resolution

The result is a homelab that's **easy to operate**, **secure by design**, and **simple to extend** with new services.

---

*"The best software is software that just works, without you having to think about it."*