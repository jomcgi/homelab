# agent-platform

Umbrella Helm chart bundling the core agent platform components into a single
ArgoCD Application.

- **Chart version:** 0.8.0
- **OCI registry:** `oci://ghcr.io/jomcgi/homelab/charts/agent-platform`
- **Namespace:** `agent-platform`
- **Source:** [`projects/agent_platform/chart/`](.)

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components](#components)
- [MCP Servers](#mcp-servers)
- [Network Policy](#network-policy)
- [CRDs](#crds)
- [Secrets](#secrets)
- [Values Reference](#values-reference)
- [Deployment](#deployment)
- [Local Rendering](#local-rendering)
- [Image Strategy](#image-strategy)

---

## Overview

The agent platform runs [Goose](https://github.com/block/goose) AI agents in
ephemeral Kubernetes pods (sandboxes). Each agent job is submitted via a REST
API, queued in NATS JetStream, and executed in an isolated pod provisioned by
the agent-sandbox controller. Agents connect to a suite of MCP servers to
interact with cluster infrastructure (ArgoCD, SigNoz, Kubernetes, BuildBuddy,
etc.).

```
Client → agent-orchestrator REST API
           → NATS JetStream (job queue)
             → agent-sandbox controller (creates Sandbox pod)
               → Goose agent pod
                 → Context Forge MCP gateway
                   → MCP servers (signoz, kubernetes, argocd, buildbuddy, …)
```

---

## Architecture

### Traffic flows

| Source | Destination | Purpose |
| ------------------------------------ | ----------------------------------- | ----------------------------------------- |
| Envoy Gateway (Cloudflare) | `agent-orchestrator :8080` | External job submission via HTTPRoute |
| `agent-orchestrator` | NATS `:4222` | Job queuing |
| `agent-orchestrator` | Kubernetes API | Sandbox creation / status polling |
| Goose sandbox pod | Context Forge gateway | MCP tool calls |
| Goose sandbox pod | Internet | Code checkout, npm, pip, GitHub API, etc. |
| MCP server registration jobs | Context Forge gateway | Self-registration on deploy |

### Component interactions

```
┌─────────────────────────────────────────────────────────────────┐
│  namespace: agent-platform                                      │
│                                                                 │
│  ┌──────────────────────┐     ┌──────────────────────────────┐  │
│  │  agent-orchestrator  │────▶│  NATS JetStream              │  │
│  │  (REST API / Go)     │     └──────────────────────────────┘  │
│  └──────────────────────┘                                       │
│           │ creates Sandbox CRs                                 │
│           ▼                                                     │
│  ┌──────────────────────┐     ┌──────────────────────────────┐  │
│  │  agent-sandbox       │────▶│  Goose sandbox pods          │  │
│  │  controller          │     │  (SandboxTemplate: goose-    │  │
│  └──────────────────────┘     │   agent + WarmPool)          │  │
│                               └──────────────────────────────┘  │
│                                          │ MCP calls            │
│                                          ▼                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  MCP servers                                             │   │
│  │  signoz-mcp · buildbuddy-mcp · kubernetes-mcp           │   │
│  │  argocd-mcp · todo-mcp · agent-orchestrator-mcp         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │ MCP gateway proxy
         ▼
  namespace: mcp
  Context Forge gateway  (deployed separately — see projects/mcp/)
```

---

## Components

| Subchart | Description | Enabled |
| ------------------------------ | ----------------------------------------------------------------- | ------- |
| `agent-platform-mcp-servers` | MCP server deployments with optional Context Forge registration | ✅ |
| `agent-orchestrator` | REST API + NATS-backed queue for Goose agent jobs | ✅ |
| `goose-sandboxes` | SandboxTemplate + WarmPool for ephemeral Goose agent pods | ✅ |
| `agent-sandbox` | SandboxTemplate CRDs (`sandboxes.agents.x-k8s.io`) + controller | ✅ |
| `nats` | NATS JetStream (upstream chart) | ✅ |

> **Not in this chart:** Context Forge and MCP OAuth Proxy are deployed
> separately in the `mcp` namespace. See `projects/mcp/` for their ArgoCD
> Applications.

---

## MCP Servers

The `agent-platform-mcp-servers` subchart deploys any number of MCP servers
via the `servers` list. Each server gets its own Deployment, Service,
ServiceAccount, optional ClusterRole, and optional post-install registration
Job.

### Servers deployed in homelab

| Server | Image | Port | Registered |
| ------------------------ | ------------------------------------------------- | ----- | ---------- |
| `signoz-mcp` | `docker.io/signoz/signoz-mcp-server` | 8000 | ✅ |
| `buildbuddy-mcp` | `ghcr.io/jomcgi/homelab/…/buildbuddy-mcp` | 8000 | ✅ |
| `kubernetes-mcp` | `ghcr.io/containers/kubernetes-mcp-server` | 8080 | ✅ |
| `argocd-mcp` | `ghcr.io/argoproj-labs/mcp-for-argocd` | 3000 | ✅ |
| `todo-mcp` | `ghcr.io/jomcgi/homelab/…/todo-mcp` | 8000 | ✅ |
| `agent-orchestrator-mcp` | `ghcr.io/jomcgi/homelab/…/agent-orchestrator-mcp` | 8000 | ✅ |

### Adding a new MCP server

Add an entry to `servers` in `deploy/values.yaml`:

```yaml
agent-platform-mcp-servers:
  servers:
    - name: my-mcp-server
      image:
        repository: ghcr.io/example/my-mcp-server
        tag: "v1.0.0"
      port: 8080
      registration:
        enabled: true
        transport: STREAMABLEHTTP   # STREAMABLEHTTP | SSE | STDIO
      alert:
        enabled: true
        url: "http://my-mcp-server.agent-platform.svc.cluster.local:8080/health"
```

For a stdio server wrapped in an HTTP translation sidecar:

```yaml
agent-platform-mcp-servers:
  servers:
    - name: stdio-mcp-server
      translate:
        enabled: true
        command: "uvx my-mcp-server"
        port: 8080
      writableTmp: true
      secret:
        name: my-secret
        itemPath: "vaults/k8s-homelab/items/my-secret"
      registration:
        enabled: true
        transport: STREAMABLEHTTP
```

---

## Network Policy

When `networkPolicy.enabled: true`, the chart deploys a **default-deny** baseline
plus per-service allow rules:

| Policy | Allows |
| ---------------------------------- | -------------------------------------------------------- |
| `netpol-default-deny` | Denies all ingress/egress by default |
| `netpol-allow-dns` | Egress to kube-dns `:53` (UDP/TCP) |
| `netpol-orchestrator` | Orchestrator → NATS, K8s API; Envoy Gateway → Orchestrator |
| `netpol-nats` | NATS ingress from orchestrator only |
| `netpol-mcp-servers` | MCP server ingress from Context Forge gateway |
| `netpol-sandbox` | Sandbox egress to MCP servers + internet |

> **Homelab note:** NetworkPolicies are **disabled** in the live cluster
> (`networkPolicy.enabled: false` in `deploy/values.yaml`) because Linkerd
> mTLS delivers traffic on port 4143, causing NetworkPolicies to silently drop
> meshed traffic. Application-layer auth is used instead.

---

## CRDs

The `agent-sandbox` subchart installs four CRDs from its `crds/` directory:

| CRD | Purpose |
| --------------------------------------------- | ---------------------------------- |
| `sandboxes.agents.x-k8s.io` | Individual sandbox pod lifecycle |
| `sandboxclaims.extensions.agents.x-k8s.io` | Claim a sandbox from a pool |
| `sandboxtemplates.extensions.agents.x-k8s.io` | Template for sandbox pods |
| `sandboxwarmpools.extensions.agents.x-k8s.io` | Pre-warmed sandbox pool |

### Parallel install (CRDs already present)

If another release already owns these CRDs (e.g. a `cluster-critical` release),
disable CRD installation and the controller:

```yaml
# deploy/values.yaml
agent-sandbox:
  installCRDs: false
  deployController: false
```

With ArgoCD also add to the Application:

```yaml
spec:
  source:
    helm:
      skipCrds: true
```

---

## Secrets

All secrets are managed via the **1Password Operator** (`OnePasswordItem` CRD).
No secrets are hardcoded — never add plaintext credentials to `values.yaml` or
`deploy/values.yaml`.

| Secret | Purpose | 1Password item |
| ----------------------- | ------------------------------------------ | ----------------------- |
| `claude-auth` | Claude API token for Goose agents | `litellm-claude-auth` |
| `agent-secrets` | Agent-level secrets (GitHub tokens, etc.) | `agent-secrets` |
| `goose-mcp-tokens` | MCP bearer tokens for Goose | `goose-mcp-tokens` |
| `context-forge-gateway` | Context Forge admin credentials | `context-forge` |
| Per-server secrets | Injected as `envFrom` into MCP server pods | Defined per server in `servers[].secret` |

To use 1Password-managed secrets for sandbox pods:

```yaml
goose-sandboxes:
  secrets:
    useOnePassword: true
    claudeAuth:
      onePasswordItem: litellm-claude-auth
      vault: k8s-homelab
    agentSecrets:
      onePasswordItem: agent-secrets
      vault: k8s-homelab
    mcpTokens:
      onePasswordItem: goose-mcp-tokens
      vault: k8s-homelab
```

---

## Values Reference

### Top-level values

| Key | Type | Default | Description |
| ------------------------------------ | ------ | ------- | ----------------------------------------------- |
| `networkPolicy.enabled` | bool | `true` | Deploy default-deny NetworkPolicies |
| `networkPolicy.apiServerCidr` | string | `""` | Restrict K8s API egress to this CIDR |
| `networkPolicy.gateway.namespace` | string | `mcp` | Namespace of the Context Forge gateway |

### agent-platform-mcp-servers

| Key | Type | Default | Description |
| ------------------------------------------------ | ------ | ------------- | --------------------------------------------------------- |
| `agent-platform-mcp-servers.enabled` | bool | `true` | Deploy MCP servers |
| `agent-platform-mcp-servers.servers` | list | `[]` | List of MCP server definitions (see above) |
| `agent-platform-mcp-servers.gateway.url` | string | `""` | Context Forge URL (required when any server registers) |
| `agent-platform-mcp-servers.translate.image.tag` | string | `v1.0.0-RC1` | Shared stdio→HTTP translation sidecar image tag |

### agent-orchestrator

| Key | Type | Default | Description |
| ------------------------------------------------- | ------ | ------------- | -------------------------------------------------- |
| `agent-orchestrator.enabled` | bool | `true` | Deploy the orchestrator |
| `agent-orchestrator.replicaCount` | int | `1` | Replica count |
| `agent-orchestrator.config.sandboxTemplate` | string | `goose-agent` | SandboxTemplate name for agent jobs |
| `agent-orchestrator.config.maxConcurrent` | string | `"5"` | Max concurrently running agent jobs |
| `agent-orchestrator.config.maxRetries` | string | `"2"` | Max retries on job failure |
| `agent-orchestrator.config.jobInactivityTimeout` | string | `"10m"` | Cancel job after this long with no agent activity |
| `agent-orchestrator.config.jobMaxDuration` | string | `"168h"` | Hard cap on job duration (7 days) |
| `agent-orchestrator.config.natsUrl` | string | `""` | Auto-derived from release name when empty |
| `agent-orchestrator.config.sandboxNamespace` | string | `""` | Auto-derived from release namespace when empty |
| `agent-orchestrator.httpRoute.enabled` | bool | `false` | Expose via Envoy Gateway HTTPRoute |
| `agent-orchestrator.httpRoute.hostname` | string | `""` | Hostname (e.g. `agents.example.com`) |

### goose-sandboxes

| Key | Type | Default | Description |
| ------------------------------------------------------------- | ------ | ------------------- | --------------------------------------------------------- |
| `goose-sandboxes.enabled` | bool | `true` | Deploy the SandboxTemplate + WarmPool |
| `goose-sandboxes.sandboxTemplate.name` | string | `goose-agent` | SandboxTemplate resource name |
| `goose-sandboxes.sandboxTemplate.image.repository` | string | — | Goose agent container image |
| `goose-sandboxes.sandboxTemplate.env.gooseProvider` | string | `claude-code` | LLM provider for Goose |
| `goose-sandboxes.sandboxTemplate.env.gooseModel` | string | `claude-sonnet-4-6` | Model name |
| `goose-sandboxes.sandboxTemplate.env.contextForgeUrl` | string | `""` | MCP gateway URL injected into agent pods |
| `goose-sandboxes.sandboxTemplate.workspace.storageClassName` | string | `""` | StorageClass for the 20 Gi agent workspace PVC |
| `goose-sandboxes.warmPool.size` | int | `1` | Number of pre-warmed sandbox pods |
| `goose-sandboxes.secrets.useOnePassword` | bool | `false` | Source secrets from 1Password Operator |

### agent-sandbox

| Key | Type | Default | Description |
| --------------------------------- | ---- | ------- | --------------------------------------------------------- |
| `agent-sandbox.enabled` | bool | `true` | Deploy CRDs + controller |
| `agent-sandbox.installCRDs` | bool | `true` | Install CRDs (set `false` for parallel installs) |
| `agent-sandbox.deployController` | bool | `true` | Deploy the controller (set `false` for parallel installs) |

### nats

| Key | Type | Default | Description |
| ------------------------------------------------------ | ------ | ------- | ----------------------------------------- |
| `nats.enabled` | bool | `true` | Deploy NATS JetStream |
| `nats.config.jetstream.fileStore.pvc.size` | string | `10Gi` | Persistent volume size for JetStream |
| `nats.config.jetstream.fileStore.pvc.storageClassName` | string | `""` | StorageClass for NATS PVC |

---

## Deployment

The chart is published to `oci://ghcr.io/jomcgi/homelab/charts/agent-platform`
by CI on every merge to `main`. The ArgoCD Application in
`projects/agent_platform/deploy/application.yaml` pulls the chart from the OCI
registry and overlays environment-specific values from
`projects/agent_platform/deploy/values.yaml`.

**ArgoCD Image Updater** watches the chart OCI artifact and automatically bumps
`targetRevision` in the Application when a new chart version is pushed.

To change cluster configuration, edit `deploy/values.yaml` and push — ArgoCD
auto-syncs within ~5–10 seconds. **Never use `kubectl apply` or `helm install`
directly.**

---

## Local Rendering

Render the full manifest stack locally to verify changes before committing:

```bash
# Update subchart dependencies
helm dependency update projects/agent_platform/chart/

# Render with both chart defaults and env values
helm template agent-platform projects/agent_platform/chart/ \
  -f projects/agent_platform/chart/values.yaml \
  -f projects/agent_platform/deploy/values.yaml \
  --namespace agent-platform
```

---

## Image Strategy

**Custom images** (orchestrator, buildbuddy-mcp, todo-mcp, goose-agent, etc.)
are built via Bazel + apko (no Dockerfiles) and pinned using Bazel's
`helm_chart(images={})` map. This produces a `values-generated.yaml` baked into
the chart `.tgz` at build time. Images are dual-arch (linux/amd64 + linux/arm64).

**Upstream images** (NATS, Context Forge translate sidecar, kubernetes-mcp-server,
argocd-mcp, signoz-mcp-server) are pinned with explicit `repository` + `tag` in
`values.yaml`. ArgoCD Image Updater can optionally pin these to a digest via the
`imageUpdater` stanza on each server entry.
