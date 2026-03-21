# Shared Service Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `homelab.service` library template and migrate all multi-component service charts to use it, eliminating 8 hand-written Service templates.

**Architecture:** New `_service.tpl` in homelab-library follows the same dict API as `_deployment.tpl`. Each service chart replaces its Service YAML with a one-liner `include`. Values-driven port config ensures consistency.

**Tech Stack:** Helm library chart templates (Go templates), values.yaml conventions

---

### Task 1: Write the shared `_service.tpl` template

**Files:**

- Create: `projects/shared/helm/homelab-library/chart/templates/_service.tpl`
- Modify: `projects/shared/helm/homelab-library/chart/Chart.yaml:5` (version 0.2.0 → 0.3.0)

**Step 1: Create `_service.tpl`**

```gotemplate
{{/*
Service resource.
Renders a complete Service for a named component.
All config is read from .Values.<component>.service by convention.

Usage:
  {{- include "homelab.service" (dict "context" . "component" "api") }}
  {{- include "homelab.service" (dict "context" . "component" "wsGateway" "componentName" "ws-gateway") }}

Required values under .<component>.service:
  port (int)

Optional values (with defaults):
  type (ClusterIP), portName ("http"), targetPort (portName value)

Multi-port alternative — set .service.ports list instead of port/portName/targetPort:
  ports: [{port: 6379, name: redis, targetPort: redis}, ...]
*/}}
{{- define "homelab.service" -}}
{{- $ctx := .context -}}
{{- $component := .component -}}
{{- $name := default $component .componentName -}}
{{- $vals := index $ctx.Values $component -}}
{{- $svc := $vals.service -}}
{{- if (default true $vals.enabled) }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "homelab.fullname" $ctx }}-{{ $name }}
  labels:
    {{- include "homelab.componentLabels" (dict "context" $ctx "component" $name) | nindent 4 }}
spec:
  type: {{ $svc.type | default "ClusterIP" }}
  ports:
    {{- if $svc.ports }}
    {{- range $svc.ports }}
    - port: {{ .port }}
      targetPort: {{ .targetPort | default .name }}
      protocol: TCP
      name: {{ .name }}
    {{- end }}
    {{- else }}
    {{- $portName := $svc.portName | default "http" }}
    - port: {{ $svc.port }}
      targetPort: {{ $svc.targetPort | default $portName }}
      protocol: TCP
      name: {{ $portName }}
    {{- end }}
  selector:
    {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $name) | nindent 4 }}
{{- end }}
{{- end }}
```

**Step 2: Bump library version**

In `projects/shared/helm/homelab-library/chart/Chart.yaml`, change line 5:

```yaml
version: 0.3.0
```

**Step 3: Validate template renders in isolation**

```bash
cd /tmp/claude-worktrees/shared-service-template
helm template test projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml --show-only templates/service-api.yaml 2>&1 | head -5
```

This won't work yet (stargazer still has its own template), but confirms the library chart itself is valid.

**Step 4: Commit**

```bash
git add projects/shared/helm/homelab-library/chart/templates/_service.tpl projects/shared/helm/homelab-library/chart/Chart.yaml
git commit -m "feat(homelab-library): add shared service template"
```

---

### Task 2: Update helm dependency versions in all consuming charts

Every chart that depends on `homelab-library` needs its `Chart.yaml` dependency bumped from `0.2.0` to `0.3.0`, and `Chart.lock` / `.tgz` files regenerated.

**Files:**

- Modify: `projects/grimoire/chart/Chart.yaml` (dependency version)
- Modify: `projects/stargazer/chart/Chart.yaml` (dependency version)
- Modify: `projects/ships/chart/Chart.yaml` (dependency version)
- Modify: `projects/trips/chart/Chart.yaml` (dependency version)
- Modify: `projects/agent_platform/chart/orchestrator/Chart.yaml` (dependency version)
- Modify: `projects/agent_platform/chart/mcp-servers/Chart.yaml` (dependency version)
- Modify: `projects/mcp/context-forge-gateway/chart/Chart.yaml` (dependency version)
- Modify: `projects/mcp/oauth-proxy/chart/Chart.yaml` (dependency version)

**Step 1: Update dependency version in all Chart.yaml files**

In each file above, change the homelab-library dependency version:

```yaml
dependencies:
  - name: homelab-library
    version: "0.3.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

Note: The `repository` path varies by chart depth — `../../shared/...` vs `../../../shared/...` vs `../../../../shared/...`. Preserve the existing path; only change the version string.

**Step 2: Regenerate lock files and tarballs**

```bash
cd /tmp/claude-worktrees/shared-service-template
format
```

The `format` command runs `sync-helm-deps.sh` which calls `helm dependency update` on each chart, regenerating `Chart.lock` and the `.tgz` files in `charts/`.

**Step 3: Verify lock files updated**

```bash
git diff --name-only | grep -E 'Chart\.(lock|yaml)'
```

Should show all the Chart.yaml and Chart.lock files updated.

**Step 4: Commit**

```bash
git add -A projects/*/chart/Chart.yaml projects/*/chart/Chart.lock projects/*/chart/charts/ \
        projects/agent_platform/chart/*/Chart.yaml projects/agent_platform/chart/*/Chart.lock projects/agent_platform/chart/*/charts/ \
        projects/mcp/*/chart/Chart.yaml projects/mcp/*/chart/Chart.lock projects/mcp/*/chart/charts/
git commit -m "build(deps): bump homelab-library to 0.3.0"
```

---

### Task 3: Migrate stargazer (simplest — 1 service, already parametrized)

**Files:**

- Modify: `projects/stargazer/chart/templates/service-api.yaml`
- Modify: `projects/stargazer/chart/Chart.yaml:3` (version bump)

**Step 1: Capture before-state**

```bash
cd /tmp/claude-worktrees/shared-service-template
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml --show-only templates/service-api.yaml > /tmp/stargazer-service-before.yaml
```

**Step 2: Replace template content**

Replace the entire content of `projects/stargazer/chart/templates/service-api.yaml` with:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "api") }}
```

**Step 3: Bump chart version**

In `projects/stargazer/chart/Chart.yaml`, bump version (e.g. `0.1.0` → `0.2.0`).

**Step 4: Validate rendered output matches**

```bash
helm template stargazer projects/stargazer/chart/ -f projects/stargazer/deploy/values.yaml --show-only templates/service-api.yaml > /tmp/stargazer-service-after.yaml
diff /tmp/stargazer-service-before.yaml /tmp/stargazer-service-after.yaml
```

Expected: identical or cosmetic whitespace only. Key things to verify: labels include `app.kubernetes.io/component: api`, selector includes component label, port/targetPort match.

**Step 5: Commit**

```bash
git add projects/stargazer/chart/
git commit -m "refactor(stargazer): migrate service to shared template"
```

---

### Task 4: Migrate ships (3 services, already parametrized)

**Files:**

- Modify: `projects/ships/chart/templates/api-service.yaml`
- Modify: `projects/ships/chart/templates/frontend-service.yaml`
- Modify: `projects/ships/chart/templates/ingest-service.yaml`
- Modify: `projects/ships/chart/Chart.yaml:4` (version bump 0.2.15 → 0.2.16)
- Modify: `projects/ships/deploy/application.yaml` (targetRevision 0.2.15 → 0.2.16)

**Step 1: Capture before-state for all 3 services**

```bash
cd /tmp/claude-worktrees/shared-service-template
for tpl in api-service frontend-service ingest-service; do
  helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml --show-only "templates/${tpl}.yaml" > "/tmp/ships-${tpl}-before.yaml"
done
```

**Step 2: Replace each template**

`projects/ships/chart/templates/api-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "api") }}
```

`projects/ships/chart/templates/frontend-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "frontend") }}
```

`projects/ships/chart/templates/ingest-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "ingest") }}
```

**Step 3: Bump chart version and targetRevision**

- `projects/ships/chart/Chart.yaml`: version `0.2.15` → `0.2.16`
- `projects/ships/deploy/application.yaml`: targetRevision `0.2.15` → `0.2.16`

**Step 4: Validate**

```bash
for tpl in api-service frontend-service ingest-service; do
  helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml --show-only "templates/${tpl}.yaml" > "/tmp/ships-${tpl}-after.yaml"
  echo "=== ${tpl} ==="
  diff "/tmp/ships-${tpl}-before.yaml" "/tmp/ships-${tpl}-after.yaml"
done
```

Expected: identical or cosmetic-only diffs.

**Step 5: Commit**

```bash
git add projects/ships/chart/ projects/ships/deploy/application.yaml
git commit -m "refactor(ships): migrate services to shared template"
```

---

### Task 5: Migrate grimoire (3 services, redis needs portName override)

**Files:**

- Modify: `projects/grimoire/chart/templates/frontend-service.yaml`
- Modify: `projects/grimoire/chart/templates/ws-gateway-service.yaml`
- Modify: `projects/grimoire/chart/templates/redis-service.yaml`
- Modify: `projects/grimoire/chart/values.yaml` (add redis portName/targetPort)
- Modify: `projects/grimoire/chart/Chart.yaml` (version bump)

**Step 1: Capture before-state**

```bash
cd /tmp/claude-worktrees/shared-service-template
for tpl in frontend-service ws-gateway-service redis-service; do
  helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml --show-only "templates/${tpl}.yaml" > "/tmp/grimoire-${tpl}-before.yaml"
done
```

**Step 2: Add portName/targetPort to redis values**

In `projects/grimoire/chart/values.yaml`, under `redis.service`, add:

```yaml
redis:
  service:
    type: ClusterIP
    port: 6379
    portName: redis
    targetPort: redis
```

**Step 3: Replace each template**

`projects/grimoire/chart/templates/frontend-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "frontend") }}
```

`projects/grimoire/chart/templates/ws-gateway-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "wsGateway" "componentName" "ws-gateway") }}
```

`projects/grimoire/chart/templates/redis-service.yaml`:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "redis") }}
```

**Step 4: Bump chart version**

`projects/grimoire/chart/Chart.yaml`: bump version (e.g. `0.1.0` → `0.2.0`).

No application.yaml change needed — grimoire uses `targetRevision: HEAD`.

**Step 5: Validate**

```bash
for tpl in frontend-service ws-gateway-service redis-service; do
  helm template grimoire projects/grimoire/chart/ -f projects/grimoire/deploy/values.yaml --show-only "templates/${tpl}.yaml" > "/tmp/grimoire-${tpl}-after.yaml"
  echo "=== ${tpl} ==="
  diff "/tmp/grimoire-${tpl}-before.yaml" "/tmp/grimoire-${tpl}-after.yaml"
done
```

Expected diffs:

- **frontend/ws-gateway**: should be identical (labels now use `homelab.componentLabels` instead of manual `grimoire.labels` + explicit component — output is the same)
- **redis**: should be identical (portName/targetPort now from values)

**Step 6: Commit**

```bash
git add projects/grimoire/chart/
git commit -m "refactor(grimoire): migrate services to shared template"
```

---

### Task 6: Migrate trips (3 services, needs service.port in values)

**Files:**

- Modify: `projects/trips/chart/templates/services.yaml`
- Modify: `projects/trips/chart/values.yaml` (add service.port/type to each component)
- Modify: `projects/trips/chart/Chart.yaml` (version bump)

**Step 1: Capture before-state**

```bash
cd /tmp/claude-worktrees/shared-service-template
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml --show-only templates/services.yaml > /tmp/trips-services-before.yaml
```

**Step 2: Add service config to chart values**

In `projects/trips/chart/values.yaml`, add `service` block under each component:

```yaml
api:
  service:
    type: ClusterIP
    port: 8000

nginx:
  service:
    type: ClusterIP
    port: 80

imgproxy:
  service:
    type: ClusterIP
    port: 8080
```

**Step 3: Replace template**

Replace the entire content of `projects/trips/chart/templates/services.yaml` with:

```gotemplate
{{- include "homelab.service" (dict "context" . "component" "imgproxy") }}
---
{{- include "homelab.service" (dict "context" . "component" "nginx") }}
---
{{- include "homelab.service" (dict "context" . "component" "api") }}
```

**Step 4: Bump chart version**

`projects/trips/chart/Chart.yaml`: bump version (e.g. `1.0.0` → `1.1.0`).

No application.yaml change — trips uses `targetRevision: HEAD`.

**Step 5: Validate**

```bash
helm template trips projects/trips/chart/ -f projects/trips/deploy/values.yaml --show-only templates/services.yaml > /tmp/trips-services-after.yaml
diff /tmp/trips-services-before.yaml /tmp/trips-services-after.yaml
```

Expected: identical or cosmetic-only. Key check: trips previously hardcoded port numbers (8000, 80, 8080) — the new template reads from values, so the output must match.

**Step 6: Commit**

```bash
git add projects/trips/chart/
git commit -m "refactor(trips): migrate services to shared template"
```

---

### Task 7: Final validation and format

**Step 1: Run format**

```bash
cd /tmp/claude-worktrees/shared-service-template
format
```

**Step 2: Full helm template render for all migrated charts**

```bash
for chart in stargazer grimoire trips; do
  echo "=== ${chart} ==="
  helm template ${chart} projects/${chart}/chart/ -f projects/${chart}/deploy/values.yaml > /dev/null && echo "OK" || echo "FAIL"
done
echo "=== marine ==="
helm template marine projects/ships/chart/ -f projects/ships/deploy/values.yaml > /dev/null && echo "OK" || echo "FAIL"
```

All should print OK.

**Step 3: Commit any format changes**

```bash
git add -A && git diff --cached --stat
# If changes exist:
git commit -m "style: format"
```

---

### Task 8: Push and create PR

**Step 1: Push branch**

```bash
git push -u origin feat/shared-service-template
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: add shared service template to homelab-library" --body "$(cat <<'EOF'
## Summary
- Adds `homelab.service` template to the shared Helm library, mirroring the existing `homelab.deployment` API
- Migrates 8 hand-written Service templates across 4 charts (stargazer, ships, grimoire, trips) to one-liner includes
- Bumps homelab-library from 0.2.0 to 0.3.0

## Test plan
- [ ] `helm template` renders identical output for all migrated charts (validated locally)
- [ ] CI passes (format check + bazel test)
- [ ] ArgoCD syncs cleanly after merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
