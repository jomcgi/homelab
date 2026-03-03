# Design: Kubernetes and ArgoCD MCP Servers

## Goal

Deploy third-party Kubernetes and ArgoCD MCP servers to the homelab cluster, registered with the Context Forge gateway, using the existing `charts/mcp-servers/` Helm chart.

## Approach

Two focused best-of-breed servers, each as a separate entry in the mcp-servers chart values:

1. **Red Hat kubernetes-mcp-server** — native Go binary, direct K8s API access
2. **argoproj-labs mcp-for-argocd** — official ArgoCD MCP, direct ArgoCD API access

This matches the existing pattern of focused, separate MCP servers (SigNoz, BuildBuddy).

## Chart Enhancement

The `charts/mcp-servers/` chart needs two additions:

### 1. Container args support

The deployment template's native server path doesn't support custom `args`. The kubernetes-mcp-server needs `--disable-destructive` passed via args.

Add to `deployment.yaml` (native server container, after image line):

```yaml
{{- with .args }}
args:
  {{- toYaml . | nindent 12 }}
{{- end }}
```

### 2. ClusterRole creation

The RBAC template only creates ClusterRoleBindings. The kubernetes-mcp-server needs a custom ClusterRole for read + exec permissions.

Add to `rbac.yaml`:

```yaml
{{- if $server.rbac.clusterRoleRules }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-{{ $server.name }}
rules:
  {{- toYaml $server.rbac.clusterRoleRules | nindent 2 }}
{{- end }}
```

Update ClusterRoleBinding to use the generated ClusterRole name when `clusterRoleRules` is defined:

```yaml
roleRef:
  kind: ClusterRole
  name: {{ if $server.rbac.clusterRoleRules }}mcp-{{ $server.name }}{{ else }}{{ $server.rbac.clusterRole }}{{ end }}
```

## Server 1: Kubernetes MCP

| Setting | Value |
|---------|-------|
| Image | `ghcr.io/containers/kubernetes-mcp-server:latest` |
| Port | 8080 |
| Args | `["--port", "8080", "--disable-destructive"]` |
| Transport | Streamable HTTP (native at `/mcp`) |
| User | 65532 (upstream Dockerfile default) |

### RBAC

Custom ClusterRole with read + non-destructive debug access:

```yaml
clusterRoleRules:
  - apiGroups: ["", "apps", "batch", "networking.k8s.io", "rbac.authorization.k8s.io"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/exec", "pods/portforward", "pods/log"]
    verbs: ["create", "get"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list"]
```

Defense in depth: `--disable-destructive` prevents mutations at the application layer, ClusterRole prevents them at the K8s API layer.

No 1Password secret needed — uses in-cluster ServiceAccount token.

## Server 2: ArgoCD MCP

| Setting | Value |
|---------|-------|
| Image | `ghcr.io/argoproj-labs/mcp-for-argocd:v0.5.0` |
| Port | 3000 |
| Transport | HTTP stream (CMD: `node dist/index.js http`) |
| writableTmp | true (Node.js needs tmp access) |

### Environment

```yaml
env:
  - name: ARGOCD_BASE_URL
    value: "http://argocd-server.argocd.svc.cluster.local:80"
```

### Secret

1Password item `argocd-mcp` in `vaults/k8s-homelab` containing `ARGOCD_API_TOKEN`.

No K8s RBAC needed — talks to ArgoCD API via token, not K8s API.

## Gateway Registration

Both servers registered with Context Forge:

```yaml
registration:
  enabled: true
  transport: "STREAMABLEHTTP"
```

## Health Check Alerts

Both servers get SigNoz HTTPCheck alerts:

```yaml
alert:
  enabled: true
  url: "http://<name>.mcp-servers.svc.cluster.local:<port>/health"
```

## Decisions

- **Third-party images over custom** — faster to ship, maintained by upstream
- **Separate servers over combined** — granular RBAC, native APIs, defense in depth
- **Red Hat over alexei-led** — native Go K8s API vs shell wrapper, better security
- **argoproj-labs over severity1** — official Argo project implementation
- **ClusterRole in chart** — avoids managing RBAC separately, keeps everything in values.yaml
