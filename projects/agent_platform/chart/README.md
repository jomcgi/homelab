# agent-platform

Umbrella Helm chart bundling the core agent platform components into a single
ArgoCD Application.

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
- [Configuration](#configuration)
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

| Source                       | Destination                | Purpose                                   |
| ---------------------------- | -------------------------- | ----------------------------------------- |
| Envoy Gateway (Cloudflare)   | `agent-orchestrator :8080` | External job submission via HTTPRoute     |
| `agent-orchestrator`         | NATS `:4222`               | Job queuing                               |
| `agent-orchestrator`         | Kubernetes API             | Sandbox creation / status polling         |
| Goose sandbox pod            | Context Forge gateway      | MCP tool calls                            |
| Goose sandbox pod            | Internet                   | Code checkout, npm, pip, GitHub API, etc. |
| MCP server registration jobs | Context Forge gateway      | Self-registration on deploy               |

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

| Subchart                     | Description                                                     | Enabled |
| ---------------------------- | --------------------------------------------------------------- | ------- |
| `agent-platform-mcp-servers` | MCP server deployments with optional Context Forge registration | ✅      |
| `agent-orchestrator`         | REST API + NATS-backed queue for Goose agent jobs               | ✅      |
| `goose-sandboxes`            | SandboxTemplate + WarmPool for ephemeral Goose agent pods       | ✅      |
| `agent-sandbox`              | SandboxTemplate CRDs (`sandboxes.agents.x-k8s.io`) + controller | ✅      |
| `nats`                       | NATS JetStream (upstream chart)                                 | ✅      |

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

See `deploy/values.yaml` for the full list of servers with their images, ports,
and configuration. Currently deployed: `signoz-mcp`, `buildbuddy-mcp`,
`kubernetes-mcp`, `argocd-mcp`, `todo-mcp`, `agent-orchestrator-mcp`.

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
        transport: STREAMABLEHTTP # STREAMABLEHTTP | SSE | STDIO
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

| Policy                | Allows                                                     |
| --------------------- | ---------------------------------------------------------- |
| `netpol-default-deny` | Denies all ingress/egress by default                       |
| `netpol-allow-dns`    | Egress to kube-dns `:53` (UDP/TCP)                         |
| `netpol-orchestrator` | Orchestrator → NATS, K8s API; Envoy Gateway → Orchestrator |
| `netpol-nats`         | NATS ingress from orchestrator only                        |
| `netpol-mcp-servers`  | MCP server ingress from Context Forge gateway              |
| `netpol-sandbox`      | Sandbox egress to MCP servers + internet                   |

> **Homelab note:** NetworkPolicies are **disabled** in the live cluster
> (`networkPolicy.enabled: false` in `deploy/values.yaml`) because Linkerd
> mTLS delivers traffic on port 4143, causing NetworkPolicies to silently drop
> meshed traffic. Application-layer auth is used instead.

---

## CRDs

The `agent-sandbox` subchart installs four CRDs from its `crds/` directory:

| CRD                                           | Purpose                          |
| --------------------------------------------- | -------------------------------- |
| `sandboxes.agents.x-k8s.io`                   | Individual sandbox pod lifecycle |
| `sandboxclaims.extensions.agents.x-k8s.io`    | Claim a sandbox from a pool      |
| `sandboxtemplates.extensions.agents.x-k8s.io` | Template for sandbox pods        |
| `sandboxwarmpools.extensions.agents.x-k8s.io` | Pre-warmed sandbox pool          |

### Parallel install (CRDs already present)

If another release already owns these CRDs (e.g. a `cluster-critical` release),
disable CRD installation and the controller:

```yaml
# deploy/values.yaml
agent-sandbox:
  installCRDs: false
  deployController: false
```

With ArgoCD also add `skipCrds` to the chart source in the Application
(this chart uses multi-source, so target the correct `sources[]` entry):

```yaml
spec:
  sources:
    - repoURL: ghcr.io/jomcgi/homelab/charts
      chart: agent-platform
      helm:
        skipCrds: true
```

---

## Secrets

All secrets are managed via the **1Password Operator** (`OnePasswordItem` CRD).
No secrets are hardcoded — never add plaintext credentials to `values.yaml` or
`deploy/values.yaml`.

| Secret                  | Purpose                                    | 1Password item                           |
| ----------------------- | ------------------------------------------ | ---------------------------------------- |
| `claude-auth`           | Claude API token for Goose agents          | `litellm-claude-auth`                    |
| `agent-secrets`         | Agent-level secrets (GitHub tokens, etc.)  | `agent-secrets`                          |
| `goose-mcp-tokens`      | MCP bearer tokens for Goose                | `goose-mcp-tokens`                       |
| `context-forge-gateway` | Context Forge admin credentials            | `context-forge`                          |
| Per-server secrets      | Injected as `envFrom` into MCP server pods | Defined per server in `servers[].secret` |

See the `goose-sandboxes.secrets` section in `values.yaml` for 1Password
integration configuration.

---

## Configuration

See [`values.yaml`](values.yaml) for the full schema with defaults and comments.
Environment-specific overrides live in
[`deploy/values.yaml`](../../../projects/agent_platform/deploy/values.yaml).

---

## Deployment

The chart is published to `oci://ghcr.io/jomcgi/homelab/projects/agent_platform/chart`
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
