# Shared Library Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the shared Helm library chart with StatefulSet template, exec probe support, custom args support, and port name customization — then migrate grimoire/redis, grimoire/frontend, and ships/api to use the shared templates.

**Architecture:** The homelab-library chart (library type) provides reusable Go template functions that consuming charts call via `{{ include }}`. We add new template functions and extend existing ones, then update consumers to use them instead of custom templates. All changes are backward compatible.

**Tech Stack:** Helm library chart (Go templates), Kustomize, ArgoCD GitOps

---

### Task 1: Add exec probe support and args to `_deployment.tpl`

**Files:**

- Modify: `projects/shared/helm/homelab-library/chart/templates/_deployment.tpl`

**Step 1: Add args support after `imagePullPolicy` line (line 66)**

Replace lines 66-93 of `_deployment.tpl` (from `imagePullPolicy` through readiness probe) with:

```yaml
          imagePullPolicy: {{ $vals.image.pullPolicy }}
          securityContext:
            {{- $sec := default $ctx.Values.securityContext $vals.securityContext -}}
            {{- toYaml $sec | nindent 12 }}
          {{- with $vals.args }}
          args:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          ports:
            - name: {{ $vals.portName | default "http" }}
              containerPort: {{ $vals.containerPort | default 8080 }}
              protocol: TCP
          {{- with $vals.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          livenessProbe:
            {{- if (dig "probes" "liveness" "exec" nil $vals) }}
            exec:
              command:
                {{- toYaml (dig "probes" "liveness" "exec" (list) $vals) | nindent 16 }}
            {{- else }}
            httpGet:
              path: {{ dig "probes" "liveness" "path" "/health" $vals }}
              port: {{ $vals.portName | default "http" }}
            {{- end }}
            initialDelaySeconds: {{ dig "probes" "liveness" "initialDelaySeconds" 10 $vals }}
            periodSeconds: {{ dig "probes" "liveness" "periodSeconds" 10 $vals }}
            timeoutSeconds: {{ dig "probes" "liveness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "liveness" "failureThreshold" 3 $vals }}
          readinessProbe:
            {{- if (dig "probes" "readiness" "exec" nil $vals) }}
            exec:
              command:
                {{- toYaml (dig "probes" "readiness" "exec" (list) $vals) | nindent 16 }}
            {{- else }}
            httpGet:
              path: {{ dig "probes" "readiness" "path" "/health" $vals }}
              port: {{ $vals.portName | default "http" }}
            {{- end }}
            initialDelaySeconds: {{ dig "probes" "readiness" "initialDelaySeconds" 5 $vals }}
            periodSeconds: {{ dig "probes" "readiness" "periodSeconds" 5 $vals }}
            timeoutSeconds: {{ dig "probes" "readiness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "readiness" "failureThreshold" 3 $vals }}
```

Key changes from the original:

- `args` block added (no-op when not set)
- Port name uses `$vals.portName | default "http"` instead of hardcoded `"http"` (needed for redis)
- Probe type switches on `probes.liveness.exec` / `probes.readiness.exec`
- `httpGet` port reference uses same `portName` variable

**Step 2: Update the doc comment at the top of `_deployment.tpl`**

Add to the "Optional values" section:

```
  args ([]), portName ("http"),
  probes.liveness.exec ([]) — if set, uses exec probe instead of httpGet,
  probes.readiness.exec ([]) — same for readiness,
```

**Step 3: Verify with helm template**

Run from the worktree root:

```bash
helm template test projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml 2>&1 | head -80
```

Expected: renders successfully, no errors, existing httpGet probes unchanged.

**Step 4: Commit**

```bash
git add projects/shared/helm/homelab-library/chart/templates/_deployment.tpl
git commit -m "feat(shared): add exec probes, args, and portName to deployment template"
```

---

### Task 2: Create `_statefulset.tpl`

**Files:**

- Create: `projects/shared/helm/homelab-library/chart/templates/_statefulset.tpl`

**Step 1: Write the StatefulSet template**

This mirrors `_deployment.tpl` (with the Task 1 enhancements included) but:

- `kind: StatefulSet` instead of `Deployment`
- Adds `serviceName` field
- Adds `volumeClaimTemplates` section from `.<component>.persistence`
- Mounts the persistent volume at `persistence.mountPath`

```yaml
{{/*
StatefulSet resource.
Renders a complete StatefulSet for a named component with persistent storage.
All config is read from .Values.<component> by convention.

Usage:
  {{- include "homelab.statefulset" (dict "context" . "component" "api") }}
  {{- include "homelab.statefulset" (dict "context" . "component" "db" "componentName" "database") }}

Required values under .<component>:
  image.repository, image.tag, image.pullPolicy
  persistence.size, persistence.mountPath

Optional values (with defaults):
  enabled (true), replicas (1), containerPort (8080), portName ("http"),
  args ([]),
  probes.liveness.path ("/health"), probes.readiness.path ("/health"),
  probes.liveness.exec ([]) — if set, uses exec probe instead of httpGet,
  probes.readiness.exec ([]) — same for readiness,
  env ([]), resources ({}), volumes ([]), volumeMounts ([]),
  podAnnotations ({}), podSecurityContext (falls back to global),
  securityContext (falls back to global),
  persistence.storageClassName (unset — uses cluster default),
  persistence.volumeName ("data")

Optional dict keys:
  componentName — override the name used in metadata/labels/container
                  (defaults to component); useful when the values key is
                  camelCase but the Kubernetes resource name should be
                  kebab-case.
*/}}
{{- define "homelab.statefulset" -}}
{{- $ctx := .context -}}
{{- $component := .component -}}
{{- $name := default $component .componentName -}}
{{- $vals := index $ctx.Values $component -}}
{{- $volName := dig "persistence" "volumeName" "data" $vals -}}
{{- if (default true $vals.enabled) }}
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "homelab.fullname" $ctx }}-{{ $name }}
  labels:
    {{- include "homelab.componentLabels" (dict "context" $ctx "component" $name) | nindent 4 }}
spec:
  serviceName: {{ include "homelab.fullname" $ctx }}-{{ $name }}
  replicas: {{ $vals.replicas | default 1 }}
  selector:
    matchLabels:
      {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $name) | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $name) | nindent 8 }}
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
        - name: {{ $name }}
          image: "{{ $vals.image.repository }}:{{ $vals.image.tag }}"
          imagePullPolicy: {{ $vals.image.pullPolicy }}
          securityContext:
            {{- $sec := default $ctx.Values.securityContext $vals.securityContext -}}
            {{- toYaml $sec | nindent 12 }}
          {{- with $vals.args }}
          args:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          ports:
            - name: {{ $vals.portName | default "http" }}
              containerPort: {{ $vals.containerPort | default 8080 }}
              protocol: TCP
          {{- with $vals.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          livenessProbe:
            {{- if (dig "probes" "liveness" "exec" nil $vals) }}
            exec:
              command:
                {{- toYaml (dig "probes" "liveness" "exec" (list) $vals) | nindent 16 }}
            {{- else }}
            httpGet:
              path: {{ dig "probes" "liveness" "path" "/health" $vals }}
              port: {{ $vals.portName | default "http" }}
            {{- end }}
            initialDelaySeconds: {{ dig "probes" "liveness" "initialDelaySeconds" 10 $vals }}
            periodSeconds: {{ dig "probes" "liveness" "periodSeconds" 10 $vals }}
            timeoutSeconds: {{ dig "probes" "liveness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "liveness" "failureThreshold" 3 $vals }}
          readinessProbe:
            {{- if (dig "probes" "readiness" "exec" nil $vals) }}
            exec:
              command:
                {{- toYaml (dig "probes" "readiness" "exec" (list) $vals) | nindent 16 }}
            {{- else }}
            httpGet:
              path: {{ dig "probes" "readiness" "path" "/health" $vals }}
              port: {{ $vals.portName | default "http" }}
            {{- end }}
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
            - name: {{ $volName }}
              mountPath: {{ $vals.persistence.mountPath }}
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
  volumeClaimTemplates:
    - metadata:
        name: {{ $volName }}
      spec:
        accessModes:
          - ReadWriteOnce
        {{- with $vals.persistence.storageClassName }}
        storageClassName: {{ . }}
        {{- end }}
        resources:
          requests:
            storage: {{ $vals.persistence.size }}
{{- end }}
{{- end }}
```

**Step 2: Commit**

```bash
git add projects/shared/helm/homelab-library/chart/templates/_statefulset.tpl
git commit -m "feat(shared): add StatefulSet template to library chart"
```

---

### Task 3: Bump library chart version to 0.4.0

**Files:**

- Modify: `projects/shared/helm/homelab-library/chart/Chart.yaml` — version `0.3.0` → `0.4.0`

**Step 1: Bump version**

Change line 5 of `Chart.yaml`:

```yaml
version: 0.4.0
```

**Step 2: Commit**

```bash
git add projects/shared/helm/homelab-library/chart/Chart.yaml
git commit -m "chore(shared): bump library chart version to 0.4.0"
```

---

### Task 4: Migrate grimoire/redis to shared deployment template

**Files:**

- Delete: `projects/grimoire/chart/templates/redis-deployment.yaml`
- Create: `projects/grimoire/chart/templates/redis-deployment.yaml` (replacement using shared template)
- Modify: `projects/grimoire/chart/values.yaml` — restructure redis values

**Step 1: Update grimoire `values.yaml` redis section**

The current redis values need these additions to work with the shared template:

- `containerPort: 6379`
- `portName: redis` (so port is named "redis" not "http")
- `args` list for `--requirepass`
- `env` list for `REDIS_PASSWORD`
- `probes` with `exec` commands
- `podAnnotations` for linkerd disable
- `podSecurityContext` override (redis runs as uid 999)
- `securityContext` override
- `volumeMounts` and `volumes` for redis-data (the shared template provides /tmp already)

Replace the `redis:` section in `values.yaml` (lines 59-77) with:

```yaml
# Redis — ephemeral pub/sub + session state
redis:
  replicas: 1
  containerPort: 6379
  portName: redis
  image:
    repository: redis
    tag: "7-alpine"
    pullPolicy: IfNotPresent
  args:
    - --requirepass
    - $(REDIS_PASSWORD)
  env:
    - name: REDIS_PASSWORD
      valueFrom:
        secretKeyRef:
          name: grimoire
          key: redis_password
  podAnnotations:
    linkerd.io/inject: disabled
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
    readOnlyRootFilesystem: true
  probes:
    liveness:
      exec:
        - redis-cli
        - -a
        - $(REDIS_PASSWORD)
        - ping
      initialDelaySeconds: 5
    readiness:
      exec:
        - redis-cli
        - -a
        - $(REDIS_PASSWORD)
        - ping
      initialDelaySeconds: 5
  volumeMounts:
    - name: redis-data
      mountPath: /data
  volumes:
    - name: redis-data
      emptyDir: {}
  service:
    type: ClusterIP
    port: 6379
    portName: redis
    targetPort: redis
  resources:
    requests:
      cpu: 10m
      memory: 16Mi
    limits:
      cpu: 10m
      memory: 16Mi
```

**Step 2: Replace `redis-deployment.yaml` with shared template call**

Replace the entire file with:

```yaml
{ { - include "homelab.deployment" (dict "context" . "component" "redis") } }
```

**Step 3: Verify with helm template**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml 2>&1 | grep -A 80 "kind: Deployment" | grep -A 80 "redis"
```

Expected: renders a Deployment with exec probes, args, port named "redis", uid 999 security context.

**Step 4: Commit**

```bash
git add projects/grimoire/chart/templates/redis-deployment.yaml projects/grimoire/chart/values.yaml
git commit -m "refactor(grimoire): migrate redis deployment to shared template"
```

---

### Task 5: Migrate grimoire/frontend to shared deployment template

**Files:**

- Modify: `projects/grimoire/chart/templates/frontend-deployment.yaml` (replace with shared template call)
- Modify: `projects/grimoire/chart/values.yaml` — restructure frontend values

**Step 1: Update grimoire `values.yaml` frontend section**

Replace lines 1-17 with:

```yaml
# Frontend — Nginx serving static React build
frontend:
  replicas: 1
  image:
    repository: ghcr.io/jomcgi/homelab/projects/grimoire/frontend
    tag: main
    pullPolicy: Always
  containerPort: 8080
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  securityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
        - ALL
    readOnlyRootFilesystem: true
  probes:
    liveness:
      path: /
      initialDelaySeconds: 5
    readiness:
      path: /
      initialDelaySeconds: 5
  volumeMounts:
    - name: nginx-main-config
      mountPath: /etc/nginx/nginx.conf
      subPath: nginx.conf
      readOnly: true
    - name: nginx-site-config
      mountPath: /etc/nginx/conf.d
      readOnly: true
    - name: nginx-cache
      mountPath: /var/cache/nginx
    - name: nginx-run
      mountPath: /var/run
    - name: nginx-lib
      mountPath: /var/lib/nginx
  volumes:
    - name: nginx-main-config
      configMap:
        name: grimoire-nginx
        items:
          - key: nginx.conf
            path: nginx.conf
    - name: nginx-site-config
      configMap:
        name: grimoire-nginx
        items:
          - key: default.conf
            path: default.conf
    - name: nginx-cache
      emptyDir: {}
    - name: nginx-run
      emptyDir: {}
    - name: nginx-lib
      emptyDir: {}
  service:
    type: ClusterIP
    port: 8080
  resources:
    requests:
      cpu: 5m
      memory: 32Mi
    limits:
      cpu: 5m
      memory: 32Mi
```

Note: The configMap name is hardcoded to `grimoire-nginx` because `{{ include "homelab.fullname" . }}` resolves to `grimoire` when the release name is `grimoire`. This matches the existing nginx-configmap.yaml template which uses `{{ include "grimoire.fullname" . }}-nginx`.

**Step 2: Replace `frontend-deployment.yaml` with shared template call**

The checksum annotation needs to be computed in the template file before calling the shared template (same pattern as ws-gateway-deployment.yaml):

```yaml
{{- $annotations := dict "checksum/nginx-config" (include (print $.Template.BasePath "/nginx-configmap.yaml") . | sha256sum) }}
{{- $_ := set .Values.frontend "podAnnotations" (merge (default dict .Values.frontend.podAnnotations) $annotations) }}
{{- include "homelab.deployment" (dict "context" . "component" "frontend") }}
```

**Step 3: Verify with helm template**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml 2>&1 | grep -A 60 "frontend"
```

Expected: renders with nginx volume mounts, configmap volumes, checksum annotation, readOnlyRootFilesystem.

**Step 4: Commit**

```bash
git add projects/grimoire/chart/templates/frontend-deployment.yaml projects/grimoire/chart/values.yaml
git commit -m "refactor(grimoire): migrate frontend deployment to shared template"
```

---

### Task 6: Bump grimoire chart version and update dependency

**Files:**

- Modify: `projects/grimoire/chart/Chart.yaml` — bump library dependency `0.3.0` → `0.4.0`, bump chart version `0.2.0` → `0.3.0`

**Step 1: Update Chart.yaml**

Change line 5: `version: 0.3.0`
Change line 22: `version: "0.4.0"` (the homelab-library dependency version)

**Step 2: Clean up `_helpers.tpl` aliases no longer needed**

After migration, `grimoire.labels` and `grimoire.selectorLabels` are only referenced by templates that now use the shared library directly. Check if any remaining custom templates still use them:

- `networkpolicy.yaml`, `tunnel.yaml`, `externalsecret.yaml`, `nginx-configmap.yaml` may still reference `grimoire.fullname` or `grimoire.labels`.

Keep the aliases in `_helpers.tpl` for these remaining custom templates.

**Step 3: Commit**

```bash
git add projects/grimoire/chart/Chart.yaml
git commit -m "chore(grimoire): bump chart version to 0.3.0, use library 0.4.0"
```

---

### Task 7: Migrate ships/api to shared StatefulSet template

**Files:**

- Modify: `projects/ships/chart/templates/api-deployment.yaml` (replace with shared template call)
- Modify: `projects/ships/chart/values.yaml` — restructure api probe values

**Step 1: Restructure ships `values.yaml` api probe config**

The current values use flat `api.livenessProbe.*` and `api.readinessProbe.*` keys. The shared template expects `api.probes.liveness.*` and `api.probes.readiness.*`.

Replace lines 153-168 (the livenessProbe/readinessProbe sections) with:

```yaml
# Health probes
probes:
  liveness:
    path: /health
    initialDelaySeconds: 10
    periodSeconds: 15
    timeoutSeconds: 10
    failureThreshold: 6
  readiness:
    path: /ready
    initialDelaySeconds: 10
    periodSeconds: 10
    timeoutSeconds: 10
    failureThreshold: 360
```

Also add `containerPort: 8000` to the api section (currently only set implicitly in the template).

Also move the static env vars into values. The current template hardcodes env vars — these need to move to `values.yaml` under `api.env`:

```yaml
env:
  - name: HOME
    value: /tmp
  - name: UV_CACHE_DIR
    value: /tmp/.uv-cache
```

Note: `NATS_URL`, `CORS_ORIGINS`, and `DB_PATH` were previously interpolated in the template from other values. These need to be set in the deploy-level `values.yaml` or computed in the template file before calling the shared template.

**Step 2: Replace `api-deployment.yaml` with shared template call**

The env vars that reference other values need to be computed before calling the shared template:

```yaml
{{- $env := concat (default list .Values.api.env) (list
  (dict "name" "NATS_URL" "value" (.Values.nats.url | quote))
  (dict "name" "CORS_ORIGINS" "value" (.Values.api.cors.origins | quote))
  (dict "name" "DB_PATH" "value" (printf "%s/ships.db" .Values.api.persistence.mountPath))
) }}
{{- $_ := set .Values.api "env" $env }}
{{- $annotations := dict "config.linkerd.io/opaque-ports" "4222" }}
{{- $_ := set .Values.api "podAnnotations" (merge (default dict .Values.api.podAnnotations) $annotations) }}
{{- include "homelab.statefulset" (dict "context" . "component" "api") }}
```

**Step 3: Verify with helm template**

```bash
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml 2>&1 | grep -A 100 "StatefulSet"
```

Expected: renders a StatefulSet with serviceName, volumeClaimTemplates (20Gi longhorn), correct env vars, and Linkerd annotation.

**Step 4: Clean up `_helpers.tpl`**

Remove the `marine.api.labels` and `marine.api.selectorLabels` aliases — they're no longer referenced after migration.

**Step 5: Commit**

```bash
git add projects/ships/chart/templates/api-deployment.yaml projects/ships/chart/values.yaml projects/ships/chart/templates/_helpers.tpl
git commit -m "refactor(ships): migrate api to shared StatefulSet template"
```

---

### Task 8: Bump ships chart version and update dependency

**Files:**

- Modify: `projects/ships/chart/Chart.yaml` — bump library dependency `0.3.0` → `0.4.0`, bump chart version
- Modify: `projects/ships/deploy/application.yaml` — bump `targetRevision` to match new chart version

**Step 1: Update Chart.yaml**

Bump `version` (line 5) from `0.2.16` to `0.3.0` (minor bump since we changed template structure).
Change `homelab-library` dependency version (line 18) to `"0.4.0"`.

**Step 2: Update application.yaml targetRevision**

Change `targetRevision` (line 12) from `0.2.16` to `0.3.0`.

**Step 3: Commit**

```bash
git add projects/ships/chart/Chart.yaml projects/ships/deploy/application.yaml
git commit -m "chore(ships): bump chart version to 0.3.0, use library 0.4.0"
```

---

### Task 9: Final verification

**Step 1: Render all affected charts**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /tmp/grimoire-rendered.yaml 2>&1
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-rendered.yaml 2>&1
helm template test projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /tmp/stargazer-rendered.yaml 2>&1
```

All three must render without errors. Stargazer (existing consumer) must be unchanged.

**Step 2: Run format**

```bash
format
```

**Step 3: Commit any formatting fixes and push**

```bash
git push -u origin feat/shared-library-enhancements
```

**Step 4: Create PR**

```bash
gh pr create --title "feat(shared): extend library with StatefulSet, exec probes, args" --body "$(cat <<'EOF'
## Summary
- Add `homelab.statefulset` template to shared library chart
- Add exec probe support and custom `args` to deployment + statefulset templates
- Add configurable `portName` (defaults to "http") for non-HTTP services like Redis
- Migrate grimoire/redis and grimoire/frontend to shared deployment template
- Migrate ships/api to shared statefulset template
- Bump library chart 0.3.0 → 0.4.0

## Test plan
- [ ] `helm template` renders all 3 charts (grimoire, ships, stargazer) without errors
- [ ] CI passes (format check + bazel test)
- [ ] After merge, verify ArgoCD syncs grimoire and ships successfully
- [ ] Verify grimoire redis, frontend, and ships api pods are healthy

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
