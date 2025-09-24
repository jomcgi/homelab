# Technology Steering Document

## Core Platform
- **Operating System**: Talos Linux (immutable, secure Kubernetes OS)
- **Orchestration**: Kubernetes v1.33.0+
- **GitOps**: ArgoCD for declarative deployments
- **Package Management**: Helm charts + Kustomize overlays

## Languages & Frameworks
- **Go 1.24+**: Kubernetes operators, system services
- **Python 3.11+**: Data processing, API services, streaming applications
- **JavaScript/Node.js 20+**: Testing, static sites
- **Style Guides**: Google's style guides for all languages

## Infrastructure Components

### Storage & Persistence
- **Distributed Storage**: Longhorn with automated backups
- **Time-Series DB**: Clickhouse (planned for AIS maritime data)
- **Message Streaming**: NATS JetStream (planned for AIS pipeline)
- **Object Storage**: Cloudflare R2 for static assets

### Networking & Security
- **Ingress**: Cloudflare Tunnel (Zero Trust, no open ports)
- **Secret Management**: 1Password Operator with OnePasswordItem CRDs
- **Container Security**: Non-root, read-only filesystems, dropped capabilities
- **DNS & CDN**: Cloudflare with automatic HTTPS

### Observability Stack
- **All-in-One**: SigNoz for metrics, logs, and traces
- **Metrics**: Prometheus-compatible metrics collection
- **Logging**: Structured logs with OpenTelemetry
- **Tracing**: Distributed tracing via OpenTelemetry
- **SLOs**: Service Level Objectives for response time tracking

## Resource Constraints
- **Current Cluster**: 3 nodes × 12 CPU cores × 16GB RAM each
- **Future Upgrade**: Potentially 64GB RAM per node for streaming workloads
- **Performance Requirements**:
  - Web requests: Fast response times (define SLOs)
  - Batch processing: Can be slow
  - Streaming: Near real-time for AIS data

## Third-Party Services
- **Current**:
  - Cloudflare (tunnels, DNS, CDN, Pages, R2)
  - 1Password (secret management)
  - GitHub (code, containers, actions)
  - Norwegian Meteorological Institute (weather API)
- **Planned**:
  - Obsidian Sync (official note synchronization)
  - LLM Providers (OpenAI, Anthropic, Google)

## Development Practices
- **CI/CD**: GitHub Actions for automated testing
- **Container Registry**: GitHub Container Registry (GHCR)
- **Testing**:
  - Playwright for end-to-end testing
  - BDD tests asserting behavior via public interfaces
  - Integration tests on actual deployments (no mocks)
  - No unit tests unless absolutely necessary
- **Local Development**: Minikube for testing deployments

## Deployment Strategy
- **GitOps Workflow**: All changes via Git commits
- **Helm Charts**: Application packaging in `charts/`
- **ArgoCD Apps**: Cluster configs in `clusters/homelab/`
- **Operators**: Custom operators in `operators/`, deployed via Git-referenced Helm charts
- **Self-Healing**: Automatic drift correction via ArgoCD

## Technical Principles
1. **Simplicity First**: Choose boring technology that works
2. **Observable by Default**: All services export metrics on `/metrics`
3. **Idempotent Operations**: Apply configurations multiple times safely
4. **Graceful Degradation**: Services work without optional dependencies
5. **Deep Modules**: Simple interfaces hiding complex implementations

## Architecture Decisions
- **Zero Trust Security**: No direct internet exposure
- **Declarative Everything**: Infrastructure as code
- **Immutable Infrastructure**: No in-place updates
- **Service Mesh**: Not needed for single-user setup
- **Multi-tenancy**: Not required, single namespace approach

## Current State
- **All services managed via ArgoCD**: No legacy deployments
- **Fully GitOps**: Every deployment tracked in Git
- **Operators First**: Custom operators for complex resources