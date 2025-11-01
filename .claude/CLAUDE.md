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

This is a **security-first Kubernetes homelab** running on Talos Linux, designed for:
- **Zero direct internet exposure** - All ingress via Cloudflare Tunnel
- **Meaningful integration testing** - We test actual deployments, not mocks
- **Operational simplicity** - If it's hard to operate, it's wrong

### Core Infrastructure

```
External Ingress        Applications             Observability
┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
│ Cloudflare      │    │ Talos K8S Cluster │    │ Grafana Cloud   │
│ Tunnel          │───>│ - Service A       │───>│ - Metrics       │
│ (Zero Trust)    │    │ - Service B       │    │ - Logs          │
└─────────────────┘    └───────────────────┘    │ - Traces        │
                                                └─────────────────┘
```

## Directory Structure

```
charts/                     # Helm charts
├── cloudflare-tunnel/      # Cloudflare tunnel chart
├── n8n/                    # N8N wrapper chart (wraps upstream n8n chart)
├── n8n-obsidian-api/       # N8N Obsidian API service chart
└── freshrss/               # FreshRSS RSS aggregator chart

clusters/                   # Cluster entry points
└── homelab/                # Production cluster
    └── kustomization.yaml  # References overlays (dev, prod, cluster-critical)

operators/                  # Custom Kubernetes operators
└── cloudflare/             # Cloudflare operator
    ├── helm/               # Operator Helm chart
    └── README.md           # Operator documentation

overlays/                   # Environment-based deployments
├── cluster-critical/       # Critical infrastructure (argocd, longhorn, signoz)
│   ├── kustomization.yaml
│   ├── argocd/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   └── longhorn/
│       ├── application.yaml
│       ├── kustomization.yaml
│       └── values.yaml
├── prod/                   # Production services
│   ├── kustomization.yaml
│   ├── cloudflare-tunnel/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── gh-arc-controller/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   └── n8n/
│       ├── application.yaml
│       ├── kustomization.yaml
│       ├── values.yaml
│       └── manifests/       # Helm-rendered n8n manifests (for review)
│           └── all.yaml
└── dev/                    # Development services
    ├── kustomization.yaml
    └── obsidian-automation/
        ├── application.yaml
        ├── kustomization.yaml
        └── values.yaml

pkg/                        # Shared Go libraries
└── n8n/                    # N8N Go client (auto-generated from OpenAPI)

services/                   # Backend services
├── n8n_obsidian_api/       # N8N Obsidian API service
└── hikes/                  # Hikes data scraping and processing
    ├── scrape_walkhighlands/
    └── update_forecast/

websites/                   # Static websites
└── hikes.jomcgi.dev/       # Hiking route finder (static)

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

### Currently Deployed

#### Cloudflare Tunnel
- **Zero Trust ingress** - No open firewall ports
- **Automatic HTTPS** with Cloudflare certificates
- **DDoS protection** and **WAF** built-in
- **Deployed via**: ArgoCD Application with Helm chart

#### Longhorn Storage
- **Distributed persistent storage** for Kubernetes
- **Automated backups** and **disaster recovery**
- **High availability** with replica management
- **Deployed via**: ArgoCD Application

#### Cloudflare Operator
- **Custom Kubernetes operator** for Cloudflare resource management
- **Automated tunnel provisioning** and **DNS management**
- **Deployed via**: Helm chart in operators/ directory

#### 1Password Operator
- **Secret management** via OnePasswordItem CRDs
- **Secure credential storage** in 1Password vaults
- **Automatic secret synchronization** to Kubernetes secrets
- **Bootstrapped manually** during cluster setup

#### N8N Workflow Automation
- **Workflow automation platform** for integrations and automations
- **Workflows managed via UI** with persistence in Longhorn storage
- **Persistent storage** via Longhorn (15Gi)
- **API enabled** for programmatic access
- **Ingress**: `n8n.jomcgi.dev` via Cloudflare Tunnel
- **Deployed via**: ArgoCD Application with Helm chart

### Static Websites

#### Hikes Route Finder (hikes.jomcgi.dev)
- **Pure static site** hosted on Cloudflare Pages
- **Cloudflare R2 backend** for data storage
- **No server-side dependencies** - maximum simplicity
- **Comprehensive Playwright testing** for reliability

### Services Under Migration

The following services are preserved in `old/services/` and will be migrated to ArgoCD:

#### Observability Stack (Planned)
- **Grafana Cloud integration** for metrics, logs, traces
- **OpenTelemetry Collector** for telemetry aggregation
- **Prometheus-compatible** metrics from all services

#### Open WebUI (Planned)
- **Local AI interface** with Google Gemini integration
- **No authentication** (secured by Cloudflare Access)
- **Persistent storage** via Longhorn

#### Obsidian MCP (Planned)
- **Note-taking service** with MCP integration
- **API backend** for Obsidian integration
- **Search capabilities** across knowledge base

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

### Spec Workflow Commands
Use the Claude Code spec workflow tool for structured development:
- **Check task status**: `npx @pimzino/claude-code-spec-workflow get-tasks <spec-name>`
- **Complete task**: `npx @pimzino/claude-code-spec-workflow get-tasks <spec-name> <task-id> --mode complete`
- **Spec status**: `npx @pimzino/claude-code-spec-workflow spec-status <spec-name>`

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
2. **Test locally** with Minikube:
   - `minikube start` to spin up local cluster
   - Apply Helm charts: `helm install <service> charts/<service>/`
   - Test with port-forwarding: `kubectl port-forward svc/<service> 8080:80`
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