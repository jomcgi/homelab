# MCP Servers Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a single range-based Helm chart (`charts/mcp-servers/`) that deploys MCP servers with optional translate sidecars, gateway registration, and SigNoz HTTPCheck alerts, then migrate `signoz-mcp` into it.

**Architecture:** Templates iterate over `.Values.servers`, generating per-server Deployment, Service, ServiceAccount, and optional RBAC, OnePasswordItem, registration Job, and alert ConfigMap. Stdio servers get the upstream IBM `mcp-context-forge` image as a translate sidecar exposing streamable-http.

**Tech Stack:** Helm 3, Kubernetes, ArgoCD, SigNoz, IBM mcp-context-forge (upstream image), Bazel (rules_helm)

**Design doc:** `docs/plans/2026-03-01-mcp-servers-chart-design.md`

---

### Task 1: Create chart skeleton and values schema

**Files:**
- Create: `charts/mcp-servers/Chart.yaml`
- Create: `charts/mcp-servers/values.yaml`
- Create: `charts/mcp-servers/BUILD`

**Step 1: Create Chart.yaml**

```yaml
# charts/mcp-servers/Chart.yaml
apiVersion: v2
name: mcp-servers
description: Deploys MCP servers with optional protocol translation, gateway registration, and health alerts
type: application
version: 1.0.0
appVersion: "1.0.0"
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create values.yaml**

```yaml
# charts/mcp-servers/values.yaml

# Shared translate sidecar image (upstream IBM mcp-context-forge)
translate:
  image:
    repository: ghcr.io/ibm/mcp-context-forge
    tag: v1.0.0-RC1
    pullPolicy: IfNotPresent

# Context Forge gateway for registration jobs
gateway:
  url: "http://context-forge-mcp-stack-mcpgateway.mcp-gateway.svc.cluster.local:80"
  secret:
    name: context-forge-jwt

# HTTPCheck alert defaults (overridable per server)
alertDefaults:
  evalWindow: "10m0s"
  frequency: "2m0s"
  matchType: "5"
  severity: "critical"
  channels:
    - pagerduty-homelab

# MCP servers to deploy
servers: []
```

**Step 3: Create BUILD file**

```python
# charts/mcp-servers/BUILD
load("//rules_helm:defs.bzl", "helm_chart")

helm_chart(
    name = "chart",
    visibility = ["//overlays/prod/mcp-servers:__pkg__"],
)
```

**Step 4: Verify lint passes**

Run: `bazel test //charts/mcp-servers:lint_test`
Expected: PASS (empty servers list, chart structure is valid)

**Step 5: Commit**

```bash
git add charts/mcp-servers/Chart.yaml charts/mcp-servers/values.yaml charts/mcp-servers/BUILD
git commit -m "feat(mcp-servers): add chart skeleton and values schema"
```

---

### Task 2: Create _helpers.tpl

**Files:**
- Create: `charts/mcp-servers/templates/_helpers.tpl`

**Step 1: Create helpers template**

```yaml
{{/*
Common labels for a server.
Usage: {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart) }}
*/}}
{{- define "mcp-servers.labels" -}}
app.kubernetes.io/name: {{ .server.name }}
app.kubernetes.io/managed-by: {{ .Chart.Name }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels for a server.
Usage: {{- include "mcp-servers.selectorLabels" .server }}
*/}}
{{- define "mcp-servers.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
{{- end }}

{{/*
Effective port for a server (translate port if enabled, otherwise server port).
Usage: {{ include "mcp-servers.port" $server }}
*/}}
{{- define "mcp-servers.port" -}}
{{- if .translate.enabled -}}
{{- .translate.port | default 8080 -}}
{{- else -}}
{{- .port -}}
{{- end -}}
{{- end }}
```

**Step 2: Commit**

```bash
git add charts/mcp-servers/templates/_helpers.tpl
git commit -m "feat(mcp-servers): add template helpers"
```

---

### Task 3: Create deployment template

**Files:**
- Create: `charts/mcp-servers/templates/deployment.yaml`

**Step 1: Create deployment template**

The deployment has two modes controlled by `.translate.enabled`:
- `false`: single container, server exposes its own port
- `true`: two containers — headless stdio server + translate sidecar with port

```yaml
{{- range .Values.servers }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "mcp-servers.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "mcp-servers.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ .name }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        seccompProfile:
          type: RuntimeDefault
      containers:
        {{- if .translate.enabled }}
        - name: server
          image: "{{ .image.repository }}:{{ .image.tag }}"
          imagePullPolicy: {{ .image.pullPolicy | default "IfNotPresent" }}
          {{- with .env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- if .secret }}
          envFrom:
            - secretRef:
                name: {{ .secret.name }}
          {{- end }}
          stdin: true
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            {{- toYaml .resources | nindent 12 }}
        - name: translate
          image: "{{ $.Values.translate.image.repository }}:{{ $.Values.translate.image.tag }}"
          imagePullPolicy: {{ $.Values.translate.image.pullPolicy }}
          command: ["python3", "-m", "mcpgateway.translate"]
          args:
            - "--stdio"
            - {{ .translate.command | quote }}
            - "--expose-streamable-http"
            - "--port"
            - {{ .translate.port | default 8080 | quote }}
          ports:
            - name: mcp
              containerPort: {{ .translate.port | default 8080 }}
              protocol: TCP
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: 10m
              memory: 64Mi
            limits:
              cpu: 100m
              memory: 128Mi
          livenessProbe:
            tcpSocket:
              port: mcp
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            tcpSocket:
              port: mcp
            initialDelaySeconds: 5
            periodSeconds: 10
        {{- else }}
        - name: server
          image: "{{ .image.repository }}:{{ .image.tag }}"
          imagePullPolicy: {{ .image.pullPolicy | default "IfNotPresent" }}
          ports:
            - name: mcp
              containerPort: {{ .port }}
              protocol: TCP
          {{- with .env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- if .secret }}
          envFrom:
            - secretRef:
                name: {{ .secret.name }}
          {{- end }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            {{- toYaml .resources | nindent 12 }}
          livenessProbe:
            tcpSocket:
              port: mcp
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            tcpSocket:
              port: mcp
            initialDelaySeconds: 5
            periodSeconds: 10
        {{- end }}
{{- end }}
```

**Step 2: Verify renders with signoz-mcp values**

Run: `helm template mcp-servers charts/mcp-servers/ --set-json 'servers=[{"name":"signoz-mcp","image":{"repository":"docker.io/signoz/signoz-mcp-server","tag":"v0.0.5"},"port":8000,"env":[{"name":"TRANSPORT_MODE","value":"http"}],"resources":{"requests":{"cpu":"10m","memory":"64Mi"},"limits":{"cpu":"100m","memory":"128Mi"}},"translate":{"enabled":false}}]'`
Expected: Valid Deployment YAML with single container, port 8000, no translate sidecar

**Step 3: Commit**

```bash
git add charts/mcp-servers/templates/deployment.yaml
git commit -m "feat(mcp-servers): add deployment template with translate sidecar support"
```

---

### Task 4: Create service, serviceaccount, and onepassworditem templates

**Files:**
- Create: `charts/mcp-servers/templates/service.yaml`
- Create: `charts/mcp-servers/templates/serviceaccount.yaml`
- Create: `charts/mcp-servers/templates/onepassworditem.yaml`

**Step 1: Create service template**

```yaml
{{- range .Values.servers }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: {{ include "mcp-servers.port" . }}
      targetPort: mcp
      protocol: TCP
      name: mcp
  selector:
    {{- include "mcp-servers.selectorLabels" . | nindent 4 }}
{{- end }}
```

**Step 2: Create serviceaccount template**

```yaml
{{- range .Values.servers }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
{{- end }}
```

**Step 3: Create onepassworditem template**

```yaml
{{- range .Values.servers }}
{{- if .secret }}
---
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: {{ .secret.name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
spec:
  itemPath: {{ .secret.itemPath | quote }}
{{- end }}
{{- end }}
```

**Step 4: Verify lint still passes**

Run: `bazel test //charts/mcp-servers:lint_test`
Expected: PASS

**Step 5: Commit**

```bash
git add charts/mcp-servers/templates/service.yaml charts/mcp-servers/templates/serviceaccount.yaml charts/mcp-servers/templates/onepassworditem.yaml
git commit -m "feat(mcp-servers): add service, serviceaccount, and onepassworditem templates"
```

---

### Task 5: Create RBAC template

**Files:**
- Create: `charts/mcp-servers/templates/rbac.yaml`

**Step 1: Create RBAC template**

```yaml
{{- range $server := $.Values.servers }}
{{- if $server.rbac }}
{{- if $server.rbac.clusterRole }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-{{ $server.name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart) | nindent 4 }}
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
  name: mcp-{{ $server.name }}
  namespace: {{ .namespace }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart) | nindent 4 }}
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

**Step 2: Commit**

```bash
git add charts/mcp-servers/templates/rbac.yaml
git commit -m "feat(mcp-servers): add RBAC template for optional cluster and namespace bindings"
```

---

### Task 6: Create HTTPCheck alert template

**Files:**
- Create: `charts/mcp-servers/templates/alert.yaml`

Reference pattern: `overlays/prod/api-gateway/api-gateway-httpcheck-alert.yaml`

**Step 1: Create alert template**

```yaml
{{- range .Values.servers }}
{{- if and .alert .alert.enabled }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .name }}-httpcheck-alert
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
    signoz.io/alert: "true"
  annotations:
    signoz.io/alert-name: {{ printf "%s Unreachable" .name | quote }}
    signoz.io/severity: {{ .alert.severity | default $.Values.alertDefaults.severity | quote }}
    signoz.io/notification-channels: {{ join "," (.alert.channels | default $.Values.alertDefaults.channels) | quote }}
data:
  alert.json: |
    {
      "alert": {{ printf "%s Unreachable" .name | quote }},
      "alertType": "METRICS_BASED_ALERT",
      "ruleType": "threshold_rule",
      "broadcastToAll": false,
      "disabled": false,
      "evalWindow": {{ .alert.evalWindow | default $.Values.alertDefaults.evalWindow | quote }},
      "frequency": {{ .alert.frequency | default $.Values.alertDefaults.frequency | quote }},
      "severity": {{ .alert.severity | default $.Values.alertDefaults.severity | quote }},
      "labels": {
        "service": {{ .name | quote }},
        "environment": "production"
      },
      "annotations": {
        "summary": {{ printf "%s at %s is unreachable" .name .alert.url | quote }},
        "description": "HTTP health check has failed {{ $.Values.alertDefaults.matchType }} consecutive times. Service may be down."
      },
      "condition": {
        "compositeQuery": {
          "builderQueries": {
            "A": {
              "queryName": "A",
              "dataSource": "metrics",
              "aggregateOperator": "avg",
              "aggregateAttribute": {
                "key": "httpcheck.status",
                "dataType": "float64",
                "type": "Gauge"
              },
              "filters": {
                "items": [
                  {
                    "key": {"key": "http.url"},
                    "op": "=",
                    "value": {{ .alert.url | quote }}
                  }
                ]
              }
            }
          },
          "queryType": "builder"
        },
        "op": "<",
        "target": 1,
        "matchType": {{ $.Values.alertDefaults.matchType | quote }}
      },
      "preferredChannels": {{ .alert.channels | default $.Values.alertDefaults.channels | toJson }}
    }
{{- end }}
{{- end }}
```

**Step 2: Commit**

```bash
git add charts/mcp-servers/templates/alert.yaml
git commit -m "feat(mcp-servers): add HTTPCheck alert template per server"
```

---

### Task 7: Create registration job template

**Files:**
- Create: `charts/mcp-servers/templates/registration-job.yaml`

Reference pattern: `charts/context-forge/templates/registration-job.yaml`

**Step 1: Create registration job template**

```yaml
{{- range .Values.servers }}
{{- if and .registration .registration.enabled }}
---
apiVersion: batch/v1
kind: Job
metadata:
  name: register-{{ .name }}
  labels:
    {{- include "mcp-servers.labels" (dict "server" . "Chart" $.Chart) | nindent 4 }}
  annotations:
    "helm.sh/hook": post-install,post-upgrade
    "helm.sh/hook-weight": "1"
    "helm.sh/hook-delete-policy": before-hook-creation
spec:
  ttlSecondsAfterFinished: 300
  backoffLimit: 3
  template:
    metadata:
      annotations:
        linkerd.io/inject: disabled
      labels:
        {{- include "mcp-servers.selectorLabels" . | nindent 8 }}
    spec:
      restartPolicy: OnFailure
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      initContainers:
        - name: wait-for-gateway
          image: "{{ $.Values.translate.image.repository }}:{{ $.Values.translate.image.tag }}"
          imagePullPolicy: {{ $.Values.translate.image.pullPolicy }}
          command: ["sh", "-c"]
          args:
            - |
              echo "Waiting for gateway at {{ $.Values.gateway.url }}/health..."
              until curl -sf "{{ $.Values.gateway.url }}/health" > /dev/null 2>&1; do
                echo "Gateway not ready, retrying in 5s..."
                sleep 5
              done
              echo "Gateway is healthy."
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 50m
              memory: 64Mi
      containers:
        - name: register
          image: "{{ $.Values.translate.image.repository }}:{{ $.Values.translate.image.tag }}"
          imagePullPolicy: {{ $.Values.translate.image.pullPolicy }}
          command: ["/bin/bash", "-c"]
          args:
            - |
              set -e

              TOKEN=$(python3 -c "
              import jwt, time, os, uuid
              payload = {
                  'sub': 'admin@jomcgi.dev',
                  'iat': int(time.time()),
                  'exp': int(time.time()) + 300,
                  'jti': str(uuid.uuid4()),
                  'aud': 'mcpgateway-api',
                  'iss': 'mcpgateway',
                  'is_admin': True,
                  'teams': None,
              }
              print(jwt.encode(payload, os.environ.get('JWT_SECRET_KEY', ''), algorithm='HS256'))
              ")

              # Idempotent: delete existing, then re-register
              curl -sf -X DELETE "{{ $.Values.gateway.url }}/gateways/{{ .name }}" \
                -H "Authorization: Bearer ${TOKEN}" || true

              echo "Registering {{ .name }}..."
              curl -sf -X POST "{{ $.Values.gateway.url }}/gateways" \
                -H "Authorization: Bearer ${TOKEN}" \
                -H "Content-Type: application/json" \
                -d '{
                  "name": "{{ .name }}",
                  "url": "http://{{ .name }}.{{ $.Release.Namespace }}.svc.cluster.local:{{ include "mcp-servers.port" . }}/mcp",
                  "transport": "{{ .registration.transport | default "STREAMABLEHTTP" }}"
                }'

              echo ""
              echo "Registration complete."
          envFrom:
            - secretRef:
                name: {{ $.Values.gateway.secret.name }}
          resources:
            requests:
              cpu: 10m
              memory: 64Mi
            limits:
              cpu: 100m
              memory: 128Mi
{{- end }}
{{- end }}
```

**Step 2: Commit**

```bash
git add charts/mcp-servers/templates/registration-job.yaml
git commit -m "feat(mcp-servers): add per-server gateway registration job"
```

---

### Task 8: Create overlay and migrate signoz-mcp

**Files:**
- Create: `overlays/prod/mcp-servers/application.yaml`
- Create: `overlays/prod/mcp-servers/kustomization.yaml`
- Create: `overlays/prod/mcp-servers/values.yaml`
- Create: `overlays/prod/mcp-servers/BUILD`
- Modify: `overlays/prod/kustomization.yaml` — replace `signoz-mcp` with `mcp-servers`

**Step 1: Create ArgoCD Application**

```yaml
# overlays/prod/mcp-servers/application.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: mcp-servers
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    path: charts/mcp-servers
    targetRevision: HEAD
    helm:
      releaseName: mcp-servers
      valueFiles:
        - values.yaml
        - ../../overlays/prod/mcp-servers/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: mcp-servers
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**Step 2: Create kustomization.yaml**

```yaml
# overlays/prod/mcp-servers/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Create prod values with signoz-mcp as first server**

```yaml
# overlays/prod/mcp-servers/values.yaml
servers:
  - name: signoz-mcp
    image:
      repository: docker.io/signoz/signoz-mcp-server
      tag: "v0.0.5"
    port: 8000
    env:
      - name: SIGNOZ_URL
        value: "http://signoz.signoz.svc.cluster.local:8080"
      - name: TRANSPORT_MODE
        value: "http"
      - name: MCP_SERVER_PORT
        value: "8000"
    secret:
      name: signoz-mcp
      itemPath: "vaults/k8s-homelab/items/signoz-mcp"
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
      url: "http://signoz-mcp.mcp-servers.svc.cluster.local:8000/health"
```

**Step 4: Create BUILD file**

```python
# overlays/prod/mcp-servers/BUILD
load("//rules_helm:defs.bzl", "argocd_app")

argocd_app(
    name = "mcp-servers",
    chart = "charts/mcp-servers",
    chart_files = "//charts/mcp-servers:chart",
    namespace = "mcp-servers",
    release_name = "mcp-servers",
    tags = [
        "helm",
        "template",
    ],
    values_files = [
        "//charts/mcp-servers:values.yaml",
        "values.yaml",
    ],
)
```

**Step 5: Update prod kustomization — replace signoz-mcp with mcp-servers**

In `overlays/prod/kustomization.yaml`, replace `- ./signoz-mcp` with `- ./mcp-servers`.

**Step 6: Verify helm template renders correctly**

Run: `helm template mcp-servers charts/mcp-servers/ -f overlays/prod/mcp-servers/values.yaml -n mcp-servers`
Expected: Deployment, Service, ServiceAccount, OnePasswordItem, registration Job, and HTTPCheck alert ConfigMap — all for signoz-mcp.

**Step 7: Verify Bazel template test passes**

Run: `bazel test //overlays/prod/mcp-servers:template_test`
Expected: PASS

**Step 8: Commit**

```bash
git add overlays/prod/mcp-servers/ overlays/prod/kustomization.yaml
git commit -m "feat(mcp-servers): add prod overlay with signoz-mcp as first server"
```

---

### Task 9: Remove old signoz-mcp chart and overlay

**Files:**
- Delete: `charts/signoz-mcp/` (entire directory)
- Delete: `overlays/prod/signoz-mcp/` (entire directory)
- Modify: `charts/context-forge/values.yaml` — remove `registration.signoz` section
- Modify: `charts/context-forge/templates/registration-job.yaml` — remove signoz-mcp registration block (or delete template entirely if no other servers remain)

**Step 1: Delete signoz-mcp chart directory**

```bash
rm -rf charts/signoz-mcp/
```

**Step 2: Delete signoz-mcp overlay directory**

```bash
rm -rf overlays/prod/signoz-mcp/
```

**Step 3: Remove registration from context-forge values**

In `charts/context-forge/values.yaml`, remove the `registration:` section (lines 88-92):

```yaml
# Remove this block:
registration:
  signoz:
    name: signoz-mcp
    url: "http://signoz-mcp.mcp-servers.svc.cluster.local:8000/mcp"
    transport: STREAMABLEHTTP
```

**Step 4: Remove or simplify context-forge registration job**

If signoz-mcp was the only registered server, delete `charts/context-forge/templates/registration-job.yaml` entirely. If other servers remain, remove only the signoz-mcp registration block.

**Step 5: Verify context-forge still renders**

Run: `helm template context-forge charts/context-forge/ -f overlays/prod/context-forge/values.yaml -n mcp-gateway`
Expected: Renders without the registration job (or without signoz-mcp block)

**Step 6: Verify no broken Bazel references**

Run: `bazel test //overlays/prod/... --test_tag_filters=template`
Expected: All template tests pass, no references to deleted signoz-mcp

**Step 7: Commit**

```bash
git add -A charts/signoz-mcp/ overlays/prod/signoz-mcp/ charts/context-forge/
git commit -m "refactor: remove signoz-mcp chart and overlay, migrate to mcp-servers"
```

---

### Task 10: Final validation

**Step 1: Run full lint and template tests**

Run: `bazel test //charts/mcp-servers:lint_test //overlays/prod/mcp-servers:template_test`
Expected: Both PASS

**Step 2: Run format check**

Run: `format`
Expected: No uncommitted formatting changes

**Step 3: Run full test suite**

Run: `bazel test //...`
Expected: All tests pass

**Step 4: Commit any formatting fixes**

```bash
git add -A && git commit -m "style: format"
```
