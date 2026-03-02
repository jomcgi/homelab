# Kubernetes API Access via Cloudflare Tunnel

**Status:** Draft
**Author:** Joe McGinley
**Date:** 2026-02-26

---

## Summary

Expose the homelab Kubernetes API server through the existing in-cluster Cloudflare tunnel, enabling `kubectl` access from any machine without SSH bastion hops or direct node access.

## Problem

Current cluster access requires SSH via a Cloudflare-proxied bastion to a specific node, then running kubectl locally on that node. This is brittle (tied to a single node), poor UX (no local tooling), and inconsistent with the rest of the infrastructure which uses HA Cloudflare tunnels for ingress. Recent SSH access has been spotty despite the tunnel itself being stable.

## Goals

- Use existing HA Cloudflare tunnel deployment (no new infrastructure)
- Standard `kubeconfig` that works with `kubectl`, `k9s`, `stern`, Lens, etc.
- Zero-trust network access via Cloudflare Access service tokens
- Non-interactive auth for all use cases (no WARP client, no browser flow)

## Non-Goals

- Replacing in-cluster RBAC (Cloudflare Access handles network auth, K8s RBAC handles authorization)
- Multi-cluster federation
- Browser-based K8s dashboard

---

## Architecture

### Current State

```
Laptop ──SSH (Cloudflare proxied)──► Bastion Node ──kubectl (local)──► K8s API Server
```

Single point of failure, no local tooling, manual SSH session management.

### Proposed State

```
┌─────────────────────────────────────────────────────────┐
│ Client Machine                                          │
│                                                         │
│  ┌──────────┐  localhost:16443  ┌────────────────────┐  │
│  │ kubectl  │ ────────────────► │ cloudflared        │  │
│  │          │                   │ access tcp         │  │
│  │ token:   │                   │ --hostname k8s...  │  │
│  │  <sa>    │                   │ --service-token-*  │  │
│  └──────────┘                   └─────────┬──────────┘  │
│                                           │              │
└───────────────────────────────────────────┼──────────────┘
                                            │ CF Access (service token headers)
                                            ▼
                                ┌───────────────────────┐
                                │ Cloudflare Edge       │
                                │ Access policy:        │
                                │   Service Token auth  │
                                └───────────┬───────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │ K8s Cluster           │
                                │ cloudflared (HA, 2x)  │
                                │  ──► kube-apiserver   │
                                └───────────────────────┘
```

**Flow:** kubectl (SA token) --> `cloudflared access tcp` (local proxy, injects CF service token headers) --> Cloudflare Edge (Access policy enforced) --> in-cluster cloudflared --> K8s API server.

Two independent auth layers:

1. **Cloudflare Access** (network): service token headers authenticate the tunnel connection
2. **K8s RBAC** (API): ServiceAccount token authenticates API requests

---

## Design Decision

**`cloudflared access tcp` with local proxy** — the simplest viable approach:

- Zero changes to K8s API server configuration
- Leverages existing HA tunnel (2 replicas, topology-spread, `system-cluster-critical`)
- Single `cloudflared` binary on client (already installed for other access)
- Service tokens make it fully non-interactive — no browser flows
- Works with all K8s ecosystem tools (k9s, stern, Lens, helm, etc.)

Alternatives considered and rejected:

- **Credential exec plugin** (K8s API server would need OIDC config changes — unnecessary complexity)
- **WARP private routing** (requires WARP client on every device — viable future enhancement)

---

## Implementation

### 1. Add tunnel ingress route

Add to `overlays/prod/cloudflare-tunnel/values.yaml`:

```yaml
ingress:
  routes:
    # ... existing HTTP routes ...
    - hostname: k8s.jomcgi.dev
      service: tcp://kubernetes.default.svc.cluster.local:443
      originRequest:
        noTLSVerify: true
```

The existing Helm chart template iterates `.Values.ingress.routes` and renders `originRequest` via `toYaml` — no chart changes needed. ArgoCD auto-syncs in ~5-10s.

### 2. Create DNS CNAME

Create `k8s.jomcgi.dev` CNAME pointing to the tunnel in the Cloudflare dashboard.

### 3. Create Cloudflare Access application + service token

In Cloudflare One dashboard:

- **Application:** Self-hosted, hostname `k8s.jomcgi.dev`, 24h session duration
- **Policy:** Service Token auth only (no interactive/email policies needed)
- **Service token:** Generate in Access > Service Auth, store `CF-Access-Client-Id` and `CF-Access-Client-Secret` in 1Password (`vaults/k8s-homelab/items/kubernetes-remote-access`)

### 4. Create Kubernetes ServiceAccount + RBAC

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: remote-admin
  namespace: kube-system
---
apiVersion: v1
kind: Secret
metadata:
  name: remote-admin-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: remote-admin
type: kubernetes.io/service-account-token
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: remote-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: remote-admin
    namespace: kube-system
```

Store the SA token in 1Password alongside the CF service token credentials.

### 5. Client setup

Start the local proxy (service token makes this fully non-interactive):

```bash
cloudflared access tcp \
  --hostname k8s.jomcgi.dev \
  --url 127.0.0.1:16443 \
  --service-token-id <CF-Access-Client-Id> \
  --service-token-secret <CF-Access-Client-Secret>
```

Kubeconfig (`~/.kube/homelab-remote.yaml`):

```yaml
apiVersion: v1
kind: Config
clusters:
  - cluster:
      server: https://127.0.0.1:16443
      insecure-skip-tls-verify: true # API server cert won't match localhost; tunnel encrypts the real hop
    name: homelab
users:
  - name: homelab-remote
    user:
      token: <remote-admin-sa-token>
contexts:
  - context:
      cluster: homelab
      user: homelab-remote
    name: homelab-remote
current-context: homelab-remote
```

### 6. Persistent proxy (launchd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.cloudflare.k8s-tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/cloudflared</string>
    <string>access</string>
    <string>tcp</string>
    <string>--hostname</string>
    <string>k8s.jomcgi.dev</string>
    <string>--url</string>
    <string>127.0.0.1:16443</string>
    <string>--service-token-id</string>
    <string>CF_ACCESS_CLIENT_ID_HERE</string>
    <string>--service-token-secret</string>
    <string>CF_ACCESS_CLIENT_SECRET_HERE</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
```

---

## TLS

The connection has two TLS segments:

| Segment                               | TLS                            | Notes                                                                    |
| ------------------------------------- | ------------------------------ | ------------------------------------------------------------------------ |
| kubectl --> local cloudflared         | `insecure-skip-tls-verify`     | API server cert won't match localhost. Traffic never leaves the machine. |
| Cloudflare edge transit               | Encrypted by tunnel protocol   | End-to-end within Cloudflare's network.                                  |
| In-cluster cloudflared --> API server | `noTLSVerify` in tunnel config | Internal cluster network, API server uses self-signed cert.              |

Acceptable for a homelab. For hardening: pin the API server CA via `originCaPool` in tunnel config.

## Security Model

| Layer             | Function                                                             |
| ----------------- | -------------------------------------------------------------------- |
| Cloudflare Access | Network-level authn (service token), session controls, audit logging |
| K8s RBAC          | API-level authz (SA token), ClusterRole scoping, audit policy        |
| Cloudflare Tunnel | Transport encryption, no exposed ports, outbound-only, HA replicas   |

---

## Rollout

| Phase | Task                                                 |
| ----- | ---------------------------------------------------- |
| 0     | Store SA token + CF service token in 1Password       |
| 1     | Add `k8s.jomcgi.dev` TCP route to tunnel values.yaml |
| 2     | Create DNS CNAME                                     |
| 3     | Create CF Access application + service token         |
| 4     | Create K8s ServiceAccount + RBAC                     |
| 5     | Test `cloudflared access tcp` + kubectl from laptop  |
| 6     | Set up launchd persistent proxy                      |
| 7     | Remove SSH bastion dependency (after validation)     |

Post-deployment: monitor shared tunnel metrics. If TCP streaming (watch, logs) causes connection saturation or latency degradation on HTTP routes, split to a dedicated tunnel.

## Future Enhancements

- **Dedicated tunnel:** Isolate API traffic if shared tunnel metrics show impact
- **WARP private routing:** Eliminate local proxy entirely (requires WARP client per device)
- **OIDC integration:** CF Access as K8s OIDC provider, replacing static SA tokens
- **Scoped RBAC:** Per-context ServiceAccounts with reduced permissions (read-only for debugging, admin for ops)
- **Token rotation:** Automate SA + CF service token rotation via CronJob (quarterly cadence is fine for homelab)

## References

- [Cloudflare: kubectl with Zero Trust](https://blog.cloudflare.com/kubectl-with-zero-trust/)
- [Cloudflare: Tunnel kubectl tutorial](https://developers.cloudflare.com/cloudflare-one/tutorials/tunnel-kubectl/)
- [Kubernetes: client-go credential plugins](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#client-go-credential-plugins)
