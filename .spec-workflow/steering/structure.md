# Project Structure

## Directory Organization

```
homelab/
├── charts/                     # Helm charts for custom services
│   └── cloudflare-tunnel/     # Cloudflare Tunnel Helm chart
│       ├── templates/          # Kubernetes manifest templates
│       ├── values.yaml         # Default configuration values
│       └── Chart.yaml          # Chart metadata
│
├── clusters/                   # ArgoCD cluster configurations (GitOps)
│   └── homelab/                # Production cluster applications
│       ├── cloudflare-tunnel/  # ArgoCD Application for tunnel
│       ├── longhorn/           # ArgoCD Application for storage
│       └── [future-services]/  # Additional service applications
│
├── operators/                  # Custom Kubernetes operators
│   └── cloudflare/             # Cloudflare operator for resource management
│       ├── helm/               # Operator Helm chart
│       │   ├── templates/      # Operator deployment manifests
│       │   └── values.yaml     # Operator configuration
│       └── crds/               # Custom Resource Definitions (if needed)
│
├── overlays/                   # Kustomize configuration overlays
│   ├── base/                   # Base configurations
│   └── homelab-prod/           # Production environment overlays
│
├── websites/                   # Static websites hosted externally
│   └── hikes.jomcgi.dev/       # Hiking route finder (Cloudflare Pages)
│       ├── src/                # Website source code
│       ├── tests/              # Playwright integration tests
│       └── README.md           # Site-specific documentation
│
├── .spec-workflow/             # Spec workflow documentation
│   ├── steering/               # Project steering documents
│   │   ├── product.md          # Product vision and goals
│   │   ├── tech.md             # Technology stack decisions
│   │   └── structure.md        # This document
│   └── specs/                  # Feature specifications (future)
│
├── .claude/                    # Claude Code configuration
│   └── CLAUDE.md               # Project instructions for AI assistant
│
├── .github/                    # GitHub configuration
│   └── workflows/              # CI/CD workflows (future)
│
└── README.md                   # Project overview and setup instructions
```

## Naming Conventions

### Files
- **Helm Charts**: `kebab-case` for chart names (e.g., `cloudflare-tunnel`)
- **Kubernetes Manifests**: `kebab-case.yaml` (e.g., `deployment.yaml`, `service-account.yaml`)
- **ArgoCD Applications**: `kebab-case.yaml` matching the service name (e.g., `cloudflare-tunnel.yaml`)
- **Directories**: `kebab-case` for consistency (e.g., `homelab-prod`, `cloudflare-tunnel`)
- **Documentation**: `UPPERCASE.md` for root-level docs (e.g., `README.md`, `CLAUDE.md`), `lowercase.md` for nested docs

### Code (YAML/Kubernetes)
- **Kubernetes Resources**: `kebab-case` for names (e.g., `metadata.name: cloudflare-tunnel`)
- **Labels**: `kebab-case` for keys and values (e.g., `app.kubernetes.io/name: cloudflare-tunnel`)
- **ConfigMap/Secret Keys**: `kebab-case` or `UPPER_SNAKE_CASE` depending on usage (e.g., `tunnel-config` or `API_TOKEN`)
- **Helm Values**: `camelCase` for nested keys (e.g., `replicaCount`, `securityContext`)
- **Namespaces**: `kebab-case` (e.g., `cloudflare-tunnel`, `monitoring`)

## Import Patterns

### Helm Chart Dependencies
Not applicable - charts are standalone without dependencies currently.

### Kustomize Resource Order
```yaml
# kustomization.yaml pattern:
resources:
  - namespace.yaml           # Namespace first
  - serviceaccount.yaml      # RBAC resources
  - role.yaml
  - rolebinding.yaml
  - configmap.yaml           # Configuration
  - secret.yaml
  - deployment.yaml          # Workloads
  - service.yaml             # Networking
  - ingress.yaml
```

### ArgoCD Application Organization
```yaml
# Application structure:
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <service-name>
  namespace: argocd
spec:
  source:
    # Points to Git repo path or Helm chart
    path: charts/<chart-name> OR overlays/<overlay-name>
  destination:
    # Target cluster and namespace
    namespace: <target-namespace>
```

## Code Structure Patterns

### Helm Chart Organization
```
chart-name/
├── Chart.yaml              # Chart metadata (name, version, description)
├── values.yaml             # Default configuration values (well-commented)
├── templates/
│   ├── NOTES.txt           # Post-installation notes
│   ├── _helpers.tpl        # Template helper functions
│   ├── namespace.yaml      # Namespace definition (if needed)
│   ├── serviceaccount.yaml # Service account
│   ├── configmap.yaml      # Configuration data
│   ├── secret.yaml         # Sensitive data (from 1Password)
│   ├── deployment.yaml     # Main workload
│   ├── service.yaml        # Service exposure
│   └── tests/              # Helm test hooks (optional)
└── README.md               # Chart documentation
```

### Kubernetes Manifest Organization (within templates/)
```yaml
# Standard order within a manifest file:
apiVersion: ...
kind: ...
metadata:
  name: ...
  namespace: ...
  labels: ...
  annotations: ...
spec:
  # Spec fields organized logically
  # Security context near the top
  # Container definitions next
  # Volume mounts and volumes at the end
```

### values.yaml Organization
```yaml
# 1. Global settings
replicaCount: 1
image:
  repository: ...
  tag: ...
  pullPolicy: ...

# 2. Service-specific configuration
service:
  type: ClusterIP
  port: 80

# 3. Security settings
securityContext:
  readOnlyRootFilesystem: true
  runAsNonRoot: true

# 4. Resource limits
resources:
  limits: ...
  requests: ...

# 5. Application-specific config
config:
  # Service-specific settings
```

## Code Organization Principles

1. **Single Responsibility**: Each Helm chart serves one service or logical component
2. **Modularity**: ArgoCD Applications are independently deployable and manageable
3. **Testability**: Charts can be validated with `helm lint` and deployed to test clusters
4. **Consistency**: All charts follow the same structure and security patterns
5. **Declarative Over Imperative**: Everything defined in Git, no manual kubectl apply

## Module Boundaries

### Clear Separation of Concerns

- **charts/ vs operators/**:
  - `charts/` contains Helm charts for deployable services
  - `operators/` contains custom controllers that manage external resources
  - Direction: Operators are deployed independently, services may depend on operators being installed

- **clusters/ vs overlays/**:
  - `clusters/` contains ArgoCD Applications (what to deploy)
  - `overlays/` contains Kustomize configurations (how to customize)
  - Direction: ArgoCD Applications reference overlays/charts, not the reverse

- **Infrastructure vs Applications**:
  - Infrastructure: Longhorn, ArgoCD, 1Password Operator (bootstrap layer)
  - Applications: Services deployed via ArgoCD (application layer)
  - Direction: Applications depend on infrastructure being healthy

### Dependency Direction Rules

```
ArgoCD Applications (clusters/)
    ↓ references
Helm Charts (charts/) OR Kustomize Overlays (overlays/)
    ↓ depends on
Infrastructure Operators (operators/)
    ↓ requires
Bootstrapped Components (1Password, ArgoCD itself)
```

## Code Size Guidelines

### File Size
- **Helm templates**: <200 lines per template file (split large deployments into multiple files)
- **values.yaml**: <300 lines (use comments generously for clarity)
- **Kubernetes manifests**: <150 lines per resource (one resource per file preferred)
- **Documentation**: <500 lines per markdown file (split into multiple docs if needed)

### Template Complexity
- **Helm template conditionals**: Max 3 levels of nesting in `{{ if }}` blocks
- **YAML nesting depth**: Max 6 levels (Kubernetes limits, readability)
- **values.yaml nesting**: Max 4 levels (flatten complex configs)

### Chart Scope
- **Resources per chart**: 5-15 Kubernetes resources (not including CRDs)
- **Values per chart**: <50 configurable values (too many indicates over-abstraction)

## Dashboard/Monitoring Structure

### SigNoz (External Service)
```
Not part of repository structure - deployed as self-contained service.
Access via Cloudflare Tunnel or kubectl port-forward.
Configuration minimal - primarily consumed as-is.
```

### ArgoCD Dashboard
```
Built-in ArgoCD UI for GitOps visualization.
Access: kubectl port-forward -n argocd svc/argocd-server 8080:443
No custom dashboard code in this repository.
```

### Separation of Concerns
- **Observability isolated**: SigNoz and ArgoCD run independently
- **Minimal coupling**: Services emit metrics/logs; observability systems consume
- **No custom dashboards**: Use built-in tools (SigNoz, ArgoCD UI, k9s)
- **Configuration via GitOps**: Even observability services deployed via ArgoCD

## Documentation Standards

### Required Documentation

1. **Chart-level README.md**: Every Helm chart must have:
   - Chart purpose and description
   - Installation instructions
   - Configuration options (key values.yaml fields)
   - Example usage
   - Security considerations

2. **Service-level documentation**: Each ArgoCD Application should have:
   - Purpose and functionality
   - Dependencies (other services, operators)
   - Health check endpoints
   - Observability (metrics, logs exported)

3. **Inline comments**:
   - **values.yaml**: Every configurable value should have a comment explaining its purpose
   - **Helm templates**: Complex conditionals and loops should have explanatory comments
   - **Kustomize patches**: Why the patch exists and what it modifies

4. **Architecture documentation**:
   - `.claude/CLAUDE.md`: High-level project philosophy and architecture
   - `.spec-workflow/steering/`: Product, tech, and structure decisions
   - Root `README.md`: Quick start and overview

### Comment Style

```yaml
# Helm values.yaml comments:
# Description of what this setting controls
# Example: replicaCount controls the number of pod replicas
replicaCount: 1

# Kubernetes manifest comments:
apiVersion: apps/v1
kind: Deployment
metadata:
  name: example
  # Annotations for ArgoCD sync waves (deployment order)
  annotations:
    argocd.argoproj.io/sync-wave: "2"
```

### Documentation Principles

- **Explain WHY, not WHAT**: Code shows what it does; comments explain why decisions were made
- **Update docs with code**: Documentation changes are part of the same PR/commit
- **No orphaned docs**: If a service is removed, its documentation goes too
- **Link to external resources**: Reference official Kubernetes/Helm docs for standard patterns
- **Security notes**: Always document security implications of configuration choices
