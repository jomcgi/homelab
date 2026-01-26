# Security Model

This document describes the security architecture of the homelab cluster.

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
