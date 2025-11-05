# CLAUDE.md - Secure Kubernetes Homelab

## Project Philosophy

> **Complexity is the silent killer of engineering velocity and reliability.**

-- _"A Philosophy of Software Design by John Ousterhout_

Every decision in this codebase prioritizes:
- **Simplicity over cleverness**
- **Security by default**
- **Observable, testable systems**
- **Deep modules with clean interfaces**

## Architecture Overview

This is a **security-first Kubernetes homelab** running K3s, designed for:
- **Zero direct internet exposure** - All ingress via Cloudflare Tunnel
- **Meaningful integration testing** - We test actual deployments, not mocks
- **Operational simplicity** - If it's hard to operate, it's wrong

### Core Infrastructure

```
External Ingress        Applications             Observability
┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
│ Cloudflare      │    │ K3s K8S Cluster   │    │ SigNoz          │
│ Tunnel          │───>│ - Service A       │───>│ - Metrics       │
│ (Zero Trust)    │    │ - Service B       │    │ - Logs          │
└─────────────────┘    └───────────────────┘    │ - Traces        │
                                                └─────────────────┘
```

## Directory Structure

```
charts/                     # Helm charts
├── argocd/                 # ArgoCD GitOps controller
├── argocd-image-updater/   # Automatic image updates for ArgoCD
├── cloudflare-tunnel/      # Cloudflare tunnel chart
├── envoy-gateway/          # Envoy Gateway API implementation
├── freshrss/               # FreshRSS RSS aggregator chart
├── gh-arc-controller/      # GitHub Actions Runner Controller
├── gh-arc-runners/         # GitHub Actions Runners
├── kyverno/                # Policy engine for Kubernetes
├── longhorn/               # Distributed persistent storage
├── n8n/                    # N8N workflow automation
├── n8n-obsidian-api/       # N8N Obsidian API service chart
├── nvidia-gpu-operator/    # NVIDIA GPU operator for GPU workloads
├── signoz/                 # SigNoz observability platform
├── ttyd-session-manager/   # Terminal session manager
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
│   ├── envoy/              # Envoy Gateway deployment
│   ├── kyverno/            # Policy engine
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
│   ├── gh-arc-runners/     # GitHub Actions Runners
│   ├── gh-arc-bazel-runner/# Bazel-specific runner
│   ├── n8n/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   ├── values.yaml
│   │   └── manifests/       # Helm-rendered n8n manifests (for review)
│   │       └── all.yaml
│   └── vllm/               # vLLM inference server
└── dev/                    # Development services
    ├── kustomization.yaml
    ├── cloudflare-operator/# Cloudflare operator deployment
    ├── freshrss/           # RSS feed aggregator
    ├── n8n-obsidian-api/   # N8N Obsidian API service
    └── ttyd-session-manager/# Terminal session manager

pkg/                        # Shared Go libraries
└── n8n/                    # N8N Go client (auto-generated from OpenAPI)

services/                   # Backend services
├── n8n_obsidian_api/       # N8N Obsidian API service
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

#### Envoy Gateway
- **Kubernetes Gateway API** implementation
- **Advanced traffic management** and routing
- **Deployed via**: ArgoCD Application

#### Kyverno
- **Policy engine** for Kubernetes resource validation
- **Security policies** enforced at admission time
- **Mutation and validation** of resources
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
- **Replaces**: Grafana Cloud (fully self-hosted)
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
- **gh-arc-runners**: General-purpose runners for CI/CD
- **gh-arc-bazel-runner**: Specialized runners for Bazel builds
- **Scalable CI/CD** infrastructure within the cluster
- **Deployed via**: ArgoCD Applications

#### N8N Workflow Automation
- **Workflow automation platform** for integrations and automations
- **Workflows managed via UI** with persistence in Longhorn storage
- **Persistent storage** via Longhorn (15Gi)
- **API enabled** for programmatic access
- **Ingress**: `n8n.jomcgi.dev` via Cloudflare Tunnel
- **Deployed via**: ArgoCD Application with Helm chart

#### vLLM Inference Server
- **LLM inference server** for serving large language models
- **GPU-accelerated** via NVIDIA GPU Operator
- **High-throughput inference** with continuous batching
- **Model**: Gemma 3 12B (configurable)
- **Deployed via**: ArgoCD Application

### Development Services

#### Cloudflare Operator
- **Custom Kubernetes operator** for Cloudflare resource management
- **Automated tunnel provisioning** and **DNS management**
- **Deployed via**: ArgoCD Application referencing operators/cloudflare/helm/

#### FreshRSS
- **Self-hosted RSS aggregator** for feed management
- **Web-based interface** for reading feeds
- **Deployed via**: ArgoCD Application

#### N8N Obsidian API
- **API service** for N8N integration with Obsidian
- **Custom Go service** for note automation
- **Deployed via**: ArgoCD Application

#### ttyd Session Manager
- **Terminal session manager** for web-based terminal access
- **Secure terminal access** via browser
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