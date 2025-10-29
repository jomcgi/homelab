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
└── n8n/                    # N8N workflow automation
    ├── WORKFLOWS.md        # Workflow GitOps documentation
    └── templates/          # Helm templates

clusters/                   # Cluster entry points
└── homelab/                # Production cluster
    └── kustomization.yaml  # References overlays (dev, prod, cluster-critical)

operators/                  # Custom Kubernetes operators
└── cloudflare/             # Cloudflare operator
    └── helm/               # Operator Helm chart

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
│       └── workflows/       # Environment-specific workflow ConfigMaps
│           └── *.yaml       # Workflow definitions
└── dev/                    # Development services
    ├── kustomization.yaml
    └── obsidian-automation/
        ├── application.yaml
        ├── kustomization.yaml
        └── values.yaml

websites/                   # Static websites
└── hikes.jomcgi.dev/       # Hiking route finder (static)
└── jomcgi.dev/frank        # Frank x Vancouver trip site

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
- **GitOps-managed workflows** via ConfigMaps and initContainer sync
- **Persistent storage** via Longhorn (15Gi)
- **API-based deployment** with name-based matching and tagging
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

### Working with Helm and ArgoCD Applications

The repository includes **two complementary tools** for working with ArgoCD deployments:

#### 1. Fast Helm Rendering (for quick iteration)

For rapid feedback during development:
```bash
bazel run //overlays/<env>/<service>:render
```

This runs `helm template` directly with values from the ArgoCD Application manifest. **Fast (~2s) but may not match ArgoCD exactly** (doesn't include plugins, transformations, server-side apply).

**Auto-generated BUILD files:**
```bash
bazel run //:gazelle  # Discovers application.yaml files and creates render targets
```

See `tools/helm/README.md` for details on the Gazelle extension.

#### 2. Accurate ArgoCD Diff (for validation)

For 100% accurate preview of what ArgoCD will deploy:
```bash
# One-time setup (~60s)
bazel run //tools/argocd:create_snapshot

# Then use for every diff (~10s)
bazel run //tools/argocd:diff                    # Compare with origin/main
bazel run //tools/argocd:diff -- origin/develop  # Compare with other branch
```

This uses **Docker snapshots** to start a real ArgoCD instance in ~5 seconds, then renders manifests using ArgoCD's actual engine. **100% accurate, works with all ArgoCD features** (Helm, Kustomize, plugins, SSA).

See `tools/argocd/README.md` for architecture details.

#### When to Use Which Tool

| Tool | Speed | Accuracy | Use Case |
|------|-------|----------|----------|
| `helm_render` | ~2s | ~95% | Quick iteration, Claude exploring charts |
| `argocd:diff` | ~10s | 100% | Final validation, complex apps, before merge |

#### Gazelle Directives

Control BUILD generation with directives in `kustomization.yaml`:

```yaml
# Enable/disable Helm BUILD generation
# gazelle:argocd enabled

# Generate diff rules (requires cluster access for kubectl diff)
# gazelle:argocd_generate_diff true

# Set kubectl context for diff operations
# gazelle:kubectl_context homelab
```

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

### Managing N8N Workflows

N8N workflows are managed as Kubernetes ConfigMaps and automatically synced to n8n via an initContainer.

#### Adding a New Workflow

1. **Export from n8n UI**: Download workflow as JSON from n8n
2. **Clean instance data**:
   ```bash
   cat workflow.json | jq 'del(.id) |
     walk(if type == "object" then del(.webhookId) else . end) |
     del(.meta.instanceId)' > cleaned-workflow.json
   ```
3. **Create ConfigMap** in `overlays/prod/n8n/workflows/<name>.yaml`:
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: n8n-workflow-<name>
     namespace: n8n
     labels:
       app.kubernetes.io/name: n8n
       app.kubernetes.io/component: workflow
       workflow-sync: "enabled"
   data:
     <name>.json: |
       # Paste cleaned workflow JSON here (indented 4 spaces)
   ```
4. **Add to kustomization**: Update `overlays/prod/n8n/kustomization.yaml`:
   ```yaml
   resources:
     - ./workflows/<name>.yaml
   ```
5. **Add to Helm values**: Update `overlays/prod/n8n/values.yaml` projected volume:
   ```yaml
   extraVolumes:
     - name: workflows
       projected:
         sources:
           - configMap:
               name: n8n-workflow-<name>
   ```
6. **Commit and push**: ArgoCD syncs, restart n8n pod to import workflow

#### Workflow Naming Convention

- **In Git**: `"name": "My Workflow"`
- **In n8n**: `My Workflow [git-managed]`
- **Tag**: Automatically tagged with `gitops-managed`

This makes it clear which workflows are managed by Git vs created in the UI.

#### Updating a Workflow

1. Edit the workflow JSON in the ConfigMap
2. Commit and push changes
3. Restart n8n pod: `kubectl rollout restart deployment/n8n -n n8n`

The initContainer will update the workflow on startup (matched by name).

#### First-Time Setup

Generate n8n API key and create secret:
```bash
# 1. Open n8n UI: Settings > n8n API > Create API key
# 2. Create secret
kubectl create secret generic n8n-api-key \
  --from-literal=api-key=YOUR_KEY \
  --namespace=n8n
```

See `charts/n8n/WORKFLOWS.md` for complete documentation.

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