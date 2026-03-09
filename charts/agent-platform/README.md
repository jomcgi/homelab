# agent-platform

MVP agent platform umbrella chart — ties together NATS messaging, the agent orchestrator, and Goose sandbox infrastructure.

## Prerequisites

### 1. agent-sandbox controller

The `agent-sandbox` controller manages the `SandboxTemplate` and `WarmPool` CRDs and must be installed into its own namespace **before** this chart:

```bash
helm install agent-sandbox charts/agent-sandbox/ \
  -n agent-sandbox-system --create-namespace
```

### 2. Secrets (non-1Password environments)

If `goose-sandboxes.secrets.useOnePassword` is `false` (the default), create these secrets manually in the release namespace before installing:

```bash
kubectl create secret generic claude-auth \
  --from-literal=CLAUDE_AUTH_TOKEN=<your-claude-oauth-token> \
  -n <namespace>

kubectl create secret generic agent-secrets \
  --from-literal=GITHUB_TOKEN=<your-github-token> \
  -n <namespace>

kubectl create secret generic goose-mcp-tokens \
  --from-literal=CI_DEBUG_MCP_TOKEN="" \
  -n <namespace>
```

## Installation

```bash
# Build subchart dependencies first
helm dependency build charts/agent-platform/

# Install with homelab overrides
helm upgrade --install agent-platform charts/agent-platform/ \
  -f charts/agent-platform/values-homelab.yaml \
  -n agent-platform --create-namespace
```

## Required Values

The following values have no sensible defaults and **must** be provided in an environment-specific values file:

| Value | Description | Example |
|-------|-------------|---------|
| `nats.nats.config.jetstream.fileStore.pvc.storageClassName` | Storage class for NATS JetStream PVC | `longhorn` |
| `agent-orchestrator.config.natsUrl` | NATS connection URL | `nats://agent-platform-nats:4222` |
| `agent-orchestrator.config.sandboxNamespace` | Namespace where sandboxes are created | `agent-platform` |
| `goose-sandboxes.sandboxTemplate.env.repoOwner` | GitHub repository owner | `jomcgi` |
| `goose-sandboxes.sandboxTemplate.env.repoName` | GitHub repository name | `homelab` |
| `goose-sandboxes.sandboxTemplate.workspace.storageClassName` | Storage class for agent workspace PVCs | `longhorn` |

## Architecture

```
agent-platform
├── nats              — JetStream messaging backbone (job queue + state)
├── agent-orchestrator — REST API + job scheduler (submits SandboxRun CRs)
└── goose-sandboxes   — SandboxTemplate, WarmPool, RBAC, and secrets
```

The orchestrator receives job requests via HTTP and enqueues them to NATS JetStream. The agent-sandbox controller watches for `SandboxRun` objects created by the orchestrator and provisions ephemeral Goose agent pods from the `SandboxTemplate`.

The `WarmPool` keeps a pre-warmed pool of sandbox pods ready to reduce cold-start latency.

> **Note:** Grafana dashboards will be added via the `mcp-servers` chart pattern in a future release.

## Subcharts

| Chart | Version | Source |
|-------|---------|--------|
| `nats` | `1.0.0` | `file://../nats` |
| `agent-orchestrator` | `0.1.0` | `file://../agent-orchestrator` |
| `goose-sandboxes` | `0.1.0` | `file://../goose-sandboxes` |

## Values Reference

See [`values.yaml`](./values.yaml) for all available options with inline documentation. For a complete homelab deployment example, see [`values-homelab.yaml`](./values-homelab.yaml).
