# Kubernetes and ArgoCD MCP Servers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Red Hat kubernetes-mcp-server and argoproj-labs mcp-for-argocd as two new entries in the existing mcp-servers Helm chart, registered with Context Forge.

**Architecture:** Both servers are third-party container images added to `overlays/prod/mcp-servers/values.yaml`. The chart needs minor enhancements (args support, ClusterRole creation) before adding the server entries. The Kubernetes MCP server uses the pod's ServiceAccount with a custom ClusterRole; the ArgoCD MCP server uses an API token from 1Password.

**Tech Stack:** Helm templates (Go templates), YAML values, Kubernetes RBAC, 1Password Operator

**Worktree:** `/tmp/claude-worktrees/k8s-argocd-mcp` (branch `feat/k8s-argocd-mcp`)

**Design doc:** `docs/plans/2026-03-02-k8s-argocd-mcp-design.md`

---

### Task 1: Add `args` support to deployment template

**Files:**

- Modify: `charts/mcp-servers/templates/deployment.yaml:88-95`

**Step 1: Add args block to native server container**

In `deployment.yaml`, insert after line 91 (the `imagePullPolicy` line) and before line 92 (the `ports` block):

```yaml
          {{- with .args }}
          args:
            {{- toYaml . | nindent 12 }}
          {{- end }}
```

The result should look like:

```yaml
        - name: server
          image: "{{ required "image.repository is required" .image.repository }}:{{ required "image.tag is required" .image.tag }}"
          imagePullPolicy: {{ .image.pullPolicy | default "IfNotPresent" }}
          {{- with .args }}
          args:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          ports:
```

**Step 2: Verify template renders with no args (backward compat)**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | head -80
```

Expected: Renders successfully, existing servers (signoz-mcp, buildbuddy-mcp) have no `args:` block in their containers.

**Step 3: Commit**

```bash
git add charts/mcp-servers/templates/deployment.yaml
git commit -m "feat(mcp-servers): add args support to native server container"
```

---

### Task 2: Add ClusterRole creation to RBAC template

**Files:**

- Modify: `charts/mcp-servers/templates/rbac.yaml:1-19`

**Step 1: Add ClusterRole resource creation**

Replace the entire content of `rbac.yaml` with:

```yaml
{{- range $server := $.Values.servers }}
{{- if $server.rbac }}
{{- if $server.rbac.clusterRoleRules }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-{{ $server.name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart "Release" $.Release) | nindent 4 }}
rules:
  {{- toYaml $server.rbac.clusterRoleRules | nindent 2 }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-{{ $server.name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart "Release" $.Release) | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: mcp-{{ $server.name }}
subjects:
  - kind: ServiceAccount
    name: {{ $server.name }}
    namespace: {{ $.Release.Namespace }}
{{- else if $server.rbac.clusterRole }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-{{ $server.name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart "Release" $.Release) | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ $server.rbac.clusterRole }}
subjects:
  - kind: ServiceAccount
    name: {{ $server.name }}
    namespace: {{ $.Release.Namespace }}
{{- end }}
{{- range $server.rbac.namespaced }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: mcp-{{ $server.name }}-{{ .namespace }}
  namespace: {{ .namespace }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart "Release" $.Release) | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: {{ .role }}
subjects:
  - kind: ServiceAccount
    name: {{ $server.name }}
    namespace: {{ $.Release.Namespace }}
{{- end }}
{{- end }}
{{- end }}
```

Logic:

- If `rbac.clusterRoleRules` is set → create both the ClusterRole and ClusterRoleBinding
- Else if `rbac.clusterRole` is set → only create ClusterRoleBinding (existing behavior)
- Namespaced RoleBindings remain unchanged

**Step 2: Verify template renders (backward compat)**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -A5 "kind: ClusterRole"
```

Expected: No ClusterRole or ClusterRoleBinding resources (existing servers don't use RBAC).

**Step 3: Commit**

```bash
git add charts/mcp-servers/templates/rbac.yaml
git commit -m "feat(mcp-servers): support inline ClusterRole creation via clusterRoleRules"
```

---

### Task 3: Add kubernetes-mcp server entry to values

**Files:**

- Modify: `overlays/prod/mcp-servers/values.yaml:64` (append after buildbuddy-mcp)

**Step 1: Add kubernetes-mcp entry**

Append to the `servers` list in `overlays/prod/mcp-servers/values.yaml`:

```yaml
- name: kubernetes-mcp
  image:
    repository: ghcr.io/containers/kubernetes-mcp-server
    tag: "latest"
  port: 8080
  args:
    - "--port"
    - "8080"
    - "--disable-destructive"
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 256Mi
  translate:
    enabled: false
  rbac:
    clusterRoleRules:
      - apiGroups:
          [
            "",
            "apps",
            "batch",
            "networking.k8s.io",
            "rbac.authorization.k8s.io",
          ]
        resources: ["*"]
        verbs: ["get", "list", "watch"]
      - apiGroups: [""]
        resources: ["pods/exec", "pods/portforward", "pods/log"]
        verbs: ["create", "get"]
      - apiGroups: ["metrics.k8s.io"]
        resources: ["pods", "nodes"]
        verbs: ["get", "list"]
  registration:
    enabled: true
    transport: "STREAMABLEHTTP"
  alert:
    enabled: true
    url: "http://kubernetes-mcp.mcp-servers.svc.cluster.local:8080/mcp"
```

Notes:

- No `secret` block — uses in-cluster ServiceAccount token, no external credentials
- Higher memory limit (256Mi) — Go binary with K8s API client may use more than the Python/Node servers
- Alert URL uses `/mcp` since kubernetes-mcp-server has no dedicated `/health` endpoint; the MCP endpoint responds to GET requests which SigNoz HTTPCheck can monitor
- `--disable-destructive` prevents delete/update operations at the application layer; ClusterRole prevents them at the K8s API layer (defense in depth)

**Step 2: Verify template renders**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -B2 -A20 "name: kubernetes-mcp"
```

Expected: Deployment, Service, ServiceAccount, ClusterRole, ClusterRoleBinding, registration Job, and alert ConfigMap all render for `kubernetes-mcp`.

Verify the args appear in the container:

```bash
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -A5 "disable-destructive"
```

Expected: `--disable-destructive` appears in the container args.

Verify the ClusterRole rules:

```bash
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -A15 "kind: ClusterRole"
```

Expected: ClusterRole `mcp-kubernetes-mcp` with the read + exec rules, followed by a ClusterRoleBinding.

**Step 3: Commit**

```bash
git add overlays/prod/mcp-servers/values.yaml
git commit -m "feat(mcp-servers): add kubernetes-mcp server with read + exec RBAC"
```

---

### Task 4: Add argocd-mcp server entry to values

**Files:**

- Modify: `overlays/prod/mcp-servers/values.yaml` (append after kubernetes-mcp)

**Step 1: Add argocd-mcp entry**

Append to the `servers` list:

```yaml
- name: argocd-mcp
  image:
    repository: ghcr.io/argoproj-labs/mcp-for-argocd
    tag: "v0.5.0"
  port: 3000
  writableTmp: true
  env:
    - name: ARGOCD_BASE_URL
      value: "http://argocd-server.argocd.svc.cluster.local:80"
  secret:
    name: argocd-mcp
    itemPath: "vaults/k8s-homelab/items/argocd-mcp"
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 128Mi
  translate:
    enabled: false
  registration:
    enabled: true
    transport: "STREAMABLEHTTP"
  alert:
    enabled: true
    url: "http://argocd-mcp.mcp-servers.svc.cluster.local:3000/mcp"
```

Notes:

- `writableTmp: true` — Node.js needs writable tmp; this also disables `runAsNonRoot` in the pod security context
- Secret `argocd-mcp` provides `ARGOCD_API_TOKEN` from 1Password
- `ARGOCD_BASE_URL` points to the in-cluster ArgoCD server service
- No RBAC — the server talks to ArgoCD's API via token, not the K8s API

**Step 2: Verify template renders**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -B2 -A20 "name: argocd-mcp"
```

Expected: Deployment (with `writableTmp` volume), Service, ServiceAccount, OnePasswordItem, registration Job, and alert ConfigMap all render for `argocd-mcp`.

Verify the 1Password item:

```bash
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml 2>&1 | grep -A5 "OnePasswordItem" | grep "argocd-mcp"
```

Expected: OnePasswordItem `argocd-mcp` with itemPath `vaults/k8s-homelab/items/argocd-mcp`.

**Step 3: Commit**

```bash
git add overlays/prod/mcp-servers/values.yaml
git commit -m "feat(mcp-servers): add argocd-mcp server with 1Password secret"
```

---

### Task 5: Full render validation and format check

**Step 1: Render the complete chart and review**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
helm template test charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml
```

Verify these resources exist for each new server:

- `kubernetes-mcp`: Deployment (with args), Service, ServiceAccount, ClusterRole, ClusterRoleBinding, registration Job, alert ConfigMap
- `argocd-mcp`: Deployment (with writableTmp + env), Service, ServiceAccount, OnePasswordItem, registration Job, alert ConfigMap

Verify existing servers still render correctly:

- `signoz-mcp`: unchanged
- `buildbuddy-mcp`: unchanged

**Step 2: Run format check**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
format
```

Expected: All formatters pass with no changes needed.

**Step 3: Run Bazel build**

Run:

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
bazel build //...
```

Expected: Build succeeds.

---

### Task 6: Create 1Password item (manual)

This step must be done by the user in 1Password.

Create item at `vaults/k8s-homelab/items/argocd-mcp` with field:

- `ARGOCD_API_TOKEN` — generate an ArgoCD API token via `argocd account generate-token`

This secret will be synced to K8s by the 1Password Operator as a Kubernetes Secret in the `mcp-servers` namespace.

---

### Task 7: Push and create PR

**Step 1: Push branch**

```bash
cd /tmp/claude-worktrees/k8s-argocd-mcp
git push -u origin feat/k8s-argocd-mcp
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(mcp-servers): add Kubernetes and ArgoCD MCP servers" --body "$(cat <<'EOF'
## Summary
- Add `args` support to mcp-servers chart deployment template
- Add inline ClusterRole creation via `clusterRoleRules` to RBAC template
- Deploy Red Hat kubernetes-mcp-server with non-destructive access (read + exec)
- Deploy argoproj-labs mcp-for-argocd with ArgoCD API token from 1Password
- Both servers registered with Context Forge gateway and monitored via SigNoz HTTPCheck alerts

## Manual Step
Create 1Password item at `vaults/k8s-homelab/items/argocd-mcp` with `ARGOCD_API_TOKEN` field before merging.

## Test plan
- [ ] `helm template` renders all 4 servers correctly
- [ ] CI passes (format + build)
- [ ] After merge: verify pods come up in `mcp-servers` namespace
- [ ] After merge: verify both servers register with Context Forge gateway
- [ ] After merge: verify `kubernetes-mcp` tools appear in Claude Code
- [ ] After merge: verify `argocd-mcp` tools appear in Claude Code
- [ ] After merge: test a read-only K8s query (e.g., list pods)
- [ ] After merge: test an ArgoCD query (e.g., list applications)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
