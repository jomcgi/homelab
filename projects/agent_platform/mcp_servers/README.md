# mcp-servers

Deploys MCP servers with optional protocol translation, Context Forge gateway registration, and SigNoz HTTPCheck alerts.

## How it works

The chart iterates over a `servers` array in values.yaml. Each entry generates:

- **Deployment** — single container (native HTTP) or dual-container with translate sidecar (stdio→HTTP)
- **Service** — ClusterIP exposing the MCP server port
- **ServiceAccount**
- **OnePasswordItem** — (if `secret` is set) creates a K8s Secret from 1Password
- **Registration Job** — (if `registration.enabled`) Helm post-install/upgrade hook that registers with Context Forge gateway
- **Alert ConfigMap** — (if `alert.enabled`) HTTPCheck alert picked up by the SigNoz dashboard sidecar
- **ImageUpdater** — (if `imageUpdater.enabled`) ArgoCD Image Updater for digest-based auto-updates
- **RBAC** — (if `rbac` is set) ClusterRoleBinding and/or namespaced RoleBindings

## Adding a new MCP server

### 1. Add the server entry

Add an entry to the `servers` array in `overlays/prod/mcp-servers/values.yaml`:

```yaml
- name: my-mcp-server
  image:
    repository: ghcr.io/jomcgi/homelab/projects/agent_platform/my_mcp_server
    tag: "main"
  port: 8000
  env:
    - name: MY_ENV_VAR
      value: "some-value"
  secret:
    name: my-mcp-server # K8s Secret name
    itemPath: "vaults/k8s-homelab/items/my-mcp-server" # 1Password vault path
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 128Mi
  translate:
    enabled: false # true for stdio servers, false for native HTTP
  registration:
    enabled: true
    transport: "STREAMABLEHTTP"
  alert:
    enabled: true
    url: "http://my-mcp-server.mcp-servers.svc.cluster.local:8000/health"
```

### 2. Create the 1Password item

Create an item in the `k8s-homelab` vault with the name matching your `secret.itemPath`. Add fields for any secret environment variables (e.g., API keys). The 1Password Operator will create a K8s Secret and inject all fields as env vars via `envFrom`.

### 3. Enable ArgoCD Image Updater (for in-repo images)

If the image is built in this repo (pushed via `//bazel/images:push_all`), add `imageUpdater.enabled: true` to your server entry:

```yaml
imageUpdater:
  enabled: true
```

The chart auto-generates the ImageUpdater resource with the correct `servers[N]` array index. The overlay's `imageUpdater.writeBackTarget` must also be set:

```yaml
imageUpdater:
  writeBackTarget: "helmvalues:../../overlays/prod/mcp-servers/values.yaml"
```

For third-party images (e.g., `docker.io/signoz/signoz-mcp-server`), skip the image updater and pin to a specific version tag.

### 4. Render and verify

```bash
helm template mcp-servers charts/mcp-servers/ \
  -f overlays/prod/mcp-servers/values.yaml
```

## Native HTTP vs translate sidecar

| Mode              | `translate.enabled` | Use when                                                                        |
| ----------------- | ------------------- | ------------------------------------------------------------------------------- |
| Native HTTP       | `false`             | Server exposes streamable-HTTP natively (e.g., FastMCP with `transport="http"`) |
| Translate sidecar | `true`              | Server only supports stdio; the IBM translate sidecar wraps it as HTTP          |

For translate mode, also set:

- `translate.command` — the stdio command to run (e.g., `python3 -m my_server`)
- `translate.port` — sidecar HTTP port (default 8080)

## Context Forge registration

When `registration.enabled: true`, a Helm post-install/upgrade Job:

1. Waits for the Context Forge gateway to be healthy
2. Mints a short-lived JWT using the gateway's `JWT_SECRET_KEY`
3. Deletes any existing gateway entry with the same name (by UUID)
4. Registers the server's ClusterIP service URL with the gateway

The server then appears as a virtual tool provider in Context Forge at `https://mcp.jomcgi.dev/mcp`.

## Alert defaults

HTTPCheck alerts use these defaults (overridable per server):

| Setting      | Default               | Description                        |
| ------------ | --------------------- | ---------------------------------- |
| `evalWindow` | `10m0s`               | Time window for evaluation         |
| `frequency`  | `2m0s`                | Check frequency                    |
| `matchType`  | `5`                   | Consecutive failures before firing |
| `severity`   | `critical`            | Alert severity                     |
| `channels`   | `[pagerduty-homelab]` | Notification channels              |
