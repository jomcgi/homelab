# Context Forge MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Context Forge as an MCP gateway with the SigNoz MCP server as an upstream backend, exposed at `mcp.jomcgi.dev`.

**Architecture:** Context Forge pod with two containers — the gateway (upstream Python image) and the SigNoz MCP server (Bazel-built Go image as sidecar). A postStart lifecycle hook registers the sidecar with the gateway on startup. Exposed via Cloudflare tunnel.

**Tech Stack:** Go (SigNoz MCP), Bazel (go_image, rules_go, gazelle), Helm, ArgoCD, Cloudflare Tunnel, 1Password Operator

**Worktree:** `/tmp/claude-worktrees/feat-context-forge` (branch: `feat/context-forge`)

**Pre-completed manual steps:** 1Password item `context-forge` with `SIGNOZ_API_KEY` already created. Cloudflare tunnel subdomain and service token bypass already configured.

---

### Task 1: Vendor SigNoz MCP server source

**Files:**
- Create: `services/signoz_mcp_server/` (vendored Go source)

**Step 1: Clone and copy source**

```bash
cd /tmp
git clone --depth 1 https://github.com/SigNoz/signoz-mcp-server.git
```

Copy the Go source into the repo. Exclude `.git`, `Dockerfile`, `docker-compose.yml`, and other non-Go files. Keep: `cmd/`, `internal/` (or whatever packages exist), `go.mod`, `go.sum`, and any `.go` files at the root.

```bash
cd /tmp/claude-worktrees/feat-context-forge
mkdir -p services/signoz_mcp_server
# Copy Go source (adjust based on actual repo structure)
cp -r /tmp/signoz-mcp-server/cmd services/signoz_mcp_server/
cp -r /tmp/signoz-mcp-server/internal services/signoz_mcp_server/ 2>/dev/null || true
cp -r /tmp/signoz-mcp-server/pkg services/signoz_mcp_server/ 2>/dev/null || true
cp /tmp/signoz-mcp-server/*.go services/signoz_mcp_server/ 2>/dev/null || true
cp /tmp/signoz-mcp-server/go.mod /tmp/signoz-mcp-server/go.sum services/signoz_mcp_server/
```

**Step 2: Inspect the source structure**

```bash
find services/signoz_mcp_server -name "*.go" | head -20
cat services/signoz_mcp_server/go.mod
```

Understand the module path (likely `github.com/SigNoz/signoz-mcp-server`) and package layout before proceeding.

**Step 3: Integrate with repo Go module**

Two approaches depending on complexity:

**Approach A (preferred): Re-module under root go.mod**
- Rewrite import paths from `github.com/SigNoz/signoz-mcp-server` → `github.com/jomcgi/homelab/services/signoz_mcp_server` in all `.go` files
- Merge external dependencies into root `go.mod` via `go get`
- Run `go mod tidy`

```bash
# Rewrite imports (adjust the source module path based on actual go.mod)
find services/signoz_mcp_server -name "*.go" -exec sed -i '' \
  's|github.com/SigNoz/signoz-mcp-server|github.com/jomcgi/homelab/services/signoz_mcp_server|g' {} +

# Remove the vendored go.mod/go.sum (now using root module)
rm services/signoz_mcp_server/go.mod services/signoz_mcp_server/go.sum

# Add external deps to root go.mod
cd /tmp/claude-worktrees/feat-context-forge
go mod tidy
```

**Approach B (fallback): Separate Go module**
If Approach A is impractical (too many deps, version conflicts), keep a separate `go.mod`:

```starlark
# In MODULE.bazel, add second go_deps source:
go_deps.from_file(go_mod = "//services/signoz_mcp_server:go.mod")
```

Add gazelle directive to `services/signoz_mcp_server/BUILD`:
```starlark
# gazelle:prefix github.com/SigNoz/signoz-mcp-server
```

**Step 4: Generate BUILD files with gazelle**

```bash
cd /tmp/claude-worktrees/feat-context-forge
bazel run gazelle
```

Verify gazelle generated `go_library` and `go_binary` targets:

```bash
cat services/signoz_mcp_server/cmd/server/BUILD
```

Expected: a `go_binary` target for the server entrypoint.

**Step 5: Verify build**

```bash
bazel build //services/signoz_mcp_server/cmd/server
```

Expected: successful build of the Go binary.

**Step 6: Commit**

```bash
git add services/signoz_mcp_server/
git commit -m "feat: vendor SigNoz MCP server source for Bazel build"
```

---

### Task 2: Build SigNoz MCP Go image

**Files:**
- Create: `services/signoz_mcp_server/BUILD` (go_image)
- Modify: `images/BUILD` (add to push_all)

**Step 1: Create go_image BUILD target**

Create `services/signoz_mcp_server/BUILD` (or append to existing gazelle-generated file):

```starlark
load("//tools/oci:go_image.bzl", "go_image")

go_image(
    name = "image",
    binary = "//services/signoz_mcp_server/cmd/server",
)
```

This produces a dual-arch distroless image at `ghcr.io/jomcgi/homelab/services/signoz_mcp_server` running as uid 65532.

**Step 2: Verify image builds**

```bash
bazel build //services/signoz_mcp_server:image
```

Expected: successful OCI image build for both amd64 and arm64.

**Step 3: Add to push_all multirun**

Modify `images/BUILD` — add to the `commands` list in `multirun`:

```starlark
"//services/signoz_mcp_server:image.push",
```

**Step 4: Commit**

```bash
git add services/signoz_mcp_server/BUILD images/BUILD
git commit -m "feat: add SigNoz MCP server container image build"
```

---

### Task 3: Create Helm chart scaffold

**Files:**
- Create: `charts/context-forge/Chart.yaml`
- Create: `charts/context-forge/values.yaml`
- Create: `charts/context-forge/templates/_helpers.tpl`

**Step 1: Create Chart.yaml**

Create `charts/context-forge/Chart.yaml`:

```yaml
apiVersion: v2
name: context-forge
description: MCP gateway aggregating observability and infrastructure tools
type: application
version: 1.0.0
appVersion: "1.0.0-BETA-1"
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

Create `charts/context-forge/values.yaml`:

```yaml
# Context Forge MCP Gateway
# Aggregates upstream MCP servers behind a single endpoint.

# Gateway container (IBM Context Forge)
gateway:
  image:
    repository: ghcr.io/ibm/mcp-context-forge
    tag: "1.0.0-BETA-1"
    pullPolicy: IfNotPresent
  port: 4444
  resources:
    requests:
      cpu: 50m
      memory: 256Mi
    limits:
      cpu: 200m
      memory: 512Mi

# SigNoz MCP server (sidecar)
signoz:
  enabled: true
  image:
    repository: ghcr.io/jomcgi/homelab/services/signoz_mcp_server
    tag: "latest"
    pullPolicy: Always
  port: 8000
  # SigNoz backend URL (cluster-internal)
  url: http://signoz.signoz.svc.cluster.local:8080
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 100m
      memory: 128Mi

# 1Password secret for backend credentials
secret:
  name: context-forge
  itemPath: "vaults/k8s-homelab/items/context-forge"
```

**Step 3: Create _helpers.tpl**

Create `charts/context-forge/templates/_helpers.tpl`:

```
{{/*
Expand the name of the chart.
*/}}
{{- define "context-forge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "context-forge.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "context-forge.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "context-forge.labels" -}}
helm.sh/chart: {{ include "context-forge.chart" . }}
{{ include "context-forge.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "context-forge.selectorLabels" -}}
app.kubernetes.io/name: {{ include "context-forge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

**Step 4: Commit**

```bash
git add charts/context-forge/
git commit -m "feat: add Context Forge Helm chart scaffold"
```

---

### Task 4: Create deployment template

**Files:**
- Create: `charts/context-forge/templates/deployment.yaml`

**Step 1: Create deployment.yaml**

Create `charts/context-forge/templates/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "context-forge.fullname" . }}
  labels:
    {{- include "context-forge.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "context-forge.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
      labels:
        {{- include "context-forge.selectorLabels" . | nindent 8 }}
    spec:
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        # Context Forge gateway
        - name: gateway
          image: "{{ .Values.gateway.image.repository }}:{{ .Values.gateway.image.tag }}"
          imagePullPolicy: {{ .Values.gateway.image.pullPolicy }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            # Context Forge (Python) needs writable filesystem for SQLite + runtime
            readOnlyRootFilesystem: false
          ports:
            - name: http
              containerPort: {{ .Values.gateway.port }}
              protocol: TCP
          env:
            - name: HOST
              value: "0.0.0.0"
            - name: PORT
              value: {{ .Values.gateway.port | quote }}
            - name: DATABASE_URL
              value: "sqlite:////data/context-forge.db"
            - name: AUTH_REQUIRED
              value: "false"
            - name: MCP_CLIENT_AUTH_ENABLED
              value: "false"
            - name: MCPGATEWAY_UI_ENABLED
              value: "false"
            - name: MCPGATEWAY_ADMIN_API_ENABLED
              value: "true"
          volumeMounts:
            - name: data
              mountPath: /data
            - name: register-script
              mountPath: /config
              readOnly: true
          lifecycle:
            postStart:
              exec:
                command:
                  - /bin/sh
                  - /config/register-gateways.sh
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            {{- toYaml .Values.gateway.resources | nindent 12 }}
        {{- if .Values.signoz.enabled }}
        # SigNoz MCP server (upstream MCP backend)
        - name: signoz-mcp
          image: "{{ .Values.signoz.image.repository }}:{{ .Values.signoz.image.tag }}"
          imagePullPolicy: {{ .Values.signoz.image.pullPolicy }}
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 65532
            capabilities:
              drop:
                - ALL
          ports:
            - name: signoz-mcp
              containerPort: {{ .Values.signoz.port }}
              protocol: TCP
          env:
            - name: SIGNOZ_URL
              value: {{ .Values.signoz.url | quote }}
            - name: TRANSPORT_MODE
              value: "http"
            - name: MCP_SERVER_PORT
              value: {{ .Values.signoz.port | quote }}
            - name: SIGNOZ_API_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.secret.name }}
                  key: SIGNOZ_API_KEY
          resources:
            {{- toYaml .Values.signoz.resources | nindent 12 }}
        {{- end }}
      volumes:
        - name: data
          emptyDir: {}
        - name: register-script
          configMap:
            name: {{ include "context-forge.fullname" . }}-config
            defaultMode: 0755
```

**Step 2: Verify template renders**

```bash
helm template context-forge charts/context-forge/
```

Expected: valid YAML with both containers, volumes, and lifecycle hook.

**Step 3: Commit**

```bash
git add charts/context-forge/templates/deployment.yaml
git commit -m "feat: add Context Forge deployment template with sidecar"
```

---

### Task 5: Create service, configmap, and secret templates

**Files:**
- Create: `charts/context-forge/templates/service.yaml`
- Create: `charts/context-forge/templates/configmap.yaml`
- Create: `charts/context-forge/templates/onepassworditem.yaml`

**Step 1: Create service.yaml**

Create `charts/context-forge/templates/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "context-forge.fullname" . }}
  labels:
    {{- include "context-forge.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: {{ .Values.gateway.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "context-forge.selectorLabels" . | nindent 4 }}
```

**Step 2: Create configmap.yaml**

The registration script uses Python (guaranteed available in the Context Forge image) to wait for the gateway health endpoint and register the SigNoz MCP server as an upstream gateway.

Create `charts/context-forge/templates/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "context-forge.fullname" . }}-config
  labels:
    {{- include "context-forge.labels" . | nindent 4 }}
data:
  register-gateways.sh: |
    #!/bin/sh
    # Register upstream MCP servers with Context Forge gateway.
    # Runs as a postStart lifecycle hook — gateway starts concurrently,
    # so we poll /health until it's ready before registering.
    GATEWAY="http://localhost:{{ .Values.gateway.port }}"

    # Wait for gateway to be healthy (up to 60s)
    attempts=0
    until curl -sf "$GATEWAY/health" > /dev/null 2>&1; do
      attempts=$((attempts + 1))
      if [ "$attempts" -ge 60 ]; then
        echo "ERROR: gateway not healthy after 60s" >&2
        exit 1
      fi
      sleep 1
    done

    {{- if .Values.signoz.enabled }}
    # Register SigNoz MCP server
    curl -sf -X POST "$GATEWAY/gateways" \
      -H "Content-Type: application/json" \
      -d '{"name":"signoz","url":"http://localhost:{{ .Values.signoz.port }}/sse","description":"SigNoz observability — logs, traces, metrics, alerts, dashboards"}'
    {{- end }}
```

**Step 3: Create onepassworditem.yaml**

Create `charts/context-forge/templates/onepassworditem.yaml`:

```yaml
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: {{ .Values.secret.name }}
  labels:
    {{- include "context-forge.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.secret.itemPath | quote }}
```

**Step 4: Verify full chart renders**

```bash
helm template context-forge charts/context-forge/
```

Expected: all resources render — Deployment, Service, ConfigMap, OnePasswordItem.

**Step 5: Commit**

```bash
git add charts/context-forge/templates/
git commit -m "feat: add Context Forge service, configmap, and secret templates"
```

---

### Task 6: Create ArgoCD overlay

**Files:**
- Create: `overlays/prod/context-forge/application.yaml`
- Create: `overlays/prod/context-forge/kustomization.yaml`
- Create: `overlays/prod/context-forge/values.yaml`
- Modify: `clusters/homelab/kustomization.yaml` (if needed to include new overlay)

**Step 1: Create application.yaml**

Create `overlays/prod/context-forge/application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: context-forge
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/context-forge
    targetRevision: HEAD
    helm:
      releaseName: context-forge
      valueFiles:
        - values.yaml
        - ../../overlays/prod/context-forge/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: mcp-gateway
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**Step 2: Create kustomization.yaml**

Create `overlays/prod/context-forge/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create values.yaml (production overrides)**

Create `overlays/prod/context-forge/values.yaml`:

```yaml
# Production overrides for Context Forge MCP gateway
# Base values in charts/context-forge/values.yaml

signoz:
  image:
    repository: ghcr.io/jomcgi/homelab/services/signoz_mcp_server
    tag: main
```

**Step 4: Wire into cluster kustomization**

Check `clusters/homelab/kustomization.yaml` to see how overlays are included. If the prod overlay directory is auto-discovered, no change needed. If manually listed, add the new overlay.

```bash
cat clusters/homelab/kustomization.yaml
# If it references overlays/prod/ via a glob or directory, no change needed.
# If it lists individual paths, add: - ../../overlays/prod/context-forge
```

**Step 5: Verify with helm template using overlay values**

```bash
helm template context-forge charts/context-forge/ \
  -f overlays/prod/context-forge/values.yaml
```

Expected: renders with production image tag.

**Step 6: Commit**

```bash
git add overlays/prod/context-forge/
git commit -m "feat: add Context Forge ArgoCD application overlay"
```

---

### Task 7: Add Cloudflare tunnel route

**Files:**
- Modify: `overlays/prod/cloudflare-tunnel/values.yaml`

**Step 1: Add mcp.jomcgi.dev route**

Add to the `ingress.routes` list in `overlays/prod/cloudflare-tunnel/values.yaml`:

```yaml
- hostname: mcp.jomcgi.dev
  service: http://context-forge.mcp-gateway.svc.cluster.local:4444
```

Insert alphabetically among the existing routes (after `longhorn.jomcgi.dev`, before `n8n.jomcgi.dev`).

**Step 2: Verify tunnel config renders**

```bash
helm template cluster-ingress charts/cloudflare-tunnel/ \
  -f overlays/prod/cloudflare-tunnel/values.yaml 2>/dev/null | grep -A2 "mcp.jomcgi.dev"
```

Expected: the new route appears in the rendered ConfigMap.

**Step 3: Commit**

```bash
git add overlays/prod/cloudflare-tunnel/values.yaml
git commit -m "feat: add mcp.jomcgi.dev tunnel route to Context Forge"
```

---

### Task 8: Push image and final validation

**Step 1: Push SigNoz MCP server image**

```bash
bazel run //services/signoz_mcp_server:image.push
```

Expected: image pushed to `ghcr.io/jomcgi/homelab/services/signoz_mcp_server`.

**Step 2: Run full build check**

```bash
bazel build //...
bazel test //...
```

Expected: no regressions.

**Step 3: Run format check**

```bash
format
```

Expected: clean (or fix any formatting issues and amend commit).

**Step 4: Push branch and create PR**

```bash
git push -u origin feat/context-forge
```

Then use the `gh-pr` skill to create the pull request.
