# Structure Steering Document

## Directory Organization

```
homelab/
├── .claude/                    # Claude Code configuration
│   ├── agents/                 # Custom Claude agents
│   ├── commands/               # Custom slash commands
│   ├── specs/                  # Specification documents
│   ├── steering/               # Steering documents (this directory)
│   └── CLAUDE.md              # Project-specific Claude instructions
│
├── charts/                     # Helm charts for applications
│   ├── argocd/                # ArgoCD deployment
│   ├── cloudflare-tunnel/     # Ingress tunnel configuration
│   ├── n8n/                   # Workflow automation
│   └── signoz/                # Observability platform
│
├── clusters/                   # ArgoCD cluster configurations
│   └── homelab/               # Production cluster
│       ├── argocd/            # ArgoCD self-management
│       ├── cloudflare-tunnel/ # Tunnel application
│       ├── longhorn/          # Storage application
│       ├── n8n/               # N8N workflow automation
│       └── signoz/            # SigNoz observability
│
├── operators/                  # Custom Kubernetes operators
│   └── cloudflare/            # Cloudflare resource operator
│       ├── api/               # CRD API definitions
│       ├── cmd/               # Operator entrypoint
│       ├── controllers/       # Reconciliation logic
│       ├── helm/              # Operator Helm chart
│       └── tests/             # BDD/integration tests
│
├── overlays/                   # Kustomize environment configs
│   ├── base/                  # Base configurations
│   ├── dev/                   # Development environment
│   └── homelab-prod/          # Production environment
│
└── websites/                   # Static websites
    ├── hikes.jomcgi.dev/      # Hiking route finder
    └── jomcgi.dev/            # Personal homepage
```

## File Naming Conventions

### Kubernetes Manifests
- **Helm Charts**: `Chart.yaml`, `values.yaml`, `templates/*.yaml`
- **Kustomize**: `kustomization.yaml`, `patches/*.yaml`
- **ArgoCD**: `application.yaml` or `app.yaml`
- **ConfigMaps**: `*-config.yaml` or `*-configmap.yaml`
- **Secrets**: `*-secret.yaml` (using OnePasswordItem CRDs)

### Source Code
- **Go Files**: `snake_case.go` for files, `CamelCase` for types
- **Python Files**: `snake_case.py` following PEP 8
- **JavaScript**: `camelCase.js` or `kebab-case.js` for files
- **Tests**: `*_test.go`, `test_*.py`, `*.test.js`

### Documentation
- **README Files**: `README.md` in each major directory
- **API Docs**: `api.md` or inline godoc comments
- **Specs**: `.claude/specs/<feature-name>.md`

## Code Organization Patterns

### Helm Charts (`charts/<name>/`)
```
<name>/
├── Chart.yaml              # Chart metadata
├── values.yaml             # Default values
├── values.dev.yaml         # Development overrides
├── values.prod.yaml        # Production overrides
├── templates/
│   ├── deployment.yaml     # Main deployment
│   ├── service.yaml        # Service definition
│   ├── ingress.yaml        # Ingress rules
│   ├── configmap.yaml      # Configuration
│   └── _helpers.tpl        # Template helpers
└── tests/
    └── integration_test.go # BDD integration tests
```

### Operators (`operators/<name>/`)
```
<name>/
├── api/
│   └── v1alpha1/
│       ├── types.go        # CRD type definitions
│       └── zz_generated.go # Generated deepcopy
├── cmd/
│   └── main.go            # Operator entrypoint
├── controllers/
│   ├── controller.go      # Main reconciliation
│   └── controller_test.go # BDD controller tests
├── helm/
│   └── <name>/            # Operator Helm chart
├── config/
│   ├── crd/               # CRD manifests
│   └── rbac/              # RBAC definitions
└── go.mod                 # Go module definition
```

### ArgoCD Applications (`clusters/homelab/<name>/`)
```
<name>/
├── application.yaml        # ArgoCD Application
├── values.yaml            # Helm value overrides
└── kustomization.yaml     # Optional Kustomize config
```

## Testing Structure

### BDD Test Organization
- **Feature Files**: `tests/features/*.feature` (if using Gherkin)
- **Step Definitions**: `tests/steps/*_steps.go` or `*_steps.py`
- **Integration Tests**: `tests/integration/*_test.go`
- **End-to-End**: `tests/e2e/*.spec.js` (Playwright)

### Test Naming
- **Go**: `TestFeature_Scenario` (e.g., `TestTunnel_CreatesRoute`)
- **Python**: `test_feature_scenario` (e.g., `test_api_returns_json`)
- **JavaScript**: `describe('Feature', () => { it('scenario', ...) })`

## Configuration Management

### Environment-Specific Configs
1. **Base Configuration**: Define in `charts/<name>/values.yaml`
2. **Environment Overrides**: Use `values.dev.yaml`, `values.prod.yaml`
3. **Secret References**: Use OnePasswordItem CRDs, never hardcode
4. **Feature Flags**: Environment variables in ConfigMaps

### GitOps Structure
- **Single Source of Truth**: Git repository
- **Environment Promotion**: Dev → Prod via PR
- **Rollback Strategy**: Git revert with ArgoCD sync

## Conventions and Standards

### Container Images
- **Registry**: `ghcr.io/jomcgi/<name>`
- **Tags**: `v1.2.3` for releases, `main` for latest
- **Multi-arch**: Support `linux/amd64` and `linux/arm64`

### Labels and Annotations
```yaml
metadata:
  labels:
    app.kubernetes.io/name: <name>
    app.kubernetes.io/instance: <instance>
    app.kubernetes.io/version: <version>
    app.kubernetes.io/component: <component>
    app.kubernetes.io/part-of: homelab
    app.kubernetes.io/managed-by: argocd
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"
```

### Security Context (Standard)
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  fsGroup: 65532
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
  seccompProfile:
    type: RuntimeDefault
```

## Development Workflow

### Adding New Service
1. Create Helm chart in `charts/<service>/`
2. Add BDD tests in `charts/<service>/tests/`
3. Create ArgoCD app in `clusters/homelab/<service>/`
4. Test locally with Minikube
5. Deploy via Git commit (ArgoCD auto-sync)

### Adding New Operator
1. Scaffold operator in `operators/<name>/`
2. Define CRDs in `operators/<name>/api/`
3. Implement controller logic with BDD tests
4. Package as Helm chart in `operators/<name>/helm/`
5. Deploy via ArgoCD with Git reference

### Modifying Existing Service
1. Update Helm chart or values
2. Run BDD tests locally
3. Commit changes to feature branch
4. Create PR for review
5. Merge triggers ArgoCD sync

## Best Practices

### Code Quality
- **Style Guides**: Follow Google's style guides
- **Linting**: Run linters before commit
- **Testing**: BDD tests for public interfaces
- **Documentation**: Document public APIs and complex logic

### Resource Management
- **Requests/Limits**: Set appropriate CPU/memory constraints
- **HPA**: Use for services with variable load
- **PDB**: Define PodDisruptionBudgets for critical services
- **Priority Classes**: Use for critical system components

### Observability Requirements
- **Metrics**: Export Prometheus metrics on `/metrics`
- **Health Checks**: Implement `/health` and `/ready` endpoints
- **Structured Logging**: JSON logs with trace correlation
- **Tracing**: OpenTelemetry spans for request flows

### Security Requirements
- **No Root**: Never run containers as root
- **Read-Only FS**: Use read-only root filesystems
- **Network Policies**: Implement where appropriate
- **Secret Management**: Only via 1Password Operator
- **Image Scanning**: Scan images for vulnerabilities