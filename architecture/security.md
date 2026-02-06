# Security Model

This document describes the security architecture of the homelab cluster.

## Defense-in-Depth Architecture

This cluster implements five layers of security:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Layer 1: Network Perimeter                         │
├──────────────────────────────────────────────────────────────────────┤
│  Cloudflare Tunnel                                                   │
│  - Zero Trust ingress (no open firewall ports)                       │
│  - DDoS protection                                                   │
│  - WAF (Web Application Firewall)                                    │
│  - TLS termination                                                   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Layer 2: Service Mesh (Linkerd)                   │
├──────────────────────────────────────────────────────────────────────┤
│  - Automatic mTLS for all inter-service communication                │
│  - Traffic encryption within the cluster                             │
│  - Service-to-service authentication                                 │
│  - Network observability and tracing                                 │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  Layer 3: Policy Enforcement (Kyverno)               │
├──────────────────────────────────────────────────────────────────────┤
│  - Validates security contexts on all workloads                      │
│  - Enforces pod security standards                                   │
│  - Automatic injection of security best practices                    │
│  - Mutation and validation admission control                         │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Layer 4: Runtime Security                          │
├──────────────────────────────────────────────────────────────────────┤
│  Container Security Context (enforced on every pod):                 │
│  - readOnlyRootFilesystem: true                                      │
│  - runAsNonRoot: true                                                │
│  - allowPrivilegeEscalation: false                                   │
│  - capabilities.drop: [ALL]                                          │
│  - seccompProfile: RuntimeDefault                                    │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Layer 5: Secret Management                         │
├──────────────────────────────────────────────────────────────────────┤
│  1Password Operator                                                  │
│  - Secrets stored in 1Password vault (external to cluster)           │
│  - OnePasswordItem CRDs sync secrets into Kubernetes                 │
│  - No secrets in Git or container images                             │
│  - Automatic secret rotation support                                 │
└──────────────────────────────────────────────────────────────────────┘
```

## Network Security

- **No direct internet exposure** - All traffic via Cloudflare Tunnel
- **Least privilege** - Services run as non-root with read-only filesystems
- **Network policies** - Microsegmentation where needed
- **Secret management** - 1Password operator with OnePasswordItem CRDs

## Container Security

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

## Security Review Checklist

When adding or modifying services, verify:

- [ ] Service runs as non-root user
- [ ] Read-only root filesystem
- [ ] No privilege escalation
- [ ] Resource limits defined
- [ ] Network policies applied (if needed)
- [ ] Secrets managed via 1Password OnePasswordItem CRDs
- [ ] Ingress via Cloudflare Tunnel only

## Security Anti-Patterns to Avoid

- **Default passwords** or weak secrets
- **Running as root** unnecessarily
- **Overprivileged** service accounts
- **Direct internet exposure** bypassing Cloudflare
