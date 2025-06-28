# CLAUDE.md - Secure Kubernetes Homelab

## Project Philosophy

This repository embodies the principles from **"A Philosophy of Software Design"** by John Ousterhout:

> **Complexity is the silent killer of engineering velocity and reliability.**

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
┌─────────────────┐    ┌───────────────────┐    ┌─────────────────┐
│ Cloudflare      │    │ Talos Kubernetes  │    │ Observability   │
│ Tunnel          │───▶│ Cluster           │───▶│ (Grafana Cloud) │
│ (Zero Trust)    │    │ - Service A       │    │ - Metrics       │
└─────────────────┘    │ - Service B       │    │ - Logs          │
                       └───────────────────┘    │ - Traces        │
                                                └─────────────────┘
```

## Directory Structure

```
cluster/
├── crd/                    # Custom Resource Definitions
│   ├── external-secrets/   # Secrets management
│   └── longhorn/          # Persistent storage
└── services/              # Application deployments
    ├── cloudflare-tunnel/ # Secure ingress
    ├── grafana-cloud/     # Observability
    ├── obsidian/          # Note-taking
    ├── open-webui/        # AI chat interface
    └── otel-collector/    # Telemetry collection

projects/                  # Side projects
└── find_good_hikes/      # Weather + walking route finder
```

## Security Model

### Network Security
- **No direct internet exposure** - All traffic via Cloudflare Tunnel
- **Least privilege** - Services run as non-root with read-only filesystems
- **Network policies** - Microsegmentation where needed
- **Secret management** - External Secrets Operator with proper RBAC

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

### GitOps with Skaffold
- **Declarative deployments** via Helm + Kustomize
- **Automated CI/CD** with GitHub Actions
- **Health checks** and **readiness probes** on everything
- **Resource limits** prevent resource exhaustion

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

### Cloudflare Tunnel
- **Zero Trust ingress** - No open firewall ports
- **Automatic HTTPS** with Cloudflare certificates
- **DDoS protection** and **WAF** built-in

### Open WebUI
- **Local AI interface** with Google Gemini integration
- **No authentication** (secured by Cloudflare Access)
- **Persistent storage** via Longhorn

### Observability Stack
- **Metrics, logs, traces** sent to Grafana Cloud
- **OpenTelemetry Collector** for telemetry aggregation
- **Prometheus-compatible** metrics from all services

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

### Adding a New Service
1. Create namespace and basic manifests in `cluster/services/<name>/`
2. Add Skaffold configuration for deployment
3. Update GitHub Actions workflow for CI/CD
4. Add health checks and observability
5. Test the complete deployment path

### Security Review Checklist
- [ ] Service runs as non-root user
- [ ] Read-only root filesystem
- [ ] No privilege escalation
- [ ] Resource limits defined
- [ ] Network policies applied (if needed)
- [ ] Secrets properly managed
- [ ] Ingress via Cloudflare Tunnel only

### Observability Requirements
Every service must:
- [ ] Export Prometheus metrics on `/metrics`
- [ ] Provide health check endpoint
- [ ] Send structured logs
- [ ] Include OpenTelemetry tracing (for user-facing services)

## Development Workflow

1. **Make changes** in feature branch
2. **Test locally** with Skaffold: `skaffold dev`
3. **Verify deployment** works end-to-end
4. **Check observability** - metrics, logs, traces
5. **Create PR** - GitHub Actions runs integration tests
6. **Merge** - Automatic deployment to production

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