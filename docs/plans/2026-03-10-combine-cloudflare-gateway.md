# Combined cloudflare-gateway Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Combine envoy-gateway, cloudflare/ingress, and cloudflare/tunnel into a single `cloudflare-gateway` chart at `projects/platform/cloudflare-gateway/`.

**Architecture:** Single Helm chart with the upstream `gateway-helm` as a subchart dependency. Tunnel templates (cloudflared deployment, configmap, secret, service) and Gateway API templates (GatewayClass, Gateway, EnvoyProxy, service) live as top-level templates. Gateway API resources are gated behind `gateway.enabled`. The subchart is gated behind `envoyGateway.enabled`. Everything deploys to `envoy-gateway-system`.

**Tech Stack:** Helm 3, ArgoCD, Kustomize, Kubernetes Gateway API

---

### Task 1: Create chart scaffolding

**Files:**

- Create: `projects/platform/cloudflare-gateway/Chart.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/_helpers.tpl`

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: cloudflare-gateway
description: Cloudflare ingress stack - Envoy Gateway control plane, Gateway API resources, and Cloudflare Tunnel
type: application
version: 1.0.0
appVersion: "v1.3.2"

dependencies:
  - name: gateway-helm
    repository: oci://docker.io/envoyproxy
    version: v1.3.2
    condition: envoyGateway.enabled

annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.url: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create `_helpers.tpl`**

Combines helpers from both old charts. Template names use `cloudflare-gateway.` prefix. The tunnel fullname helper defaults to `cloudflared` (matching the existing `fullnameOverride`).

```gotemplate
{{/*
Expand the name of the chart.
*/}}
{{- define "cloudflare-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "cloudflare-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "cloudflare-gateway.labels" -}}
helm.sh/chart: {{ include "cloudflare-gateway.chart" . }}
app.kubernetes.io/name: {{ include "cloudflare-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Tunnel fullname - defaults to "cloudflared" to match existing naming.
*/}}
{{- define "cloudflare-gateway.tunnel.fullname" -}}
{{- default "cloudflared" .Values.tunnel.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Tunnel selector labels
*/}}
{{- define "cloudflare-gateway.tunnel.selectorLabels" -}}
app.kubernetes.io/name: cloudflare-tunnel
app.kubernetes.io/instance: {{ .Release.Name }}
app: cloudflared
{{- end }}

{{/*
Tunnel labels
*/}}
{{- define "cloudflare-gateway.tunnel.labels" -}}
helm.sh/chart: {{ include "cloudflare-gateway.chart" . }}
{{ include "cloudflare-gateway.tunnel.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
```

**Step 3: Commit**

```bash
git add projects/platform/cloudflare-gateway/Chart.yaml projects/platform/cloudflare-gateway/templates/_helpers.tpl
git commit -m "feat(cloudflare-gateway): add chart scaffolding with gateway-helm subchart"
```

---

### Task 2: Copy upstream subchart and build dependencies

**Files:**

- Create: `projects/platform/cloudflare-gateway/charts/gateway-helm-v1.3.2.tgz` (copy from envoy-gateway)

**Step 1: Copy the vendored subchart archive**

```bash
mkdir -p projects/platform/cloudflare-gateway/charts
cp projects/platform/envoy-gateway/charts/gateway-helm-v1.3.2.tgz projects/platform/cloudflare-gateway/charts/
```

**Step 2: Commit**

```bash
git add projects/platform/cloudflare-gateway/charts/
git commit -m "feat(cloudflare-gateway): vendor gateway-helm v1.3.2 subchart"
```

---

### Task 3: Add tunnel templates

Port all tunnel templates from `cloudflare/tunnel/templates/` into `cloudflare-gateway/templates/`. Key changes:

- All template names change from `cloudflare-tunnel.*` to `cloudflare-gateway.tunnel.*`
- All values references change from `.Values.X` to `.Values.tunnel.X` (tunnel values are nested)
- Namespace helper removed — everything uses `.Release.Namespace` (ArgoCD sets it to `envoy-gateway-system`)
- Namespace template removed — ArgoCD manages the namespace via `CreateNamespace=true`

**Files:**

- Create: `projects/platform/cloudflare-gateway/templates/tunnel-deployment.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/tunnel-configmap.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/tunnel-secret.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/tunnel-service.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/tunnel-envoy-configmap.yaml`

**Step 1: Create `tunnel-deployment.yaml`**

Ported from `cloudflare/tunnel/templates/deployment.yaml`. Changes:

- Helper references: `cloudflare-tunnel.X` → `cloudflare-gateway.tunnel.X`
- Value references: `.Values.X` → `.Values.tunnel.X`
- Namespace: uses `.Release.Namespace` directly

```gotemplate
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "cloudflare-gateway.tunnel.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "cloudflare-gateway.tunnel.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.tunnel.replicaCount }}
  selector:
    matchLabels:
      {{- include "cloudflare-gateway.tunnel.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/tunnel-configmap.yaml") . | sha256sum }}
        {{- if .Values.tunnel.envoy.enabled }}
        checksum/envoy-config: {{ include (print $.Template.BasePath "/tunnel-envoy-configmap.yaml") . | sha256sum }}
        {{- end }}
      labels:
        {{- include "cloudflare-gateway.tunnel.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.tunnel.priorityClassName }}
      priorityClassName: {{ . }}
      {{- end }}
      {{- with .Values.tunnel.podSecurityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- if and .Values.tunnel.envoy.enabled .Values.tunnel.envoy.transparentProxy.enabled }}
      initContainers:
      - name: iptables-init
        image: "{{ .Values.tunnel.envoy.transparentProxy.iptablesImage }}"
        securityContext:
          capabilities:
            add:
            - NET_ADMIN
          runAsUser: 0
          runAsNonRoot: false
        command:
        - sh
        - -c
        - |
          set -e
          echo "Setting up iptables rules for transparent proxy..."
          ENVOY_UID={{ .Values.tunnel.envoy.securityContext.runAsUser | default 65534 }}
          ENVOY_PORT={{ .Values.tunnel.envoy.transparentProxy.port }}
          iptables -t nat -N ENVOY_REDIRECT || true
          iptables -t nat -F ENVOY_REDIRECT
          iptables -t nat -A ENVOY_REDIRECT -p tcp -j REDIRECT --to-port ${ENVOY_PORT}
          iptables -t nat -N ENVOY_OUTPUT || true
          iptables -t nat -F ENVOY_OUTPUT
          iptables -t nat -A ENVOY_OUTPUT -m owner --uid-owner ${ENVOY_UID} -j RETURN
          iptables -t nat -A ENVOY_OUTPUT -d 127.0.0.1/32 -j RETURN
          iptables -t nat -A ENVOY_OUTPUT -p tcp -j ENVOY_REDIRECT
          iptables -t nat -A OUTPUT -j ENVOY_OUTPUT
          echo "iptables rules configured successfully"
          iptables -t nat -L -n -v
      {{- end }}
      containers:
      {{- if .Values.tunnel.envoy.enabled }}
      - name: envoy
        image: "{{ .Values.tunnel.envoy.image.repository }}:{{ .Values.tunnel.envoy.image.tag }}"
        imagePullPolicy: {{ .Values.tunnel.envoy.image.pullPolicy }}
        args:
        - -c
        - /etc/envoy/envoy.yaml
        ports:
        - containerPort: {{ .Values.tunnel.envoy.proxy.port }}
          name: envoy-proxy
          protocol: TCP
        - containerPort: {{ .Values.tunnel.envoy.admin.port }}
          name: envoy-admin
          protocol: TCP
        {{- if .Values.tunnel.envoy.transparentProxy.enabled }}
        - containerPort: {{ .Values.tunnel.envoy.transparentProxy.port }}
          name: tproxy
          protocol: TCP
        {{- end }}
        volumeMounts:
        - name: envoy-config
          mountPath: /etc/envoy
          readOnly: true
        - name: envoy-tmp
          mountPath: /tmp
        {{- with .Values.tunnel.envoy.securityContext }}
        securityContext:
          {{- toYaml . | nindent 10 }}
        {{- end }}
        {{- with .Values.tunnel.envoy.resources }}
        resources:
          {{- toYaml . | nindent 10 }}
        {{- end }}
      {{- end }}
      - name: cloudflared
        image: "{{ .Values.tunnel.image.repository }}:{{ .Values.tunnel.image.tag }}"
        imagePullPolicy: {{ .Values.tunnel.image.pullPolicy }}
        args:
        - tunnel
        - --config
        - /etc/cloudflared/config/config.yaml
        {{- if .Values.tunnel.protocol }}
        - --protocol
        - {{ .Values.tunnel.protocol }}
        {{- end }}
        - run
        {{- if eq .Values.tunnel.secret.type "onepassword" }}
        - $(TUNNEL_ID)
        {{- else }}
        - {{ .Values.tunnel.id }}
        {{- end }}
        {{- if eq .Values.tunnel.secret.type "onepassword" }}
        env:
        - name: TUNNEL_ID
          valueFrom:
            secretKeyRef:
              name: cloudflare-tunnel-credentials
              key: tunnel-id
        - name: TUNNEL_NAME
          valueFrom:
            secretKeyRef:
              name: cloudflare-tunnel-credentials
              key: tunnel-name
        {{- end }}
        ports:
        - containerPort: {{ .Values.tunnel.service.port }}
          name: cloudflared
        {{- if .Values.tunnel.livenessProbe }}
        livenessProbe:
          {{- toYaml .Values.tunnel.livenessProbe | nindent 10 }}
        {{- end }}
        {{- if .Values.tunnel.readinessProbe }}
        readinessProbe:
          {{- toYaml .Values.tunnel.readinessProbe | nindent 10 }}
        {{- end }}
        volumeMounts:
        - name: config
          mountPath: /etc/cloudflared/config
          readOnly: true
        - name: creds
          mountPath: /etc/cloudflared/creds/credentials.json
          subPath: credentials
        securityContext:
          {{- toYaml .Values.tunnel.securityContext | nindent 10 }}
        {{- with .Values.tunnel.resources }}
        resources:
          {{- toYaml . | nindent 10 }}
        {{- end }}
      volumes:
      - name: creds
        secret:
          secretName: "cloudflare-tunnel-credentials"
      - name: config
        configMap:
          name: {{ include "cloudflare-gateway.tunnel.fullname" . }}
          items:
          - key: config.yaml
            path: config.yaml
      {{- if .Values.tunnel.envoy.enabled }}
      - name: envoy-config
        configMap:
          name: {{ include "cloudflare-gateway.tunnel.fullname" . }}-envoy
          items:
          - key: envoy.yaml
            path: envoy.yaml
      - name: envoy-tmp
        emptyDir:
          medium: Memory
          sizeLimit: 64Mi
      {{- end }}
      {{- with .Values.tunnel.topologySpreadConstraints }}
      topologySpreadConstraints:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tunnel.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tunnel.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tunnel.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

**Step 2: Create `tunnel-configmap.yaml`**

```gotemplate
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "cloudflare-gateway.tunnel.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "cloudflare-gateway.tunnel.labels" . | nindent 4 }}
data:
  config.yaml: |
    tunnel: {{ .Values.tunnel.name }}
    credentials-file: /etc/cloudflared/creds/credentials.json
    {{- if .Values.tunnel.metrics.enabled }}
    metrics: {{ .Values.tunnel.metrics.address }}
    {{- end }}
    no-autoupdate: {{ .Values.tunnel.noAutoupdate }}
    ingress:
    {{- range .Values.tunnel.ingress.routes }}
    - hostname: {{ .hostname }}
      service: {{ .service }}
      {{- if .originRequest }}
      originRequest:
        {{- toYaml .originRequest | nindent 8 }}
      {{- end }}
    {{- end }}
    - service: {{ .Values.tunnel.ingress.catchAll.service }}
```

**Step 3: Create `tunnel-secret.yaml`**

```gotemplate
{{- if eq .Values.tunnel.secret.type "onepassword" }}
apiVersion: onepassword.com/v1
kind: OnePasswordItem
metadata:
  name: cloudflare-tunnel-credentials
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "cloudflare-gateway.tunnel.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.tunnel.secret.onepassword.itemPath | quote }}
{{- else if eq .Values.tunnel.secret.type "manual" }}
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-tunnel-credentials
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "cloudflare-gateway.tunnel.labels" . | nindent 4 }}
type: Opaque
data:
  credentials: {{ .Values.tunnel.secret.manual.credentialsJson | b64enc }}
{{- end }}
{{- /* For external secrets, no resource is created - user must provide existing secret */ -}}
```

**Step 4: Create `tunnel-service.yaml`**

```gotemplate
apiVersion: v1
kind: Service
metadata:
  name: {{ include "cloudflare-gateway.tunnel.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "cloudflare-gateway.tunnel.labels" . | nindent 4 }}
spec:
  type: {{ .Values.tunnel.service.type }}
  ports:
    - port: {{ .Values.tunnel.service.port }}
      targetPort: {{ .Values.tunnel.service.port }}
      protocol: TCP
      name: cloudflared
  selector: {{- include "cloudflare-gateway.tunnel.selectorLabels" . | nindent 4 }}
```

**Step 5: Create `tunnel-envoy-configmap.yaml`**

This is the existing envoy sidecar configmap, ported with `.Values.tunnel.envoy.*` and `.Values.tunnel.metrics.*` paths.

Copy from `projects/platform/cloudflare/tunnel/templates/envoy-configmap.yaml` with these replacements:

- `{{- if .Values.envoy.enabled }}` → `{{- if .Values.tunnel.envoy.enabled }}`
- All `.Values.envoy.` → `.Values.tunnel.envoy.`
- All `.Values.metrics.` → `.Values.tunnel.metrics.`
- `cloudflare-tunnel.fullname` → `cloudflare-gateway.tunnel.fullname`
- `cloudflare-tunnel.labels` → `cloudflare-gateway.tunnel.labels`
- `{{ include "cloudflare-tunnel.namespace" . }}` → `{{ .Release.Namespace }}`

**Step 6: Commit**

```bash
git add projects/platform/cloudflare-gateway/templates/tunnel-*.yaml
git commit -m "feat(cloudflare-gateway): add tunnel templates"
```

---

### Task 4: Add gateway API templates

Port all templates from `cloudflare/ingress/templates/` into `cloudflare-gateway/templates/`. Each template is wrapped in `{{- if .Values.gateway.enabled }}`. Value paths change from `.Values.gatewayClass.*` etc to `.Values.gateway.*`.

**Files:**

- Create: `projects/platform/cloudflare-gateway/templates/gateway-class.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/gateway.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/gateway-envoyproxy.yaml`
- Create: `projects/platform/cloudflare-gateway/templates/gateway-service.yaml`

**Step 1: Create `gateway-class.yaml`**

```gotemplate
{{- if .Values.gateway.enabled }}
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: {{ .Values.gateway.className }}
  labels: {{- include "cloudflare-gateway.labels" . | nindent 4 }}
spec:
  controllerName: {{ .Values.gateway.controllerName }}
  parametersRef:
    group: gateway.envoyproxy.io
    kind: EnvoyProxy
    name: {{ .Values.gateway.envoyProxy.name }}
    namespace: {{ .Release.Namespace }}
{{- end }}
```

**Step 2: Create `gateway.yaml`**

```gotemplate
{{- if .Values.gateway.enabled }}
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {{ .Values.gateway.name }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "cloudflare-gateway.labels" . | nindent 4 }}
spec:
  gatewayClassName: {{ .Values.gateway.className }}
  listeners:
    - name: http
      protocol: HTTP
      port: {{ .Values.gateway.listener.port }}
      allowedRoutes:
        namespaces:
          from: All
{{- end }}
```

**Step 3: Create `gateway-envoyproxy.yaml`**

```gotemplate
{{- if .Values.gateway.enabled }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: {{ .Values.gateway.envoyProxy.name }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "cloudflare-gateway.labels" . | nindent 4 }}
spec:
  provider:
    type: Kubernetes
    kubernetes:
      envoyDeployment:
        container:
          resources: {{- toYaml .Values.gateway.envoyProxy.resources | nindent 12 }}
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 65532
            runAsGroup: 65532
            capabilities:
              drop:
                - ALL
            seccompProfile:
              type: RuntimeDefault
{{- end }}
```

**Step 4: Create `gateway-service.yaml`**

```gotemplate
{{- if .Values.gateway.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ .Values.gateway.service.name }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "cloudflare-gateway.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: {{ .Values.gateway.service.port }}
      targetPort: {{ add .Values.gateway.listener.port 10000 }}
      protocol: TCP
      name: http
  selector:
    gateway.envoyproxy.io/owning-gateway-name: {{ .Values.gateway.name }}
    gateway.envoyproxy.io/owning-gateway-namespace: {{ .Release.Namespace }}
{{- end }}
```

**Step 5: Commit**

```bash
git add projects/platform/cloudflare-gateway/templates/gateway*.yaml
git commit -m "feat(cloudflare-gateway): add gateway API templates with enable/disable toggle"
```

---

### Task 5: Create values files

**Files:**

- Create: `projects/platform/cloudflare-gateway/values.yaml`
- Create: `projects/platform/cloudflare-gateway/values-prod.yaml`

**Step 1: Create `values.yaml`**

This is the merged default values from all three charts. Structure:

- `envoyGateway.enabled` — controls subchart condition
- `gateway-helm:` — subchart values (from old envoy-gateway/values.yaml)
- `gateway:` — Gateway API resources (from old cloudflare-ingress values)
- `tunnel:` — cloudflared config (from old cloudflare-tunnel values, nested under `tunnel:`)

```yaml
# --- Envoy Gateway control plane (subchart) ---
envoyGateway:
  enabled: true

gateway-helm:
  deployment:
    envoyGateway:
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi
  config:
    envoyGateway:
      provider:
        type: Kubernetes

# --- Gateway API resources (GatewayClass, Gateway, EnvoyProxy) ---
gateway:
  enabled: true
  name: cloudflare-ingress
  className: cloudflare-ingress
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
  listener:
    port: 80
  envoyProxy:
    name: cloudflare-ingress-proxy
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
      limits:
        cpu: 500m
        memory: 256Mi
  service:
    name: cloudflare-ingress
    port: 80

# --- Cloudflare Tunnel ---
tunnel:
  replicaCount: 2
  fullnameOverride: "cloudflared"

  image:
    repository: cloudflare/cloudflared
    tag: "2025.4.0"
    pullPolicy: IfNotPresent

  # Tunnel identity (set from secret when using OnePassword)
  id: ""
  name: ""
  protocol: ""
  noAutoupdate: true

  secret:
    type: onepassword
    onepassword:
      itemPath: ""
    manual:
      credentialsJson: ""

  ingress:
    routes: []
    catchAll:
      service: http_status:404

  service:
    type: ClusterIP
    port: 2000

  resources: {}
  priorityClassName: ""
  topologySpreadConstraints: []
  nodeSelector: {}
  tolerations: []
  affinity: {}
  podSecurityContext: {}

  securityContext:
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    runAsNonRoot: true
    runAsUser: 65532
    capabilities:
      drop:
        - ALL
    seccompProfile:
      type: RuntimeDefault

  livenessProbe:
    exec:
      command:
        - cloudflared
        - tunnel
        - --metrics
        - 127.0.0.1:2000
        - ready
    failureThreshold: 6
    initialDelaySeconds: 30
    periodSeconds: 10
    timeoutSeconds: 5

  readinessProbe:
    exec:
      command:
        - cloudflared
        - tunnel
        - --metrics
        - 127.0.0.1:2000
        - ready
    failureThreshold: 3
    initialDelaySeconds: 10
    periodSeconds: 5
    timeoutSeconds: 5

  metrics:
    enabled: true
    address: "127.0.0.1:2000"

  envoy:
    enabled: false
    image:
      repository: envoyproxy/envoy
      tag: "v1.31-latest"
      pullPolicy: IfNotPresent
    admin:
      port: 9901
    proxy:
      port: 8000
    transparentProxy:
      enabled: false
      port: 15001
      iptablesImage: "docker.io/istio/proxyv2:1.20.0"
    securityContext:
      runAsUser: 65534
      runAsNonRoot: true
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
      capabilities:
        drop:
          - ALL
      seccompProfile:
        type: RuntimeDefault
    tracing:
      enabled: true
      otlpEndpoint: "signoz-otel-collector.signoz.svc.cluster.local:4317"
      serviceName: "cloudflare-tunnel"
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 256Mi
```

**Step 2: Create `values-prod.yaml`**

Merges prod overrides from all three old files.

```yaml
# Production overrides for cloudflare-gateway

# --- Envoy Gateway control plane ---
gateway-helm:
  deployment:
    envoyGateway:
      priorityClassName: system-cluster-critical
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi
      securityContext:
        readOnlyRootFilesystem: true
  config:
    envoyGateway:
      provider:
        type: Kubernetes

# --- Cloudflare Tunnel ---
tunnel:
  secret:
    onepassword:
      itemPath: "vaults/k8s-homelab/items/cluster-cloudflare-tunnel"

  ingress:
    routes:
      - hostname: argocd.jomcgi.dev
        service: http://argocd-server.argocd.svc.cluster.local:80
      - hostname: longhorn.jomcgi.dev
        service: http://longhorn-frontend.longhorn.svc.cluster.local:80
      - hostname: mcp.jomcgi.dev
        service: http://mcp-oauth-proxy.mcp-gateway.svc.cluster.local:8080
      - hostname: n8n.jomcgi.dev
        service: http://n8n.n8n.svc.cluster.local:80
      - hostname: feeds.jomcgi.dev
        service: http://freshrss.freshrss.svc.cluster.local:80
      - hostname: signoz.jomcgi.dev
        service: http://signoz.signoz.svc.cluster.local:8080
      - hostname: img.jomcgi.dev
        service: http://trips-nginx.trips.svc.cluster.local:80
      - hostname: grimoire.jomcgi.dev
        service: http://grimoire-frontend.grimoire.svc.cluster.local:8080
      - hostname: ships.jomcgi.dev
        service: http://marine-frontend.marine.svc.cluster.local:80
      - hostname: todo.jomcgi.dev
        service: http://todo-public.todo.svc.cluster.local:80
      - hostname: todo-admin.jomcgi.dev
        service: http://todo-admin.todo.svc.cluster.local:8080
      - hostname: api.jomcgi.dev
        service: http://api-gateway.api-gateway.svc.cluster.local:80
        originRequest:
          keepAliveConnections: 100
          keepAliveTimeout: 90s
          tcpKeepAlive: 30s
    catchAll:
      service: http://cloudflare-ingress.envoy-gateway-system.svc.cluster.local:80

  priorityClassName: system-cluster-critical

  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: kubernetes.io/hostname
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          app.kubernetes.io/name: cloudflare-tunnel

  resources:
    requests:
      cpu: 25m
      memory: 64Mi
    limits:
      cpu: 250m
      memory: 256Mi

  envoy:
    enabled: false
```

**Step 3: Commit**

```bash
git add projects/platform/cloudflare-gateway/values.yaml projects/platform/cloudflare-gateway/values-prod.yaml
git commit -m "feat(cloudflare-gateway): add merged values files"
```

---

### Task 6: Create ArgoCD application and kustomization

**Files:**

- Create: `projects/platform/cloudflare-gateway/application.yaml`
- Create: `projects/platform/cloudflare-gateway/kustomization.yaml`

**Step 1: Create `application.yaml`**

Single Application replacing all three. Key settings:

- `ServerSideApply=true` for CRDs
- `CreateNamespace=true` for `envoy-gateway-system`
- `managedNamespaceMetadata` with `linkerd.io/inject: disabled`
- Finalizer for cleanup

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cloudflare-gateway
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: projects/platform/cloudflare-gateway
    helm:
      releaseName: cloudflare-gateway
      valueFiles:
        - values.yaml
        - values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: envoy-gateway-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    managedNamespaceMetadata:
      annotations:
        linkerd.io/inject: disabled
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

**Step 2: Create `kustomization.yaml`**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

**Step 3: Commit**

```bash
git add projects/platform/cloudflare-gateway/application.yaml projects/platform/cloudflare-gateway/kustomization.yaml
git commit -m "feat(cloudflare-gateway): add ArgoCD application"
```

---

### Task 7: Update platform kustomization and remove old components

**Files:**

- Modify: `projects/platform/kustomization.yaml`
- Delete: `projects/platform/envoy-gateway/` (entire directory)
- Delete: `projects/platform/cloudflare/ingress/` (entire directory)
- Delete: `projects/platform/cloudflare/tunnel/` (entire directory)

**Step 1: Update `projects/platform/kustomization.yaml`**

Remove the three old entries and add the single new one. The new entry replaces:

- `./cloudflare/ingress`
- `./cloudflare/tunnel`
- `./envoy-gateway`

The comment about CRD ordering is still relevant — `cloudflare-gateway` installs CRDs and must be before linkerd.

Replace:

```yaml
  - ./cloudflare/ingress
  - ./cloudflare/tunnel
  ...
  - ./envoy-gateway # Installs Gateway API CRDs; must be before linkerd
```

With:

```yaml
- ./cloudflare-gateway # Envoy Gateway + Gateway API + Cloudflare Tunnel; CRDs must be before linkerd
```

**Step 2: Delete old directories**

```bash
rm -rf projects/platform/envoy-gateway
rm -rf projects/platform/cloudflare/ingress
rm -rf projects/platform/cloudflare/tunnel
```

**Step 3: Check if `projects/platform/cloudflare/` is now empty**

If so, remove it. If other content exists (other cloudflare services), leave it.

```bash
ls projects/platform/cloudflare/
# If empty, remove:
rmdir projects/platform/cloudflare
```

**Step 4: Commit**

```bash
git add -A projects/platform/
git commit -m "refactor: replace envoy-gateway, cloudflare/ingress, cloudflare/tunnel with cloudflare-gateway"
```

---

### Task 8: Validate with helm template

**Step 1: Render templates to verify correctness**

```bash
helm template cloudflare-gateway projects/platform/cloudflare-gateway/ -f projects/platform/cloudflare-gateway/values.yaml -f projects/platform/cloudflare-gateway/values-prod.yaml
```

Verify output includes:

- Envoy Gateway control plane resources (from subchart)
- GatewayClass named `cloudflare-ingress`
- Gateway named `cloudflare-ingress`
- EnvoyProxy named `cloudflare-ingress-proxy`
- Service named `cloudflare-ingress` targeting envoy pods
- cloudflared Deployment with 2 replicas
- cloudflared ConfigMap with all routes
- OnePasswordItem for credentials
- cloudflared Service on port 2000
- All resources in `envoy-gateway-system` namespace

**Step 2: Verify gateway disabled mode**

```bash
helm template cloudflare-gateway projects/platform/cloudflare-gateway/ -f projects/platform/cloudflare-gateway/values.yaml --set gateway.enabled=false --set envoyGateway.enabled=false
```

Verify: only tunnel resources are rendered, no GatewayClass/Gateway/EnvoyProxy/subchart.

**Step 3: Fix any template rendering issues, re-commit if needed**

---

### Task 9: Run format and final commit

**Step 1: Run format**

```bash
format
```

This regenerates `projects/home-cluster/kustomization.yaml` (the ArgoCD root) and formats all files.

**Step 2: Commit formatting changes if any**

```bash
git add -A
git commit -m "style: auto-format"
```

**Step 3: Push and create PR**

```bash
git push -u origin chore/combine-cloudflare-gateway
gh pr create --title "refactor: combine ingress charts into cloudflare-gateway" --body "$(cat <<'EOF'
## Summary
- Combines `envoy-gateway`, `cloudflare/ingress`, and `cloudflare/tunnel` into a single `cloudflare-gateway` chart
- Gateway API resources (GatewayClass, Gateway, EnvoyProxy) toggleable via `gateway.enabled`
- Envoy Gateway control plane subchart toggleable via `envoyGateway.enabled`
- Tunnel moves from `ingress` namespace to `envoy-gateway-system`
- Single ArgoCD Application replaces 3 separate apps

## Migration
ArgoCD will delete resources from old apps and recreate from new app. Brief reconciliation period expected.

## Test plan
- [ ] `helm template` renders all expected resources
- [ ] `helm template` with `gateway.enabled=false` only renders tunnel resources
- [ ] CI passes (format check, Bazel tests)
- [ ] ArgoCD syncs successfully after merge
- [ ] Tunnel pods running in `envoy-gateway-system`
- [ ] Gateway API resources created
- [ ] Traffic routing works end-to-end

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
