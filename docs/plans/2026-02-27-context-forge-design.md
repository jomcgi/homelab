# Context Forge MVP — Implementation Design

**Date:** 2026-02-27
**RFC:** `architecture/rfcs/context-forge.md`
**Branch:** `feat/context-forge`

---

## Scope

Deploy Context Forge as an MCP gateway with the official SigNoz MCP server as an upstream backend, exposed via Cloudflare tunnel at `mcp.jomcgi.dev`. Read-only. Single gateway pattern ready for future ArgoCD/Longhorn backends.

## Architecture

```
Agent → Cloudflare (mcp.jomcgi.dev) → Context Forge pod
                                          │
                                          ├─ container: context-forge (gateway, port 4444)
                                          └─ container: signoz-mcp (sidecar, port 8000)
                                                │
                                                └──▶ SigNoz (ClusterIP :8080)
```

- **Context Forge**: upstream image `ghcr.io/ibm/mcp-context-forge:1.0.0-BETA-1`. MCP gateway that aggregates upstream MCP servers behind a single endpoint.
- **SigNoz MCP**: official SigNoz MCP server (`github.com/SigNoz/signoz-mcp-server`), built with Bazel `go_image`, pushed to `ghcr.io/jomcgi/homelab/services/signoz-mcp-server`. Provides 25+ observability tools (logs, traces, metrics, alerts, dashboards).
- **Gateway registration**: postStart lifecycle hook calls `POST /gateways` to register the SigNoz MCP sidecar as an upstream MCP server.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SigNoz integration | Official MCP server (not REST wrappers) | 25+ maintained tools vs 5 hand-crafted; SigNoz team maintains schemas |
| Gateway pattern | Context Forge proxying to SigNoz MCP | Single URL for all future backends; gateway ready for ArgoCD in Phase 2 |
| SigNoz MCP image | Bazel `go_image` (distroless, dual-arch) | Consistent with repo conventions; uid 65532, no Dockerfiles |
| Context Forge image | Upstream Docker image (pinned tag) | Python deps make Bazel build impractical |
| Tool registration | emptyDir SQLite + postStart hook | Fully declarative (script in ConfigMap), no PVC, no drift from Git |
| Namespace | `mcp-gateway` (dedicated) | Clean RBAC scoping for future K8s API access |

## File Structure

```
services/signoz_mcp_server/           # Vendored SigNoz MCP source (Go)
  cmd/server/
    BUILD                             # go_binary
  BUILD                               # go_image

charts/context-forge/                 # Helm chart
  Chart.yaml
  values.yaml
  templates/
    _helpers.tpl
    deployment.yaml                   # 2 containers: gateway + signoz-mcp sidecar
    service.yaml
    configmap.yaml                    # Gateway registration script
    onepassworditem.yaml              # SigNoz API key

overlays/prod/context-forge/          # ArgoCD Application
  application.yaml
  kustomization.yaml
  values.yaml

overlays/prod/cloudflare-tunnel/
  values.yaml                         # + mcp.jomcgi.dev route
```

## Deployment Configuration

### Context Forge container

- Image: `ghcr.io/ibm/mcp-context-forge:1.0.0-BETA-1`
- Port: 4444
- Environment:
  - `HOST=0.0.0.0`
  - `PORT=4444`
  - `DATABASE_URL=sqlite:////data/context-forge.db`
  - `AUTH_REQUIRED=false` (Cloudflare Zero Trust handles external auth)
  - `MCP_CLIENT_AUTH_ENABLED=false`
  - `MCPGATEWAY_UI_ENABLED=false`
  - `MCPGATEWAY_ADMIN_API_ENABLED=true` (needed for gateway registration)
- Volumes: emptyDir at `/data` (SQLite) and `/tmp` (Python runtime)
- Lifecycle: postStart hook runs registration script from ConfigMap

### SigNoz MCP sidecar

- Image: `ghcr.io/jomcgi/homelab/services/signoz-mcp-server` (Bazel-built)
- Port: 8000
- Environment:
  - `SIGNOZ_URL=http://signoz.signoz.svc.cluster.local:8080`
  - `TRANSPORT_MODE=http`
  - `MCP_SERVER_PORT=8000`
  - `SIGNOZ_API_KEY` from 1Password secret

### Registration script (ConfigMap)

```sh
#!/bin/sh
until curl -sf http://localhost:4444/health; do sleep 1; done
curl -X POST http://localhost:4444/gateways \
  -H "Content-Type: application/json" \
  -d '{"name":"signoz","url":"http://localhost:8000/sse","description":"SigNoz observability"}'
```

### Cloudflare tunnel route

Added to existing `overlays/prod/cloudflare-tunnel/values.yaml`:

```yaml
- hostname: mcp.jomcgi.dev
  service: http://context-forge.mcp-gateway.svc.cluster.local:4444
```

### Secrets

One `OnePasswordItem` CRD: `context-forge-secrets` with `SIGNOZ_API_KEY` (SigNoz viewer API key). Item path: `vaults/k8s-homelab/items/context-forge-secrets`.

## Security

- Context Forge: upstream image runs its own user; may need security context exception similar to trips-api if it requires writable filesystem beyond `/data` and `/tmp`
- SigNoz MCP: distroless, uid 65532, readOnlyRootFilesystem, drop ALL capabilities
- No auth on gateway (Cloudflare Zero Trust authenticates external agents via service token; ClusterIP isolates from unauthenticated traffic)
- SigNoz API key is read-only (viewer scope)
- No write operations registered

## Manual Steps (not in Git)

1. Create 1Password item `context-forge-secrets` with SigNoz viewer API key
2. Create Cloudflare Zero Trust service token scoped to `mcp.jomcgi.dev`
3. Store CF service token in 1Password, configure local `direnv` to export `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET`
4. Add `.mcp.json` entry for Claude Code after deployment validates

## Out of Scope

- ArgoCD backend (Phase 2)
- K8s API, Longhorn backends
- Per-agent JWT auth
- Write operations
- Virtual server bundling (role-scoped tool subsets)
