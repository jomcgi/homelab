# Agent Platform Umbrella Chart Consolidation

**Date:** 2026-03-10
**Status:** Approved

## Problem

The agent platform deploys 8 individual ArgoCD Applications across 6+ namespaces, each with their own `application.yaml`, `values-prod.yaml`, and `imageupdater.yaml`. This creates:

- Operational sprawl (8 apps to monitor, 4 Image Updater CRs)
- Duplicated config between the unused umbrella chart and individual overlays
- No single "deploy the agent platform" action

## Design

### Architecture

**Before:** 8 ArgoCD Applications, 6+ namespaces, 4 ImageUpdater CRs tracking individual images
**After:** 1 ArgoCD Application, 1 namespace (`agent-platform`), 1 ImageUpdater CR tracking the chart OCI artifact

### Deployment Flow

```
Code change
  → CI builds images (Bazel)
  → Images baked into chart via helm_chart(images={...})
  → Chart pushed to oci://ghcr.io/jomcgi/homelab/charts/agent-platform (auto-versioned)
  → Image Updater detects new chart digest → bumps chart version in ArgoCD Application
  → ArgoCD syncs
```

### Scope

**In the umbrella (`agent-platform` namespace):**

- agent-orchestrator
- goose-sandboxes + agent-sandbox CRDs/controller
- agent-platform-mcp-servers
- context-forge
- mcp-oauth-proxy
- nats

**Left as-is (separate ArgoCD apps):**

- cluster-agents
- api-gateway
- llama-cpp

### Chart Structure

`projects/agent_platform/deploy/` is the generic chart:

- `Chart.yaml` — umbrella with subchart `file://` dependencies
- `values.yaml` — all defaults including upstream image pins
- `values.schema.json` — schema for validation
- `README.md` — chart documentation
- `templates/` — umbrella-level templates (NOTES.txt)

`projects/agent_platform/deploy/BUILD`:

```python
helm_chart(
    name = "chart",
    publish = True,
    lint = False,
    images = {
        "agent-orchestrator.image": "//projects/agent_platform/orchestrator:image.info",
        "goose-sandboxes.sandboxTemplate.image": "//projects/agent_platform/goose_agent/image:image.info",
        "agent-platform-mcp-servers.servers[1].image": "//projects/agent_platform/buildbuddy_mcp:image.info",
        "agent-platform-mcp-servers.servers[4].image": "//projects/todo_app:py_image.info",
        "agent-platform-mcp-servers.servers[5].image": "//projects/agent_platform/orchestrator/mcp:image.info",
    },
)
```

### ArgoCD Application Config (homelab-specific)

New directory: uses existing `projects/agent_platform/` kustomization pointing to a single app:

- `application.yaml` — ArgoCD Application using `source.chart` (OCI)
- `values-homelab.yaml` — environment overrides only (1Password, storageClass, OTel, domains)
- `imageupdater.yaml` — single CR watching the chart OCI artifact
- `kustomization.yaml` — makes it discoverable

### Image Strategy

- **Custom images** → `images={}` map in BUILD, Bazel resolves repo+tag from `.info` providers
- **Upstream images** → pinned in chart default `values.yaml` with explicit `repository` + `tag`
- **Image Updater** → watches the chart OCI artifact only (not individual images)

### Namespace Consolidation

All services move to `agent-platform` namespace. Pod-to-pod NetworkPolicies use label selectors for isolation within the namespace. The sandboxes NetworkPolicy simplifies since orchestrator is now co-located.

### Service Discovery Changes

Internal service URLs change from cross-namespace to same-namespace:

- `nats://nats.nats.svc` → `nats://agent-platform-nats:4222`
- `context-forge-mcp-stack-mcpgateway.mcp-gateway.svc` → `agent-platform-context-forge-mcp-stack-mcpgateway:80`
- MCP server health check URLs update similarly

### What Gets Removed

- Individual `application.yaml` for consolidated services
- Individual `imageupdater.yaml` files
- Individual `values-prod.yaml` files (merged into chart defaults + homelab overrides)
- `argocd_app()` targets from individual subchart BUILD files
