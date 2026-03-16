# Helm Library Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract duplicated Helm templates into a shared library chart, so all service charts share one source of truth for boilerplate.

**Architecture:** A Helm library chart (`type: library`) at `projects/shared/helm/homelab-library/chart/` exports named templates for helpers, ServiceAccount, ImagePullSecret, and ImageUpdater. Consumers import via `file://` relative path and call `{{ include "homelab.*" . }}`.

**Tech Stack:** Helm 3, Helm library charts, file:// dependencies

---

### Task 1: Create the library chart

**Files:**

- Create: `projects/shared/helm/homelab-library/chart/Chart.yaml`
- Create: `projects/shared/helm/homelab-library/chart/templates/_helpers.tpl`
- Create: `projects/shared/helm/homelab-library/chart/templates/_serviceaccount.tpl`
- Create: `projects/shared/helm/homelab-library/chart/templates/_imagepullsecret.tpl`
- Create: `projects/shared/helm/homelab-library/chart/templates/_imageupdater.tpl`

**Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: homelab-library
description: Shared Helm library chart for homelab services
type: library
version: 0.1.0
maintainers:
  - name: homelab
annotations:
  org.opencontainers.image.source: "https://github.com/jomcgi/homelab"
  org.opencontainers.image.licenses: "MPL-2.0"
```

**Step 2: Create `templates/_helpers.tpl`**

```yaml
{{/*
Expand the name of the chart.
*/}}
{{- define "homelab.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "homelab.fullname" -}}
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
{{- define "homelab.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "homelab.labels" -}}
helm.sh/chart: {{ include "homelab.chart" . }}
{{ include "homelab.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.extraLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "homelab.selectorLabels" -}}
app.kubernetes.io/name: {{ include "homelab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "homelab.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "homelab.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Component labels — adds app.kubernetes.io/component to common labels.
Usage: {{ include "homelab.componentLabels" (dict "context" . "component" "api") }}
*/}}
{{- define "homelab.componentLabels" -}}
{{ include "homelab.labels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Component selector labels — adds app.kubernetes.io/component to selector labels.
Usage: {{ include "homelab.componentSelectorLabels" (dict "context" . "component" "api") }}
*/}}
{{- define "homelab.componentSelectorLabels" -}}
{{ include "homelab.selectorLabels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
```

**Step 3: Create `templates/_serviceaccount.tpl`**

```yaml
{{/*
ServiceAccount resource.
Renders a complete ServiceAccount if .Values.serviceAccount.create is true.
Supports optional annotations and automountServiceAccountToken.
*/}}
{{- define "homelab.serviceaccount" -}}
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "homelab.serviceAccountName" . }}
  labels:
    {{- include "homelab.labels" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- if hasKey .Values.serviceAccount "automount" }}
automountServiceAccountToken: {{ .Values.serviceAccount.automount }}
{{- end }}
{{- end }}
{{- end }}
```

**Step 4: Create `templates/_imagepullsecret.tpl`**

```yaml
{{/*
GHCR image pull secret via 1Password Operator.
Renders a OnePasswordItem of type kubernetes.io/dockerconfigjson.
Requires .Values.imagePullSecret.enabled, .create, and .onepassword.itemPath.
*/}}
{{- define "homelab.imagepullsecret" -}}
{{- if and .Values.imagePullSecret.enabled .Values.imagePullSecret.create }}
apiVersion: onepassword.com/v1
kind: OnePasswordItem
type: kubernetes.io/dockerconfigjson
metadata:
  name: ghcr-imagepull-secret
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "homelab.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.imagePullSecret.onepassword.itemPath | quote }}
{{- end }}
{{- end }}
```

**Step 5: Create `templates/_imageupdater.tpl`**

```yaml
{{/*
ArgoCD Image Updater CRD.
Renders an ImageUpdater resource for automatic digest-based image updates.
Requires .Values.imageUpdater.enabled, .images[], and .writeBack config.
*/}}
{{- define "homelab.imageupdater" -}}
{{- if .Values.imageUpdater.enabled }}
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: {{ include "homelab.fullname" . }}
  namespace: argocd
spec:
  applicationRefs:
    - images:
        {{- range .Values.imageUpdater.images }}
        - alias: {{ .alias }}
          commonUpdateSettings:
            updateStrategy: {{ .updateStrategy | default "digest" }}
            forceUpdate: {{ .forceUpdate | default false }}
          imageName: {{ .imageName }}
          manifestTargets:
            helm:
              name: {{ .helm.name }}
              tag: {{ .helm.tag }}
        {{- end }}
      namePattern: {{ include "homelab.fullname" . }}
  namespace: argocd
  writeBackConfig:
    method: {{ .Values.imageUpdater.writeBack.method }}
    gitConfig:
      repository: {{ .Values.imageUpdater.writeBack.repository }}
      branch: {{ .Values.imageUpdater.writeBack.branch }}
      writeBackTarget: {{ .Values.imageUpdater.writeBack.target }}
{{- end }}
{{- end }}
```

**Step 6: Commit**

```bash
git add projects/shared/helm/homelab-library/
git commit -m "feat: add homelab-library shared Helm library chart"
```

---

### Task 2: Migrate grimoire chart

**Files:**

- Modify: `projects/grimoire/chart/Chart.yaml` — add dependency
- Modify: `projects/grimoire/chart/templates/_helpers.tpl` — replace with thin aliases
- Modify: `projects/grimoire/chart/templates/serviceaccount.yaml` — replace with include
- Modify: `projects/grimoire/chart/templates/image-pull-secret.yaml` — replace with include
- Modify: `projects/grimoire/chart/templates/imageupdater.yaml` — replace with include

**Step 1: Capture before snapshot**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /tmp/grimoire-before.yaml 2>&1 || true
```

**Step 2: Add library dependency to Chart.yaml**

Add to `projects/grimoire/chart/Chart.yaml`:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/grimoire/chart/
```

This creates `Chart.lock` and downloads the library into `charts/`.

**Step 4: Replace `_helpers.tpl` with thin aliases**

Replace `projects/grimoire/chart/templates/_helpers.tpl` with:

```yaml
{{- define "grimoire.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "grimoire.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "grimoire.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "grimoire.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "grimoire.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "grimoire.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
```

**Step 5: Replace `serviceaccount.yaml`**

Replace `projects/grimoire/chart/templates/serviceaccount.yaml` with:

```yaml
{ { - include "homelab.serviceaccount" . } }
```

**Step 6: Replace `image-pull-secret.yaml`**

Replace `projects/grimoire/chart/templates/image-pull-secret.yaml` with:

```yaml
{ { - include "homelab.imagepullsecret" . } }
```

**Step 7: Replace `imageupdater.yaml`**

Replace `projects/grimoire/chart/templates/imageupdater.yaml` with:

```yaml
{ { - include "homelab.imageupdater" . } }
```

**Step 8: Verify output is identical**

```bash
helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml > /tmp/grimoire-after.yaml 2>&1 || true
diff /tmp/grimoire-before.yaml /tmp/grimoire-after.yaml
```

Expected: no diff (or only whitespace differences).

**Step 9: Commit**

```bash
git add projects/grimoire/chart/
git commit -m "refactor(grimoire): migrate chart to homelab-library"
```

---

### Task 3: Migrate ships (marine) chart

**Files:**

- Modify: `projects/ships/chart/Chart.yaml` — add dependency
- Modify: `projects/ships/chart/templates/_helpers.tpl` — replace with aliases + component helpers
- Modify: `projects/ships/chart/templates/serviceaccount.yaml` — replace with include
- Modify: `projects/ships/chart/templates/image-pull-secret.yaml` — replace with include

**Step 1: Capture before snapshot**

```bash
helm template ships projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-before.yaml 2>&1 || true
```

**Step 2: Add library dependency to Chart.yaml**

Add to `projects/ships/chart/Chart.yaml`:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/ships/chart/
```

**Step 4: Replace `_helpers.tpl` with aliases + component helpers**

Replace `projects/ships/chart/templates/_helpers.tpl` with:

```yaml
{{- define "marine.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "marine.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "marine.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "marine.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "marine.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "marine.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}

{{/*
Component label aliases — these call the library's component helpers.
*/}}
{{- define "marine.ingest.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "ingest") }}
{{- end }}

{{- define "marine.ingest.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "ingest") }}
{{- end }}

{{- define "marine.api.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "api") }}
{{- end }}

{{- define "marine.api.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "api") }}
{{- end }}

{{- define "marine.frontend.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "frontend") }}
{{- end }}

{{- define "marine.frontend.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "frontend") }}
{{- end }}
```

Note: The component label aliases are kept in the consumer because they're chart-specific names (ingest, api, frontend). The library provides the generic `homelab.componentLabels` helper they delegate to.

**Step 5: Replace `serviceaccount.yaml`**

Replace `projects/ships/chart/templates/serviceaccount.yaml` with:

```yaml
{ { - include "homelab.serviceaccount" . } }
```

**Step 6: Replace `image-pull-secret.yaml`**

Replace `projects/ships/chart/templates/image-pull-secret.yaml` with:

```yaml
{ { - include "homelab.imagepullsecret" . } }
```

**Step 7: Verify output is identical**

```bash
helm template ships projects/ships/chart/ -f projects/ships/deploy/values.yaml > /tmp/ships-after.yaml 2>&1 || true
diff /tmp/ships-before.yaml /tmp/ships-after.yaml
```

Expected: no diff (or only whitespace differences).

**Step 8: Commit**

```bash
git add projects/ships/chart/
git commit -m "refactor(ships): migrate chart to homelab-library"
```

---

### Task 4: Migrate stargazer chart

**Files:**

- Modify: `projects/stargazer/chart/Chart.yaml` — add dependency
- Modify: `projects/stargazer/chart/templates/_helpers.tpl` — replace with thin aliases
- Modify: `projects/stargazer/chart/templates/serviceaccount.yaml` — replace with include
- Modify: `projects/stargazer/chart/templates/image-pull-secret.yaml` — replace with include
- Modify: `projects/stargazer/chart/templates/imageupdater.yaml` — replace with include

**Step 1: Capture before snapshot**

```bash
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /tmp/stargazer-before.yaml 2>&1 || true
```

**Step 2: Add library dependency to Chart.yaml**

Add to `projects/stargazer/chart/Chart.yaml`:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/stargazer/chart/
```

**Step 4: Replace `_helpers.tpl` with thin aliases**

Replace `projects/stargazer/chart/templates/_helpers.tpl` with:

```yaml
{{- define "stargazer.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "stargazer.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "stargazer.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "stargazer.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "stargazer.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "stargazer.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
```

**Step 5: Replace `serviceaccount.yaml`**

Replace `projects/stargazer/chart/templates/serviceaccount.yaml` with:

```yaml
{ { - include "homelab.serviceaccount" . } }
```

**Step 6: Replace `image-pull-secret.yaml`**

Replace `projects/stargazer/chart/templates/image-pull-secret.yaml` with:

```yaml
{ { - include "homelab.imagepullsecret" . } }
```

**Step 7: Replace `imageupdater.yaml`**

Replace `projects/stargazer/chart/templates/imageupdater.yaml` with:

```yaml
{ { - include "homelab.imageupdater" . } }
```

**Step 8: Verify output is identical**

```bash
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml > /tmp/stargazer-after.yaml 2>&1 || true
diff /tmp/stargazer-before.yaml /tmp/stargazer-after.yaml
```

**Step 9: Commit**

```bash
git add projects/stargazer/chart/
git commit -m "refactor(stargazer): migrate chart to homelab-library"
```

---

### Task 5: Migrate trips chart

**Files:**

- Modify: `projects/trips/chart/Chart.yaml` — add dependency
- Modify: `projects/trips/chart/templates/_helpers.tpl` — replace with thin aliases
- Modify: `projects/trips/chart/templates/image-pull-secret.yaml` — replace with include
- Modify: `projects/trips/chart/values.yaml` — add `extraLabels` for `part-of`

**Step 1: Capture before snapshot**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-before.yaml 2>&1 || true
```

**Step 2: Add library dependency to Chart.yaml**

Add to `projects/trips/chart/Chart.yaml`:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/trips/chart/
```

**Step 4: Add `extraLabels` to trips values.yaml**

Add to `projects/trips/chart/values.yaml`:

```yaml
extraLabels:
  app.kubernetes.io/part-of: yukon-tracker
```

This replaces the hardcoded `part-of` label that was in trips' `_helpers.tpl`.

**Step 5: Replace `_helpers.tpl` with thin aliases**

Replace `projects/trips/chart/templates/_helpers.tpl` with:

```yaml
{{- define "trips.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "trips.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "trips.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "trips.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "trips.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
```

Note: trips has no serviceAccount templates, so no alias needed for serviceAccountName.

**Step 6: Replace `image-pull-secret.yaml`**

Replace `projects/trips/chart/templates/image-pull-secret.yaml` with:

```yaml
{ { - include "homelab.imagepullsecret" . } }
```

**Step 7: Verify output is identical**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml > /tmp/trips-after.yaml 2>&1 || true
diff /tmp/trips-before.yaml /tmp/trips-after.yaml
```

Expected: no diff (the `extraLabels` in values.yaml produces the same `part-of` label that was hardcoded before).

**Step 8: Commit**

```bash
git add projects/trips/chart/
git commit -m "refactor(trips): migrate chart to homelab-library"
```

---

### Task 6: Migrate context-forge-gateway chart

**Files:**

- Modify: `projects/mcp/context-forge-gateway/chart/Chart.yaml` — add dependency
- Modify: `projects/mcp/context-forge-gateway/chart/templates/_helpers.tpl` — replace with thin aliases

**Step 1: Capture before snapshot**

```bash
helm dependency update projects/mcp/context-forge-gateway/chart/
helm template context-forge projects/mcp/context-forge-gateway/chart/ -f projects/mcp/context-forge-gateway/deploy/values.yaml > /tmp/cf-before.yaml 2>&1 || true
```

**Step 2: Add library dependency to Chart.yaml**

Add to `projects/mcp/context-forge-gateway/chart/Chart.yaml` dependencies list:

```yaml
- name: homelab-library
  version: "0.1.0"
  repository: "file://../../../shared/helm/homelab-library/chart"
```

Note the deeper relative path (`../../../`) since this chart is under `projects/mcp/context-forge-gateway/`.

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/mcp/context-forge-gateway/chart/
```

**Step 4: Replace `_helpers.tpl` with thin aliases**

Replace `projects/mcp/context-forge-gateway/chart/templates/_helpers.tpl` with:

```yaml
{{- define "context-forge.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "context-forge.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "context-forge.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "context-forge.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "context-forge.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
```

**Step 5: Verify output is identical**

```bash
helm template context-forge projects/mcp/context-forge-gateway/chart/ -f projects/mcp/context-forge-gateway/deploy/values.yaml > /tmp/cf-after.yaml 2>&1 || true
diff /tmp/cf-before.yaml /tmp/cf-after.yaml
```

**Step 6: Commit**

```bash
git add projects/mcp/context-forge-gateway/chart/
git commit -m "refactor(context-forge): migrate chart to homelab-library"
```

---

### Task 7: Migrate mcp-oauth-proxy chart

**Files:**

- Modify: `projects/mcp/oauth-proxy/chart/Chart.yaml` — add dependency
- Modify: `projects/mcp/oauth-proxy/chart/templates/_helpers.tpl` — replace with thin aliases

**Step 1: Capture before snapshot**

```bash
helm template mcp-oauth-proxy projects/mcp/oauth-proxy/chart/ > /tmp/oauth-before.yaml 2>&1 || true
```

**Step 2: Read and add library dependency to Chart.yaml**

Read `projects/mcp/oauth-proxy/chart/Chart.yaml` first, then add:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../../shared/helm/homelab-library/chart"
```

**Step 3: Run helm dependency update**

```bash
helm dependency update projects/mcp/oauth-proxy/chart/
```

**Step 4: Replace `_helpers.tpl` with thin aliases**

Replace `projects/mcp/oauth-proxy/chart/templates/_helpers.tpl` with:

```yaml
{{- define "mcp-oauth-proxy.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "mcp-oauth-proxy.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "mcp-oauth-proxy.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "mcp-oauth-proxy.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "mcp-oauth-proxy.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
```

**Step 5: Verify output is identical**

```bash
helm template mcp-oauth-proxy projects/mcp/oauth-proxy/chart/ > /tmp/oauth-after.yaml 2>&1 || true
diff /tmp/oauth-before.yaml /tmp/oauth-after.yaml
```

**Step 6: Commit**

```bash
git add projects/mcp/oauth-proxy/chart/
git commit -m "refactor(mcp-oauth-proxy): migrate chart to homelab-library"
```

---

### Task 8: Update /add-service skill

**Files:**

- Modify: `.claude/skills/add-service/SKILL.md` — update templates to include library dependency

**Step 1: Update the skill**

Update the `application.yaml` template in the skill — no change needed (it doesn't touch chart internals).

Update the skill's "After Running This Skill" section to note that new charts should depend on `homelab-library`:

Add to the Chart.yaml template guidance:

```yaml
# Chart.yaml should include:
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

And note that `_helpers.tpl` should use thin aliases instead of the full boilerplate.

**Step 2: Commit**

```bash
git add .claude/skills/add-service/SKILL.md
git commit -m "docs(add-service): reference homelab-library in skill templates"
```

---

### Task 9: Run format and push

**Step 1: Run format**

```bash
format
```

This regenerates BUILD files and `projects/home-cluster/kustomization.yaml` if needed.

**Step 2: Commit any format changes**

```bash
git add -A
git commit -m "style: format after helm library migration"
```

(Skip if format produces no changes.)

**Step 3: Push and create PR**

```bash
git push -u origin feat/helm-library
gh pr create --title "feat: add shared homelab-library Helm chart" --body "$(cat <<'EOF'
## Summary
- Extracts duplicated Helm boilerplate into a shared library chart at `projects/shared/helm/homelab-library/chart/`
- Migrates all 6 custom charts (grimoire, ships, stargazer, trips, context-forge, mcp-oauth-proxy) to use the library
- Library provides: `_helpers.tpl` (name, fullname, labels, selectorLabels, serviceAccountName, componentLabels), ServiceAccount, ImagePullSecret (1Password), and ImageUpdater templates
- Each migrated chart verified via `helm template` diff — output is identical before and after

## Test plan
- [ ] `helm template` output diffed for each chart — no regressions
- [ ] CI passes (Bazel test, format check)
- [ ] Verify ArgoCD still syncs affected applications after merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
