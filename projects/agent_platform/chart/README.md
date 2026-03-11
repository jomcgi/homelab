# agent-platform

Umbrella Helm chart bundling the core agent platform components into a single
ArgoCD Application.

## Components

| Subchart                     | Description                                   | Default |
| ---------------------------- | --------------------------------------------- | ------- |
| `context-forge`              | MCP gateway (IBM mcp-stack)                   | enabled |
| `mcp-oauth-proxy`            | OAuth 2.1 proxy for MCP clients (Google OIDC) | enabled |
| `agent-platform-mcp-servers` | MCP server deployments with registration      | enabled |
| `agent-orchestrator`         | REST API + NATS queue for Goose agent jobs    | enabled |
| `goose-sandboxes`            | SandboxTemplate + WarmPool for agent pods     | enabled |
| `agent-sandbox`              | SandboxTemplate CRDs and controller           | enabled |
| `nats`                       | NATS JetStream (upstream chart)               | enabled |

## Image Strategy

**Custom images** are resolved at build time via Bazel's `helm_chart(images={})` map.
The `images={}` dict maps Helm values paths to `OciImageInfo` providers, producing a
`values-generated.yaml` that is baked into the chart `.tgz`.

**Upstream images** are pinned in `values.yaml` with explicit `repository` + `tag`.

## Deployment

The chart is published to `oci://ghcr.io/jomcgi/homelab/charts/agent-platform` by CI.
ArgoCD Image Updater watches the chart OCI artifact and bumps the version in the
ArgoCD Application when a new chart is pushed.

Environment-specific values (secrets, storage classes, domains) live in
`deploy/values.yaml` alongside the ArgoCD Application.

## Local Rendering

```bash
helm dependency update projects/agent_platform/chart/
helm template agent-platform projects/agent_platform/chart/ \
  -f projects/agent_platform/chart/values.yaml \
  -f projects/agent_platform/deploy/values.yaml \
  --namespace agent-platform
```
