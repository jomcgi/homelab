# Shared Deployment Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `homelab.deployment` template to the shared library chart that renders a complete Deployment from a standardized values structure, then migrate 7 standard deployments to use it.

**Architecture:** A single `_deployment.tpl` in `projects/shared/helm/homelab-library/chart/templates/` that accepts a component name and reads all config from `.Values.<component>`. Each chart's deployment file becomes a one-liner `include`. The template uses existing `homelab.componentLabels` and `homelab.componentSelectorLabels` helpers.

**Tech Stack:** Helm templates (Go templates), YAML, `helm template` for validation

---

### Task 1: Write the deployment template

**Files:**

- Create: `projects/shared/helm/homelab-library/chart/templates/_deployment.tpl`

**Step 1: Create the template file**

Write `_deployment.tpl` with the following content. Key design decisions inline:

- Looks up component values via `index .context.Values .component`
- Defaults: `enabled=true`, `replicas=1`, `containerPort=8080`, probe paths `/health`
- Always adds a `/tmp` emptyDir volume; merges with user-supplied `volumes`/`volumeMounts`
- Pod security context: component-level falls back to global
- Container security context: component-level falls back to global
- Image pull secrets: reads from global `imagePullSecret.enabled`

```gotemplate
{{/*
Deployment resource.
Renders a complete Deployment for a named component.
All config is read from .Values.<component> by convention.

Usage:
  {{- include "homelab.deployment" (dict "context" . "component" "api") }}

Required values under .<component>:
  image.repository, image.tag, image.pullPolicy

Optional values (with defaults):
  enabled (true), replicas (1), containerPort (8080),
  probes.liveness.path ("/health"), probes.readiness.path ("/health"),
  env ([]), resources ({}), volumes ([]), volumeMounts ([]),
  podAnnotations ({}), podSecurityContext (falls back to global),
  securityContext (falls back to global)
*/}}
{{- define "homelab.deployment" -}}
{{- $ctx := .context -}}
{{- $component := .component -}}
{{- $vals := index $ctx.Values $component -}}
{{- if (default true $vals.enabled) }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "homelab.fullname" $ctx }}-{{ $component }}
  labels:
    {{- include "homelab.componentLabels" (dict "context" $ctx "component" $component) | nindent 4 }}
spec:
  replicas: {{ $vals.replicas | default 1 }}
  selector:
    matchLabels:
      {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $component) | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $component) | nindent 8 }}
      {{- with $vals.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      {{- if $ctx.Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- else if $ctx.Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml $ctx.Values.imagePullSecrets | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "homelab.serviceAccountName" $ctx }}
      securityContext:
        {{- $podSec := default $ctx.Values.podSecurityContext $vals.podSecurityContext -}}
        {{- toYaml $podSec | nindent 8 }}
      containers:
        - name: {{ $component }}
          image: "{{ $vals.image.repository }}:{{ $vals.image.tag }}"
          imagePullPolicy: {{ $vals.image.pullPolicy }}
          securityContext:
            {{- $sec := default $ctx.Values.securityContext $vals.securityContext -}}
            {{- toYaml $sec | nindent 12 }}
          ports:
            - name: http
              containerPort: {{ $vals.containerPort | default 8080 }}
              protocol: TCP
          {{- with $vals.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          livenessProbe:
            httpGet:
              path: {{ dig "probes" "liveness" "path" "/health" $vals }}
              port: http
            initialDelaySeconds: {{ dig "probes" "liveness" "initialDelaySeconds" 10 $vals }}
            periodSeconds: {{ dig "probes" "liveness" "periodSeconds" 10 $vals }}
            timeoutSeconds: {{ dig "probes" "liveness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "liveness" "failureThreshold" 3 $vals }}
          readinessProbe:
            httpGet:
              path: {{ dig "probes" "readiness" "path" "/health" $vals }}
              port: http
            initialDelaySeconds: {{ dig "probes" "readiness" "initialDelaySeconds" 5 $vals }}
            periodSeconds: {{ dig "probes" "readiness" "periodSeconds" 5 $vals }}
            timeoutSeconds: {{ dig "probes" "readiness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "readiness" "failureThreshold" 3 $vals }}
          {{- with $vals.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            {{- with $vals.volumeMounts }}
            {{- toYaml . | nindent 12 }}
            {{- end }}
      volumes:
        - name: tmp
          emptyDir: {}
        {{- with $vals.volumes }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      {{- with $ctx.Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $ctx.Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $ctx.Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
{{- end }}
{{- end }}
```

**Step 2: Validate template syntax**

Run: `helm template test projects/shared/helm/homelab-library/chart/`
Expected: No output (library charts don't render directly), no syntax errors.

**Step 3: Commit**

```bash
git add projects/shared/helm/homelab-library/chart/templates/_deployment.tpl
git commit -m "feat(homelab-library): add shared deployment template"
```

---

### Task 2: Migrate trips/imgproxy (simplest deployment)

The simplest of the 7 — no volumes, no image pull secrets, straightforward env vars.

**Files:**

- Modify: `projects/trips/chart/templates/imgproxy-deployment.yaml`
- Modify: `projects/trips/chart/values.yaml` (add `containerPort`, `env`, restructure `probes`)

**Step 1: Capture current rendered output**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-before.yaml
```

**Step 2: Add missing values fields to `projects/trips/chart/values.yaml`**

Under `imgproxy:`, add `containerPort` and `env` fields. The env vars currently live inline in the deployment template and need to move to values:

```yaml
imgproxy:
  enabled: true
  replicas: 2
  containerPort: 8080
  image:
    repository: darthsim/imgproxy
    tag: "v3.25.0"
    pullPolicy: IfNotPresent
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
    fsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
  env:
    - name: IMGPROXY_USE_S3
      value: "true"
    - name: IMGPROXY_S3_ENDPOINT
      value: "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    - name: IMGPROXY_S3_REGION
      value: "us-east-1"
    - name: AWS_ACCESS_KEY_ID
      value: "anonymous"
    - name: AWS_SECRET_ACCESS_KEY
      value: "anonymous"
    - name: IMGPROXY_QUALITY
      value: "90"
    - name: IMGPROXY_FORMAT_QUALITY
      value: "webp=92,avif=90,jpeg=90"
    - name: IMGPROXY_ENABLE_WEBP_DETECTION
      value: "true"
    - name: IMGPROXY_ENFORCE_WEBP
      value: "false"
    - name: IMGPROXY_CONCURRENCY
      value: "4"
    - name: IMGPROXY_MAX_SRC_RESOLUTION
      value: "50"
    - name: IMGPROXY_STRIP_METADATA
      value: "true"
    - name: IMGPROXY_STRIP_COLOR_PROFILE
      value: "false"
    - name: IMGPROXY_ALLOW_INSECURE_URLS
      value: "true"
  resources:
    requests:
      cpu: 10m
      memory: 75Mi
    limits:
      cpu: 10m
      memory: 75Mi
```

Note: The `config.*` keys that were previously used to template env vars can be removed since the env vars are now explicit. However, keep the `seaweedfs.endpoint` reference — in the env list, use the literal value since `env` is a plain YAML list (not templated). The deploy `values.yaml` can override the env list if the endpoint differs per environment.

**Step 3: Replace deployment template**

Replace contents of `projects/trips/chart/templates/imgproxy-deployment.yaml` with:

```yaml
{ { - include "homelab.deployment" (dict "context" . "component" "imgproxy") } }
```

**Step 4: Render and diff**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-after.yaml
diff /tmp/trips-before.yaml /tmp/trips-after.yaml
```

Expected: The Deployment resource should be functionally equivalent. Acceptable differences:

- Label format changes (using `homelab.*` instead of `trips.*`)
- Addition of `/tmp` volume mount (wasn't present before)
- Minor probe default differences

Review the diff carefully — any unexpected changes indicate a bug in the template or migration.

**Step 5: Commit**

```bash
git add projects/trips/chart/templates/imgproxy-deployment.yaml projects/trips/chart/values.yaml
git commit -m "refactor(trips): migrate imgproxy deployment to shared template"
```

---

### Task 3: Migrate trips/nginx

Similar to imgproxy but has configmap volumes and a config checksum annotation.

**Files:**

- Modify: `projects/trips/chart/templates/nginx-deployment.yaml`
- Modify: `projects/trips/chart/values.yaml`

**Step 1: Add missing values fields to `projects/trips/chart/values.yaml`**

Under `nginx:`, add `containerPort`, `podSecurityContext`, `securityContext`, `podAnnotations`, `volumes`, and `volumeMounts`. The checksum annotation currently uses a template expression `{{ include ... | sha256sum }}` — this **cannot** move to values since it's dynamic. Instead, keep the deployment file as a two-liner that sets the annotation via values merge, OR accept that nginx keeps a slightly longer deployment file.

**Decision:** For configmap checksum annotations, the deployment template file will need to pre-compute the annotation and pass it via a values override. This is a known limitation. The simplest approach: keep the deployment file at ~3 lines:

```yaml
{{- $_ := set .Values.nginx "podAnnotations" (merge (default dict .Values.nginx.podAnnotations) (dict "checksum/config" (include (print $.Template.BasePath "/nginx-configmap.yaml") . | sha256sum))) }}
{{- include "homelab.deployment" (dict "context" . "component" "nginx") }}
```

Update `nginx` values:

```yaml
nginx:
  enabled: true
  replicas: 1
  containerPort: 8080
  image:
    repository: nginx
    tag: "1.27-alpine"
    pullPolicy: IfNotPresent
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
    fsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    readOnlyRootFilesystem: true
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
  probes:
    liveness:
      path: /health
      initialDelaySeconds: 5
      periodSeconds: 10
    readiness:
      path: /health
      initialDelaySeconds: 2
      periodSeconds: 5
  volumes:
    - name: config
      configMap:
        name: FULLNAME-nginx-config # will need templating — see note below
    - name: cache
      configMap: {}
  volumeMounts:
    - name: config
      mountPath: /etc/nginx/nginx.conf
      subPath: nginx.conf
      readOnly: true
    - name: cache
      mountPath: /var/cache/nginx
  resources:
    requests:
      cpu: 5m
      memory: 16Mi
    limits:
      cpu: 5m
      memory: 16Mi
```

**Problem:** The `volumes` list references `{{ include "trips.fullname" . }}-nginx-config` which is a template expression — plain YAML values can't contain template expressions.

**Solution:** Add support for a `volumesTemplate` field in the deployment template that gets rendered, OR accept that deployments with configmap volumes that reference the release name need a slightly longer template file that constructs the volumes before calling `include`.

**Recommended approach:** Keep the deployment file at ~5 lines where it pre-builds the volumes list:

```yaml
{{- if .Values.nginx.enabled }}
{{- $annotations := dict "checksum/config" (include (print $.Template.BasePath "/nginx-configmap.yaml") . | sha256sum) }}
{{- $_ := set .Values.nginx "podAnnotations" (merge (default dict .Values.nginx.podAnnotations) $annotations) }}
{{- $configVol := dict "name" "config" "configMap" (dict "name" (printf "%s-nginx-config" (include "homelab.fullname" .))) }}
{{- $cacheVol := dict "name" "cache" "emptyDir" dict }}
{{- $_ := set .Values.nginx "volumes" (list $configVol $cacheVol) }}
{{- $configMount := dict "name" "config" "mountPath" "/etc/nginx/nginx.conf" "subPath" "nginx.conf" "readOnly" true }}
{{- $cacheMount := dict "name" "cache" "mountPath" "/var/cache/nginx" }}
{{- $_ := set .Values.nginx "volumeMounts" (list $configMount $cacheMount) }}
{{- include "homelab.deployment" (dict "context" . "component" "nginx") }}
{{- end }}
```

**Step 2: Update the deployment template file and values**

Apply the changes above.

**Step 3: Render and diff**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-after.yaml
diff /tmp/trips-before.yaml /tmp/trips-after.yaml
```

**Step 4: Commit**

```bash
git add projects/trips/chart/templates/nginx-deployment.yaml projects/trips/chart/values.yaml
git commit -m "refactor(trips): migrate nginx deployment to shared template"
```

---

### Task 4: Migrate trips/api

Has env vars with template references (`{{ .Values.nats.url }}`), secret refs, and conditional anti-affinity.

**Files:**

- Modify: `projects/trips/chart/templates/api-deployment.yaml`
- Modify: `projects/trips/chart/values.yaml`

**Step 1: Move env vars to values**

The env vars reference other values (`.Values.nats.url`, `.Values.seaweedfs.endpoint`, etc.). Since env is a plain YAML list in values, use the literal default values. The deploy `values.yaml` can override if needed.

Add to `api:` in chart values:

```yaml
api:
  enabled: true
  replicas: 1
  containerPort: 8000
  image:
    repository: ghcr.io/jomcgi/homelab/projects/trips/backend
    tag: "latest"
    pullPolicy: Always
  securityContext:
    readOnlyRootFilesystem: false
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
  probes:
    liveness:
      path: /health
      initialDelaySeconds: 10
      periodSeconds: 10
    readiness:
      path: /health
      initialDelaySeconds: 5
      periodSeconds: 5
  env:
    - name: HOME
      value: /tmp
    - name: UV_CACHE_DIR
      value: /tmp/.uv-cache
    - name: NATS_URL
      value: "nats://nats.nats.svc.cluster.local:4222"
    - name: S3_ENDPOINT
      value: "http://seaweedfs-s3.seaweedfs.svc.cluster.local:8333"
    - name: S3_BUCKET
      value: "trips"
    - name: TRIP_API_KEY
      valueFrom:
        secretKeyRef:
          name: trips-api-key
          key: credential
          optional: true
    - name: CORS_ORIGINS
      value: "https://trips.jomcgi.dev,http://localhost:5173,http://localhost:3000"
  resources:
    requests:
      cpu: 10m
      memory: 256Mi
    limits:
      cpu: 250m
      memory: 256Mi
```

**Note on anti-affinity:** The current template has conditional anti-affinity when `replicas > 1`. This is a scheduling concern — the shared template reads global `.Values.affinity`. For the trips/api case, the deploy values should set affinity when replicas > 1. Since the deploy values already sets `replicas: 2`, it should also set the affinity there. Alternatively, keep a slightly longer template file that conditionally sets affinity before calling include.

**Step 2: Handle the anti-affinity in the deployment file**

```yaml
{{- if .Values.api.enabled }}
{{- if gt (int (.Values.api.replicas | default 1)) 1 }}
{{- $antiAffinity := dict "podAntiAffinity" (dict "preferredDuringSchedulingIgnoredDuringExecution" (list (dict "weight" 100 "podAffinityTerm" (dict "labelSelector" (dict "matchLabels" (dict "app.kubernetes.io/name" (include "homelab.name" .) "app.kubernetes.io/instance" .Release.Name "app.kubernetes.io/component" "api")) "topologyKey" "kubernetes.io/hostname")))) }}
{{- $_ := set .Values "affinity" $antiAffinity }}
{{- end }}
{{- $annotations := dict "config.linkerd.io/opaque-ports" "4222" }}
{{- $_ := set .Values.api "podAnnotations" (merge (default dict .Values.api.podAnnotations) $annotations) }}
{{- include "homelab.deployment" (dict "context" . "component" "api") }}
{{- end }}
```

**Step 3: Render and diff**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-after.yaml
diff /tmp/trips-before.yaml /tmp/trips-after.yaml
```

**Step 4: Commit**

```bash
git add projects/trips/chart/templates/api-deployment.yaml projects/trips/chart/values.yaml
git commit -m "refactor(trips): migrate api deployment to shared template"
```

---

### Task 5: Migrate ships/ingest

Similar pattern to trips/api — env vars with cross-references, NATS annotation, secret ref.

**Files:**

- Modify: `projects/ships/chart/templates/ingest-deployment.yaml`
- Modify: `projects/ships/chart/values.yaml`

**Step 1: Capture current rendered output**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-before.yaml
```

**Step 2: Move env vars and annotations to values**

Add to `ingest:` in chart values:

```yaml
ingest:
  enabled: true
  containerPort: 8000
  image:
    repository: ghcr.io/jomcgi/homelab/projects/ships/ingest
    tag: "main"
    pullPolicy: IfNotPresent
  replicas: 1
  podAnnotations:
    config.linkerd.io/opaque-ports: "4222"
  env:
    - name: HOME
      value: /tmp
    - name: UV_CACHE_DIR
      value: /tmp/.uv-cache
    - name: SSL_CERT_FILE
      value: /etc/ssl/certs/ca-certificates.crt
    - name: NATS_URL
      value: "nats://nats.nats.svc.cluster.local:4222"
    - name: AISSTREAM_URL
      value: "wss://stream.aisstream.io/v0/stream"
    - name: BOUNDING_BOX
      value: "[[[-2.455379, -173.009262], [71.414709, -32.0327]]]"
    - name: AISSTREAM_API_KEY
      valueFrom:
        secretKeyRef:
          name: marine
          key: ais-stream-api-key
  probes:
    liveness:
      path: /health
      initialDelaySeconds: 10
      periodSeconds: 30
      failureThreshold: 3
    readiness:
      path: /health
      initialDelaySeconds: 5
      periodSeconds: 10
  service:
    type: ClusterIP
    port: 8000
  resources:
    requests:
      cpu: 20m
      memory: 100Mi
    limits:
      cpu: 20m
      memory: 100Mi
```

**Step 3: Replace deployment template**

```yaml
{ { - include "homelab.deployment" (dict "context" . "component" "ingest") } }
```

**Step 4: Render and diff**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-after.yaml
diff /tmp/ships-before.yaml /tmp/ships-after.yaml
```

**Step 5: Commit**

```bash
git add projects/ships/chart/templates/ingest-deployment.yaml projects/ships/chart/values.yaml
git commit -m "refactor(ships): migrate ingest deployment to shared template"
```

---

### Task 6: Migrate ships/frontend

Has custom security context (inline, not from global values), env vars referencing other components.

**Files:**

- Modify: `projects/ships/chart/templates/frontend-deployment.yaml`
- Modify: `projects/ships/chart/values.yaml`

**Step 1: Move env vars and security context to values**

Add to `frontend:` in chart values:

```yaml
frontend:
  enabled: true
  containerPort: 3000
  image:
    repository: ghcr.io/jomcgi/homelab/projects/ships/frontend
    tag: "main"
    pullPolicy: IfNotPresent
  replicas: 1
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
    fsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    readOnlyRootFilesystem: false
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
  env:
    - name: PORT
      value: "3000"
    - name: API_URL
      value: "" # overridden in deployment template to use fullname
    - name: PUBLIC_DIR
      value: /app/public/dist
  probes:
    liveness:
      path: /health
      initialDelaySeconds: 30
      periodSeconds: 10
      failureThreshold: 6
    readiness:
      path: /ready
      initialDelaySeconds: 30
      periodSeconds: 5
      failureThreshold: 60
  service:
    type: ClusterIP
    port: 80
  resources:
    requests:
      cpu: 10m
      memory: 100Mi
    limits:
      cpu: 10m
      memory: 100Mi
```

**Step 2: Handle API_URL template reference**

The `API_URL` env var references `{{ include "marine.fullname" . }}-api:{{ .Values.api.service.port }}`. Use a short preamble:

```yaml
{{- if .Values.frontend.enabled }}
{{- $apiUrl := printf "http://%s-api:%s" (include "homelab.fullname" .) (toString (.Values.api.service.port | default 8000)) }}
{{- $envOverride := list (dict "name" "API_URL" "value" $apiUrl) }}
{{- $existingEnv := without .Values.frontend.env (dict "name" "API_URL" "value" "") }}
{{- $_ := set .Values.frontend "env" (concat $envOverride $existingEnv) }}
{{- include "homelab.deployment" (dict "context" . "component" "frontend") }}
{{- end }}
```

Alternatively, simpler: just hardcode the env list in the template file preamble:

```yaml
{{- if .Values.frontend.enabled }}
{{- $_ := set .Values.frontend "env" (list
  (dict "name" "PORT" "value" "3000")
  (dict "name" "API_URL" "value" (printf "http://%s-api:%v" (include "homelab.fullname" .) (.Values.api.service.port | default 8000)))
  (dict "name" "PUBLIC_DIR" "value" (default "/app/public/dist" .Values.frontend.publicDir))
) }}
{{- include "homelab.deployment" (dict "context" . "component" "frontend") }}
{{- end }}
```

**Step 3: Render and diff**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-after.yaml
diff /tmp/ships-before.yaml /tmp/ships-after.yaml
```

**Step 4: Commit**

```bash
git add projects/ships/chart/templates/frontend-deployment.yaml projects/ships/chart/values.yaml
git commit -m "refactor(ships): migrate frontend deployment to shared template"
```

---

### Task 7: Migrate stargazer/api

Has nginx configmap volumes, optional PVC/testdata volumes, custom image path (`api.nginx.image`).

**Files:**

- Modify: `projects/stargazer/chart/templates/deployment-api.yaml`
- Modify: `projects/stargazer/chart/values.yaml`

**Step 1: Read current stargazer values to understand the full structure**

The stargazer api uses `api.nginx.image` instead of `api.image` — this needs restructuring to match the convention. Rename `api.nginx.image` to `api.image` in values.

**Step 2: Update values and template**

Restructure `api:` values and build volumes in the template file preamble (similar to trips/nginx pattern for configmap references).

**Step 3: Render and diff**

```bash
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /tmp/stargazer-after.yaml
diff /tmp/stargazer-before.yaml /tmp/stargazer-after.yaml
```

**Step 4: Commit**

```bash
git add projects/stargazer/chart/templates/deployment-api.yaml projects/stargazer/chart/values.yaml
git commit -m "refactor(stargazer): migrate api deployment to shared template"
```

---

### Task 8: Migrate grimoire/ws-gateway

Minimal deployment — env vars with secret refs, custom security context.

**Files:**

- Modify: `projects/grimoire/chart/templates/ws-gateway-deployment.yaml`
- Modify: `projects/grimoire/chart/values.yaml`

**Step 1: Capture current rendered output**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /tmp/grimoire-before.yaml
```

**Step 2: Move env vars, security context, probes to values**

Add to `wsGateway:` in chart values. Note: env vars reference `.Values.grimoireSecret.name` and other component values. Use literal values or preamble to resolve.

Probe paths differ: `/healthz` and `/readyz` instead of `/health`.

```yaml
wsGateway:
  replicaCount: 1
  containerPort: 8080
  image:
    repository: ghcr.io/jomcgi/homelab/projects/grimoire/ws-gateway
    tag: latest
    pullPolicy: IfNotPresent
  podSecurityContext:
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    allowPrivilegeEscalation: false
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    capabilities:
      drop:
        - ALL
    readOnlyRootFilesystem: true
  probes:
    liveness:
      path: /healthz
      initialDelaySeconds: 5
    readiness:
      path: /readyz
      initialDelaySeconds: 5
```

**Note:** The `replicaCount` field name differs from convention (`replicas`). The shared template expects `replicas`. Either rename in values or add `replicas` as an alias. Simplest: rename to `replicas` in values and update any references.

**Step 3: Handle env vars with cross-references in template file**

```yaml
{{- $_ := set .Values.wsGateway "replicas" (.Values.wsGateway.replicaCount | default 1) }}
{{- $_ := set .Values.wsGateway "env" (list
  (dict "name" "CF_ACCESS_TEAM" "value" .Values.wsGateway.cfAccessTeam)
  (dict "name" "GOOGLE_API_KEY" "valueFrom" (dict "secretKeyRef" (dict "name" .Values.grimoireSecret.name "key" "google_api_key")))
  (dict "name" "REDIS_ADDR" "value" (printf "%s-redis:%v" (include "homelab.fullname" .) .Values.redis.service.port))
  (dict "name" "REDIS_PASSWORD" "valueFrom" (dict "secretKeyRef" (dict "name" .Values.grimoireSecret.name "key" "redis_password")))
) }}
{{- include "homelab.deployment" (dict "context" . "component" "wsGateway") }}
```

**Step 4: Render and diff**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /tmp/grimoire-after.yaml
diff /tmp/grimoire-before.yaml /tmp/grimoire-after.yaml
```

**Step 5: Commit**

```bash
git add projects/grimoire/chart/templates/ws-gateway-deployment.yaml projects/grimoire/chart/values.yaml
git commit -m "refactor(grimoire): migrate ws-gateway deployment to shared template"
```

---

### Task 9: Clean up unused \_helpers.tpl wrappers

After all migrations, the per-chart component label wrappers (e.g. `marine.ingest.labels`, `marine.api.selectorLabels`) are no longer referenced by deployment templates. Check if service templates or other files still reference them — if not, remove them.

**Files:**

- Modify: `projects/ships/chart/templates/_helpers.tpl`
- Modify: `projects/trips/chart/templates/_helpers.tpl`
- Modify: `projects/grimoire/chart/templates/_helpers.tpl`
- Modify: `projects/stargazer/chart/templates/_helpers.tpl`

**Step 1: Search for references to chart-specific component helpers**

```bash
grep -r "marine\.\(ingest\|api\|frontend\)\.\(labels\|selectorLabels\)" projects/ships/chart/templates/
grep -r "trips\.\(labels\|selectorLabels\)" projects/trips/chart/templates/
grep -r "grimoire\.\(labels\|selectorLabels\)" projects/grimoire/chart/templates/
grep -r "stargazer\.\(labels\|selectorLabels\)" projects/stargazer/chart/templates/
```

**Step 2: Remove unreferenced component wrapper defines**

Only remove defines that are no longer used by any template file. Keep the base wrappers (`marine.fullname`, `marine.labels`, etc.) if service templates still reference them.

**Step 3: Render all charts to verify nothing breaks**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /dev/null
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /dev/null
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /dev/null
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /dev/null
```

**Step 4: Commit**

```bash
git add projects/*/chart/templates/_helpers.tpl
git commit -m "refactor: remove unused component helper wrappers from chart templates"
```

---

### Task 10: Bump library chart version and push PR

**Files:**

- Modify: `projects/shared/helm/homelab-library/chart/Chart.yaml` (bump version)

**Step 1: Bump library chart version**

Change `version: 0.1.0` to `version: 0.2.0` in `Chart.yaml`.

**Step 2: Update all charts' dependency references**

Check if charts pin the library version in their `Chart.yaml` dependencies. If they reference `version: "0.1.0"`, update to `"0.2.0"`.

**Step 3: Final validation — render all charts**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /dev/null
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /dev/null
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /dev/null
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /dev/null
```

All should render without errors.

**Step 4: Commit and push**

```bash
git add projects/shared/helm/homelab-library/chart/Chart.yaml
git commit -m "chore(homelab-library): bump chart version to 0.2.0"
git push -u origin feat/shared-deployment-template
```

**Step 5: Create PR**

```bash
gh pr create --title "feat(homelab-library): add shared deployment template" --body "$(cat <<'EOF'
## Summary
- Adds `homelab.deployment` template to the shared library chart
- Migrates 7 standard deployments to use the shared template: trips/{api,nginx,imgproxy}, ships/{ingest,frontend}, stargazer/api, grimoire/ws-gateway
- Removes unused component helper wrappers from chart _helpers.tpl files
- Reduces ~600 lines of duplicated deployment YAML to one-liner includes

## Test plan
- [ ] `helm template` renders correctly for all 4 charts (ships, trips, stargazer, grimoire)
- [ ] Diff before/after migration shows functionally equivalent output
- [ ] CI passes (format check, Bazel tests)
- [ ] ArgoCD sync succeeds after merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
