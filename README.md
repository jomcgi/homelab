# Secure Kubernetes Homelab

A production-grade Kubernetes homelab running K3s with security-first design, GitOps deployment, and full observability.

## Design Principles

- **Zero direct internet exposure** - All ingress via Cloudflare Tunnel
- **Security by default** - Non-root containers, read-only filesystems, mTLS everywhere
- **Observable everything** - Automatic distributed tracing via Linkerd + SigNoz
- **GitOps workflow** - ArgoCD syncs all changes from Git

## Architecture

```mermaid
flowchart LR
    subgraph Internet
        User([User])
    end

    subgraph Cloudflare
        CF[Cloudflare Tunnel]
    end

    subgraph K3s Cluster
        subgraph Ingress
            TUN[Tunnel Pod]
        end

        subgraph Service Mesh
            L[Linkerd]
        end

        subgraph Workloads
            SVC[Services]
        end

        subgraph Observability
            SIG[SigNoz]
        end
    end

    User --> CF --> TUN
    TUN --> L --> SVC
    L -.->|traces| SIG
    SVC -.->|metrics/logs| SIG
```

All pod-to-pod traffic is automatically meshed by Linkerd for mTLS and distributed tracing.

## Directory Structure

```
charts/           # Helm charts for all services
overlays/         # Environment-specific configurations
  cluster-critical/   # Core infrastructure (argocd, linkerd, signoz)
  prod/               # Production services
  dev/                # Development services
clusters/         # Cluster entry points for ArgoCD
operators/        # Custom Kubernetes operators
services/         # Backend service code
websites/         # Frontend applications
```

## Key Components

| Component | Purpose |
|-----------|---------|
| **ArgoCD** | GitOps continuous deployment |
| **Linkerd** | Service mesh with automatic mTLS and tracing |
| **SigNoz** | Unified metrics, logs, and traces |
| **Cloudflare Tunnel** | Zero-trust ingress |
| **Longhorn** | Distributed persistent storage |
| **Kyverno** | Policy engine for security and auto-injection |

## Getting Started

1. Clone this repository
2. Review [.claude/CLAUDE.md](.claude/CLAUDE.md) for detailed architecture and workflows
3. Bootstrap ArgoCD pointing to `clusters/homelab/`

## Documentation

- [Architecture & Workflows](.claude/CLAUDE.md) - Detailed technical documentation
- [Bazel Build System](README.bazel.md) - Build tooling reference

## License

MIT
