# MCP Servers Chart Design

A single Helm chart (`charts/mcp-servers/`) that deploys any number of MCP servers from a range-based values list. Replaces per-server charts (starting with `signoz-mcp`) and integrates protocol translation, gateway registration, and SigNoz HTTPCheck alerts.

## Goals

1. **One chart, many servers** -- adding an MCP server = one values entry, one PR
2. **Optional translate sidecar** -- stdio servers get the upstream IBM `mcpgateway.translate` image as a sidecar, exposing streamable-http. Native HTTP servers run without it.
3. **Self-registering** -- each server optionally registers itself with Context Forge gateway via a post-install/post-upgrade Job
4. **Baked-in alerts** -- each server optionally generates a SigNoz HTTPCheck alert ConfigMap

## Architecture

```
charts/mcp-servers/
  Chart.yaml
  values.yaml
  templates/
    _helpers.tpl
    deployment.yaml         # range: pod with optional translate sidecar
    service.yaml            # range: ClusterIP per server
    serviceaccount.yaml     # range: SA per server
    rbac.yaml               # range: optional ClusterRoleBinding/RoleBinding
    registration-job.yaml   # range: optional post-install Job per server
    alert.yaml              # range: optional HTTPCheck ConfigMap per server
    onepassworditem.yaml    # range: optional 1Password secret per server
```

All templates iterate over `.Values.servers`. Each server entry controls which optional resources are generated via feature flags (`translate.enabled`, `registration.enabled`, `alert.enabled`).

## Values Schema

### Chart-level defaults

```yaml
translate:
  image:
    repository: ghcr.io/ibm/mcp-context-forge
    tag: v1.0.0-RC1
    pullPolicy: IfNotPresent

gateway:
  url: "http://context-forge-mcp-stack-mcpgateway.mcp-gateway.svc.cluster.local:80"
  secret:
    name: context-forge-jwt

alertDefaults:
  evalWindow: "10m0s"
  frequency: "2m0s"
  matchType: "5"
  severity: "critical"
  channels: ["pagerduty-homelab"]

servers: []
```

### Per-server entry

```yaml
- name: signoz-mcp # required: used for all resource names
  image: # required
    repository: docker.io/signoz/signoz-mcp-server
    tag: "v0.0.5"
  port: 8000 # required when translate.enabled=false
  env: [] # optional: env vars for server container
  secret: # optional: creates OnePasswordItem + secretRef
    name: signoz-mcp
    itemPath: "vaults/k8s-homelab/items/signoz-mcp"
  resources: # required
    requests: { cpu: 10m, memory: 64Mi }
    limits: { cpu: 100m, memory: 128Mi }
  translate: # required (at minimum enabled: false)
    enabled: false # true = add sidecar
    command: "" # stdio command for translate to wrap
    port: 8080 # sidecar listen port (default 8080)
  registration: # optional
    enabled: true
    transport: "streamable-http" # default transport for gateway registration
  alert: # optional
    enabled: true
    url: "http://signoz-mcp.mcp-servers.svc.cluster.local:8000/health"
    severity: "" # override alertDefaults.severity
    channels: [] # override alertDefaults.channels
  rbac: # optional
    clusterRole: "" # bind SA to existing ClusterRole
    namespaced: [] # list of {namespace, role} for RoleBindings
```

## Deployment Modes

### Native HTTP server (translate.enabled: false)

Single-container pod. The server exposes its own port. Service targets that port. Probes on the server container.

### Stdio server with translate sidecar (translate.enabled: true)

Two-container pod:

- **server** -- runs headless with `stdin: true`, no ports, no probes
- **translate** -- runs `python3 -m mcpgateway.translate --stdio "<command>" --expose-streamable-http --port <port>`. Exposes the network port. Gets the probes.

The translate sidecar uses the upstream IBM `mcp-context-forge` image. No custom image build needed.

## Registration

Per-server Helm hook Job (`post-install`, `post-upgrade`) with:

1. **Init-container** -- polls `gateway.url/health` until healthy (handles cross-release ordering)
2. **Register container** -- mints short-lived JWT using PyJWT (from the IBM image), then:
   - DELETE existing registration (idempotent)
   - POST new registration with server URL and transport
3. **Cleanup** -- `helm.sh/hook-delete-policy: before-hook-creation` + `ttlSecondsAfterFinished: 300`

Registration is best-effort. A failed Job does not block the sync -- servers are healthy and running regardless. Manual follow-up in the gateway UI is the fallback.

## HTTPCheck Alerts

Each server with `alert.enabled: true` generates a ConfigMap with:

- Label `signoz.io/alert: "true"` (picked up by signoz-dashboard-sidecar)
- Standard HTTPCheck alert JSON matching the existing `api-gateway-httpcheck-alert.yaml` pattern
- Defaults from `alertDefaults`, overridable per server

## Security

All pods follow existing patterns:

- `runAsNonRoot: true`, `runAsUser: 65532`
- `readOnlyRootFilesystem: true`
- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`
- `seccompProfile.type: RuntimeDefault`
- Secrets via 1Password `OnePasswordItem` CRD

## Migration

### Removed

- `charts/signoz-mcp/` -- absorbed into `charts/mcp-servers/`
- `overlays/prod/signoz-mcp/` -- replaced by `overlays/prod/mcp-servers/`
- `context-forge` registration-job's signoz-mcp entry -- replaced by self-registration

### Added

- `charts/mcp-servers/` -- new chart
- `overlays/prod/mcp-servers/` -- ArgoCD Application + values with signoz-mcp as first server

### Coordination

Remove signoz-mcp registration from context-forge's registration-job before deploying the new chart to avoid duplicate registrations during transition.
