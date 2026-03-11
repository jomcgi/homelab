# MCP Namespace Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract Context Forge and MCP OAuth Proxy from the agent-platform umbrella chart into a new `projects/mcp/` project deploying to a dedicated `mcp` namespace, fixing the PreSync hook ordering issue blocking ArgoCD sync.

**Architecture:** Context Forge (mcp-stack wrapper) and MCP OAuth Proxy become independent ArgoCD apps in `projects/mcp/{context-forge-gateway,oauth-proxy}/`, each with their own `chart/` and `deploy/` directories, deploying to namespace `mcp`. The agent-platform umbrella chart retains MCP servers, orchestrator, sandboxes, agent-sandbox, and NATS. Cross-namespace NetworkPolicies are made configurable via a `gateway` values block so the MCP servers chart can target Context Forge in any namespace.

**Tech Stack:** Helm, ArgoCD, Kubernetes NetworkPolicies, Kustomize, Bazel (BUILD files)

---

## Background

The agent-platform umbrella chart (v0.7.0) includes Context Forge as a subchart. Context Forge's upstream `mcp-stack` chart uses a Helm PreSync hook for database migration, but the hook depends on Secrets/ConfigMaps created during the Sync phase. Under ArgoCD, PreSync hooks run _before_ resources are applied — causing `CreateContainerConfigError: secret "agent-platform-mcp-stack-gateway-secret" not found`.

Extracting Context Forge into its own ArgoCD app (Git-sourced, standard Helm install) avoids this PreSync ordering issue entirely, since ArgoCD manages the full resource set as a single sync wave.

## Key Files Reference

| Current Path                                                                | Purpose                                           |
| --------------------------------------------------------------------------- | ------------------------------------------------- |
| `projects/agent_platform/chart/Chart.yaml`                                  | Umbrella chart dependencies                       |
| `projects/agent_platform/chart/values.yaml`                                 | Umbrella chart defaults                           |
| `projects/agent_platform/chart/context-forge/`                              | Context Forge subchart (to extract)               |
| `projects/agent_platform/chart/mcp-oauth-proxy/`                            | OAuth Proxy subchart (to extract)                 |
| `projects/agent_platform/chart/templates/netpol-context-forge.yaml`         | CF NetworkPolicies (to remove)                    |
| `projects/agent_platform/chart/templates/netpol-mcp-oauth-proxy.yaml`       | Proxy NetworkPolicies (to remove)                 |
| `projects/agent_platform/chart/templates/netpol-mcp-servers.yaml`           | MCP server registration egress (to update)        |
| `projects/agent_platform/chart/templates/netpol-sandbox.yaml`               | Sandbox → CF egress (to update)                   |
| `projects/agent_platform/chart/templates/NOTES.txt`                         | Install notes (to simplify)                       |
| `projects/agent_platform/deploy/values.yaml`                                | Environment overrides (to trim CF/proxy sections) |
| `projects/agent_platform/kustomization.yaml`                                | Kustomize aggregator                              |
| `projects/agent_platform/chart/mcp-servers/values.yaml`                     | MCP servers chart defaults                        |
| `projects/agent_platform/chart/mcp-servers/templates/registration-job.yaml` | Registration post-install hook                    |

---

### Task 1: Create `projects/mcp/` Directory Structure

**Files:**

- Create: `projects/mcp/context-forge-gateway/chart/Chart.yaml`
- Create: `projects/mcp/context-forge-gateway/chart/values.yaml`
- Create: `projects/mcp/context-forge-gateway/chart/BUILD`
- Create: `projects/mcp/context-forge-gateway/chart/templates/onepassworditem.yaml`
- Create: `projects/mcp/context-forge-gateway/chart/templates/networkpolicy.yaml`
- Move: `projects/agent_platform/chart/context-forge/charts/` → `projects/mcp/context-forge-gateway/chart/charts/` (mcp-stack tgz)
- Create: `projects/mcp/context-forge-gateway/deploy/application.yaml`
- Create: `projects/mcp/context-forge-gateway/deploy/kustomization.yaml`
- Create: `projects/mcp/context-forge-gateway/deploy/values.yaml`

**Step 1: Create the Context Forge gateway chart**

The chart structure is: a thin wrapper around the upstream `mcp-stack` chart (OCI dependency from GHCR), plus a 1Password secret template and NetworkPolicies for internal traffic.

Copy from `projects/agent_platform/chart/context-forge/`:

- `Chart.yaml` — keep as-is (already references mcp-stack dependency)
- `Chart.lock` — keep
- `charts/` — keep (contains mcp-stack tgz)
- `values.yaml` — keep defaults, remove the `secret:` block (move to its own template)
- `BUILD` — keep (helm_chart rule)
- `templates/` — create if not exists

Add new templates:

1. `templates/onepassworditem.yaml` — 1Password secret for JWT keys (from values.secret)
2. `templates/networkpolicy.yaml` — Context Forge internal traffic (mcpgateway ↔ postgres ↔ redis ↔ migration), ingress from MCP servers namespace + sandboxes namespace, ingress from OAuth proxy

**Step 2: Create the ArgoCD Application**

`deploy/application.yaml` — Git-sourced (not OCI), pointing to `projects/mcp/context-forge-gateway/chart`, deploying to namespace `mcp`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: context-forge-gateway
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/mcp/context-forge-gateway/chart
    targetRevision: HEAD
    helm:
      releaseName: context-forge-gateway
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: mcp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 3: Create deploy/kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - application.yaml
```

**Step 4: Create deploy/values.yaml**

Extract Context Forge values from `projects/agent_platform/deploy/values.yaml` (lines 6-22):

```yaml
mcp-stack:
  mcpContextForge:
    config:
      PLATFORM_ADMIN_EMAIL: "admin@jomcgi.dev"
    resources:
      requests:
        cpu: 50m
        memory: 1Gi
      limits:
        cpu: 200m
        memory: 1Gi
  postgres:
    persistence:
      storageClassName: longhorn

secret:
  itemPath: "vaults/k8s-homelab/items/context-forge"
```

**Step 5: Commit**

```
feat(mcp): add context-forge-gateway as standalone ArgoCD app in mcp namespace
```

---

### Task 2: Create `projects/mcp/oauth-proxy/`

**Files:**

- Move: `projects/agent_platform/chart/mcp-oauth-proxy/` → `projects/mcp/oauth-proxy/chart/`
- Create: `projects/mcp/oauth-proxy/deploy/application.yaml`
- Create: `projects/mcp/oauth-proxy/deploy/kustomization.yaml`
- Create: `projects/mcp/oauth-proxy/deploy/values.yaml`
- Create: `projects/mcp/oauth-proxy/chart/templates/networkpolicy.yaml`

**Step 1: Move the chart**

Move the entire `mcp-oauth-proxy/` subchart directory to `projects/mcp/oauth-proxy/chart/`.

**Step 2: Add NetworkPolicy template to the chart**

Create `chart/templates/networkpolicy.yaml` — adapted from the old `netpol-mcp-oauth-proxy.yaml`:

```yaml
{{- if .Values.networkPolicy.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ .Release.Name }}-ingress
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: mcp-oauth-proxy
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: envoy-gateway-system
      ports:
        - protocol: TCP
          port: 8080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ .Release.Name }}-egress
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: mcp-oauth-proxy
  policyTypes:
    - Egress
  egress:
    # → Google OIDC
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except: [10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16]
      ports:
        - { protocol: TCP, port: 443 }
    # → Context Forge (same namespace)
    - to:
        - podSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values: [mcpcontextforge, mcp-stack-mcpcontextforge]
      ports:
        - { protocol: TCP, port: 80 }
        - { protocol: TCP, port: 8000 }
{{- end }}
```

Add `networkPolicy.enabled: true` default to `chart/values.yaml`.

**Step 3: Create ArgoCD Application**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mcp-oauth-proxy
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: projects/mcp/oauth-proxy/chart
    targetRevision: HEAD
    helm:
      releaseName: mcp-oauth-proxy
      valueFiles:
        - values.yaml
        - ../deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: mcp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 4: Create deploy/values.yaml**

Extract from `projects/agent_platform/deploy/values.yaml` (lines 25-27):

```yaml
secret:
  itemPath: "vaults/k8s-homelab/items/mcp-oauth-proxy"

config:
  # Context Forge is now in the same namespace
  MCP_SERVER_URL: "http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp"
```

**Step 5: Commit**

```
feat(mcp): add oauth-proxy as standalone ArgoCD app in mcp namespace
```

---

### Task 3: Make MCP Server Registration Gateway URL Configurable (Cross-Namespace)

**Files:**

- Modify: `projects/agent_platform/chart/mcp-servers/values.yaml`
- Modify: `projects/agent_platform/chart/templates/netpol-mcp-servers.yaml`
- Modify: `projects/agent_platform/chart/values.yaml`
- Modify: `projects/agent_platform/deploy/values.yaml`

**Step 1: Update MCP servers values.yaml gateway config**

The `gateway.url` in `mcp-servers/values.yaml` already exists and is overridden in deploy values. No schema change needed — the gateway URL just needs to point to the `mcp` namespace FQDN.

**Step 2: Update netpol-mcp-servers.yaml for cross-namespace**

Replace the `context-forge.enabled` conditional with a configurable gateway NetworkPolicy block. The registration egress and ingress policies should use `namespaceSelector` to target the `mcp` namespace.

New approach in `netpol-mcp-servers.yaml`:

```yaml
{{- if .Values.networkPolicy.enabled }}
{{- if (index .Values "agent-platform-mcp-servers" "enabled") }}
# MCP servers shared ingress: Context Forge gateway (cross-namespace) proxies
# tool calls and registration requests to servers.
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ .Release.Name }}-mcp-servers-ingress
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: mcp-server
  policyTypes:
    - Ingress
  ingress:
    {{- with .Values.networkPolicy.gateway }}
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ .namespace }}
          podSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values: {{ .podLabels | toYaml | nindent 18 }}
      ports:
        {{- range .ports }}
        - protocol: TCP
          port: {{ . }}
        {{- end }}
    {{- end }}
{{- if .Values.networkPolicy.gateway }}
---
# MCP servers → Context Forge registration egress (cross-namespace)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ .Release.Name }}-mcp-servers-registration-egress
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: mcp-server
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ .Values.networkPolicy.gateway.namespace }}
          podSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values: {{ .Values.networkPolicy.gateway.podLabels | toYaml | nindent 18 }}
      ports:
        {{- range .Values.networkPolicy.gateway.ports }}
        - protocol: TCP
          port: {{ . }}
        {{- end }}
{{- end }}
{{- end }}
{{- end }}
```

**Step 3: Add gateway config to umbrella values.yaml**

Add under `networkPolicy:`:

```yaml
networkPolicy:
  enabled: true
  apiServerCidr: ""
  # Context Forge gateway — used for MCP server registration and sandbox
  # tool-call egress policies. Set namespace to where Context Forge deploys.
  gateway:
    namespace: mcp
    podLabels:
      - mcpcontextforge
      - mcp-stack-mcpcontextforge
    ports:
      - 80
      - 8000
```

**Step 4: Update sandbox egress policy**

In `netpol-sandbox.yaml`, replace the `context-forge.enabled` conditional with the same `networkPolicy.gateway` config for cross-namespace egress to Context Forge.

**Step 5: Update deploy/values.yaml**

- Remove `context-forge:` section entirely
- Remove `mcp-oauth-proxy:` section entirely
- Update `agent-platform-mcp-servers.gateway.url` to cross-namespace FQDN:
  ```yaml
  gateway:
    url: "http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80"
  ```
- Update `goose-sandboxes.sandboxTemplate.env.contextForgeUrl` to:
  ```yaml
  contextForgeUrl: "http://context-forge-gateway-mcp-stack-mcpgateway.mcp.svc.cluster.local:80/mcp"
  ```
- Update MCP server health check URLs from `.agent-platform.svc.cluster.local` to keep as-is (servers stay in agent-platform namespace)

**Step 6: Commit**

```
refactor(agent-platform): make gateway NetworkPolicy configurable for cross-namespace access
```

---

### Task 4: Remove Context Forge and OAuth Proxy from Umbrella Chart

**Files:**

- Modify: `projects/agent_platform/chart/Chart.yaml` — remove context-forge and mcp-oauth-proxy dependencies
- Modify: `projects/agent_platform/chart/Chart.lock` — regenerate
- Delete: `projects/agent_platform/chart/context-forge/` (entire directory)
- Delete: `projects/agent_platform/chart/mcp-oauth-proxy/` (entire directory)
- Delete: `projects/agent_platform/chart/templates/netpol-context-forge.yaml`
- Delete: `projects/agent_platform/chart/templates/netpol-mcp-oauth-proxy.yaml`
- Modify: `projects/agent_platform/chart/values.yaml` — remove context-forge and mcp-oauth-proxy sections
- Modify: `projects/agent_platform/chart/templates/NOTES.txt` — remove CF/proxy sections
- Bump: `projects/agent_platform/chart/Chart.yaml` version to `0.8.0`

**Step 1: Remove dependencies from Chart.yaml**

Remove the `context-forge` and `mcp-oauth-proxy` entries from the `dependencies:` list.

**Step 2: Delete subchart directories**

```bash
rm -rf projects/agent_platform/chart/context-forge/
rm -rf projects/agent_platform/chart/mcp-oauth-proxy/
```

**Step 3: Delete unused NetworkPolicy templates**

```bash
rm projects/agent_platform/chart/templates/netpol-context-forge.yaml
rm projects/agent_platform/chart/templates/netpol-mcp-oauth-proxy.yaml
```

**Step 4: Clean up values.yaml**

Remove the `context-forge:` block (lines 21-99) and `mcp-oauth-proxy:` block (lines 101-148) from the umbrella chart's `values.yaml`.

**Step 5: Simplify NOTES.txt**

Remove the Context Forge and MCP OAuth Proxy sections. Replace with a note about the `mcp` namespace:

```
## Context Forge Gateway

Context Forge and MCP OAuth Proxy are deployed separately in the `mcp` namespace.
See projects/mcp/ for their ArgoCD applications.
```

**Step 6: Bump chart version to 0.8.0**

**Step 7: Regenerate Chart.lock**

```bash
helm dependency update projects/agent_platform/chart/
```

**Step 8: Commit**

```
refactor(agent-platform): remove context-forge and mcp-oauth-proxy from umbrella chart
```

---

### Task 5: Wire up Kustomize and Home-Cluster Discovery

**Files:**

- Create: `projects/mcp/kustomization.yaml`
- Modify: `projects/home-cluster/kustomization.yaml` (auto-generated, but verify)
- Update BUILD files if needed

**Step 1: Create projects/mcp/kustomization.yaml**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ./context-forge-gateway/deploy
  - ./oauth-proxy/deploy
```

**Step 2: Run format to regenerate home-cluster kustomization**

```bash
format
```

The `generate-home-cluster.sh` script discovers all `projects/*/kustomization.yaml` aggregators. Adding `projects/mcp/kustomization.yaml` will make `mcp` discoverable by the `canada` root app.

**Step 3: Verify home-cluster includes mcp**

Check that `projects/home-cluster/kustomization.yaml` now includes `../mcp`.

**Step 4: Commit**

```
feat(mcp): wire up kustomize discovery for mcp project
```

---

### Task 6: Add Context Forge NetworkPolicies (Gateway Chart)

**Files:**

- Create: `projects/mcp/context-forge-gateway/chart/templates/networkpolicy.yaml`
- Create: `projects/mcp/context-forge-gateway/chart/templates/default-deny.yaml`

**Step 1: Default deny for mcp namespace**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

Note: This will be in the context-forge-gateway chart since it's the first app in the namespace. Alternatively, both apps could include it (idempotent with SSA).

**Step 2: DNS allow**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - { protocol: UDP, port: 53 }
        - { protocol: TCP, port: 53 }
```

**Step 3: Context Forge internal traffic**

Adapted from the deleted `netpol-context-forge.yaml`. Covers mcpgateway ↔ postgres ↔ redis ↔ migration internal comms.

**Step 4: Context Forge ingress from external namespaces**

- `agent-platform` namespace MCP servers → Context Forge (registration + tool calls)
- `agent-platform` namespace sandboxes → Context Forge (tool calls via gateway)
- Same-namespace OAuth proxy → Context Forge

Make these configurable via values:

```yaml
networkPolicy:
  enabled: true
  # Namespaces allowed to send ingress traffic to Context Forge
  allowedNamespaces:
    - agent-platform
```

**Step 5: Commit**

```
feat(mcp): add NetworkPolicies for context-forge-gateway
```

---

### Task 7: Update Agent-Platform OCI Chart Version and Deploy Config

**Files:**

- Modify: `projects/agent_platform/deploy/application.yaml` — bump targetRevision to 0.8.0
- Modify: `projects/agent_platform/chart/BUILD` — verify helm_chart target

**Step 1: Update application.yaml targetRevision**

Change `targetRevision: 0.7.0` to `targetRevision: 0.8.0`.

**Step 2: Verify BUILD file**

Ensure `helm_chart()` target doesn't reference removed subcharts in its `images={}` map.

**Step 3: Commit**

```
chore(agent-platform): bump chart version to 0.8.0
```

---

### Task 8: Clean Up and Validate

**Step 1: Helm template the umbrella chart**

```bash
helm template agent-platform projects/agent_platform/chart/ \
  -f projects/agent_platform/deploy/values.yaml
```

Verify: no context-forge or mcp-oauth-proxy resources rendered.

**Step 2: Helm template the context-forge-gateway chart**

```bash
helm template context-forge-gateway projects/mcp/context-forge-gateway/chart/ \
  -f projects/mcp/context-forge-gateway/deploy/values.yaml
```

Verify: mcp-stack resources rendered, 1Password item, NetworkPolicies.

**Step 3: Helm template the oauth-proxy chart**

```bash
helm template mcp-oauth-proxy projects/mcp/oauth-proxy/chart/ \
  -f projects/mcp/oauth-proxy/deploy/values.yaml
```

Verify: proxy deployment, service, NetworkPolicies.

**Step 4: Run format**

```bash
format
```

**Step 5: Final commit and push**

```bash
git push -u origin refactor/mcp-namespace
```

**Step 6: Create PR**

Target: `main`

---

## NetworkPolicy Summary After Refactor

| Policy                          | Namespace      | Direction | From/To                                                   |
| ------------------------------- | -------------- | --------- | --------------------------------------------------------- |
| default-deny                    | agent-platform | both      | all pods                                                  |
| allow-dns                       | agent-platform | egress    | all → kube-system:53                                      |
| mcp-servers-ingress             | agent-platform | ingress   | mcp:context-forge → servers                               |
| mcp-servers-registration-egress | agent-platform | egress    | servers → mcp:context-forge                               |
| per-server-egress               | agent-platform | egress    | each server → its upstream                                |
| orchestrator-ingress            | agent-platform | ingress   | envoy-gw + sandbox → orchestrator                         |
| orchestrator-egress             | agent-platform | egress    | orchestrator → NATS + K8s API                             |
| sandbox-egress                  | agent-platform | egress    | sandbox → mcp:context-forge + internet                    |
| nats-ingress                    | agent-platform | ingress   | orchestrator → NATS                                       |
| default-deny                    | mcp            | both      | all pods                                                  |
| allow-dns                       | mcp            | egress    | all → kube-system:53                                      |
| cf-internal                     | mcp            | both      | mcpgateway ↔ postgres ↔ redis                             |
| cf-ingress                      | mcp            | ingress   | agent-platform:{servers,sandboxes} + mcp:oauth-proxy → CF |
| oauth-proxy-ingress             | mcp            | ingress   | envoy-gw → proxy                                          |
| oauth-proxy-egress              | mcp            | egress    | proxy → Google OIDC + CF                                  |
