# Long-Lived Agents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add support for long-lived Goose agents as Kubernetes Deployments in the `goose-sandboxes` chart, with ConfigMap-based prompt injection and automatic restart on crash. First agent: CI watcher.

**Architecture:** Extends `charts/goose-sandboxes/` with two new templates — a ConfigMap per agent (stores the prompt) and a Deployment per agent (runs Goose with the prompt). Agents are defined in `values.yaml` under an `agents` map. A checksum annotation on the pod template triggers rollouts when prompts change.

**Tech Stack:** Helm, Kubernetes Deployments, ConfigMaps, existing goose-agent container image

**Design doc:** `docs/plans/2026-03-07-long-lived-agents-design.md`

---

### Task 1: Add ConfigMap template for agent prompts

**Files:**
- Create: `charts/goose-sandboxes/templates/configmap-agents.yaml`

**Step 1: Create the ConfigMap template**

```yaml
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-prompt-{{ $name }}
  namespace: {{ $.Release.Namespace }}
  labels:
    app.kubernetes.io/name: agent-{{ $name }}
    app.kubernetes.io/component: agent
    app.kubernetes.io/managed-by: {{ $.Release.Service }}
data:
  prompt: |
    {{- $agent.prompt | nindent 4 }}
---
{{- end }}
{{- end }}
```

**Step 2: Validate with helm lint**

Run: `helm lint charts/goose-sandboxes/`
Expected: PASS (no errors)

**Step 3: Render and verify ConfigMap output**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ | grep -A 20 'kind: ConfigMap'`
Expected: Should show `agent-prompt-ci-watcher` ConfigMap with the prompt text (once values are added in Task 3).

**Step 4: Commit**

```bash
git add charts/goose-sandboxes/templates/configmap-agents.yaml
git commit -m "feat(goose-sandboxes): add ConfigMap template for agent prompts"
```

---

### Task 2: Add Deployment template for long-lived agents

**Files:**
- Create: `charts/goose-sandboxes/templates/deployment-agents.yaml`

**Step 1: Create the Deployment template**

```yaml
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-{{ $name }}
  namespace: {{ $.Release.Namespace }}
  labels:
    app.kubernetes.io/name: agent-{{ $name }}
    app.kubernetes.io/component: agent
    app.kubernetes.io/managed-by: {{ $.Release.Service }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: agent-{{ $name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: agent-{{ $name }}
        app.kubernetes.io/component: agent
      annotations:
        checksum/prompt: {{ include (print $.Template.BasePath "/configmap-agents.yaml") $ | sha256sum }}
        linkerd.io/inject: disabled
    spec:
      serviceAccountName: goose-agent
      securityContext:
        runAsNonRoot: true
        fsGroup: 65532
        seccompProfile:
          type: RuntimeDefault
      initContainers:
        - name: clone-repo
          image: "{{ $.Values.sandboxTemplate.image.repository }}:{{ $.Values.sandboxTemplate.image.tag }}"
          command: ["/bin/sh", "-c"]
          args:
            - |
              git clone --depth 1 https://x-access-token:${GITHUB_TOKEN}@github.com/{{ $.Values.sandboxTemplate.env.repoOwner }}/{{ $.Values.sandboxTemplate.env.repoName }}.git /workspace/{{ $.Values.sandboxTemplate.env.repoName }}
          securityContext:
            runAsUser: 65532
            runAsGroup: 65532
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
          env:
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: agent-secrets
                  key: GITHUB_TOKEN
          volumeMounts:
            - name: workspace
              mountPath: /workspace
      containers:
        - name: goose
          image: "{{ $.Values.sandboxTemplate.image.repository }}:{{ $.Values.sandboxTemplate.image.tag }}"
          command: ["goose", "run", "--text", "$(AGENT_PROMPT)"]
          workingDir: /workspace/{{ $.Values.sandboxTemplate.env.repoName }}
          securityContext:
            runAsUser: 65532
            runAsGroup: 65532
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false
            capabilities:
              drop: [ALL]
          env:
            - name: AGENT_PROMPT
              valueFrom:
                configMapKeyRef:
                  name: agent-prompt-{{ $name }}
                  key: prompt
            - name: GOOSE_PROVIDER
              value: {{ $.Values.sandboxTemplate.env.gooseProvider }}
            - name: GOOSE_MODEL
              value: {{ $.Values.sandboxTemplate.env.gooseModel }}
            - name: CLAUDE_CODE_OAUTH_TOKEN
              valueFrom:
                secretKeyRef:
                  name: claude-auth
                  key: CLAUDE_AUTH_TOKEN
            - name: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
              value: "1"
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: agent-secrets
                  key: GITHUB_TOKEN
            - name: BUILDBUDDY_API_KEY
              valueFrom:
                secretKeyRef:
                  name: agent-secrets
                  key: BUILDBUDDY_API_KEY
          resources:
            {{- toYaml ($agent.resources | default $.Values.sandboxTemplate.resources) | nindent 12 }}
          volumeMounts:
            - name: workspace
              mountPath: /workspace
      volumes:
        - name: workspace
          emptyDir: {}
---
{{- end }}
{{- end }}
```

**Step 2: Validate with helm lint**

Run: `helm lint charts/goose-sandboxes/`
Expected: PASS

**Step 3: Commit**

```bash
git add charts/goose-sandboxes/templates/deployment-agents.yaml
git commit -m "feat(goose-sandboxes): add Deployment template for long-lived agents"
```

---

### Task 3: Add CI watcher agent to values.yaml

**Files:**
- Modify: `charts/goose-sandboxes/values.yaml` — append `agents` section

**Step 1: Add the agents section to values.yaml**

Append the following to the end of `charts/goose-sandboxes/values.yaml`:

```yaml
# Long-lived agents — each entry generates a ConfigMap + Deployment.
# Prompt changes trigger pod restart via checksum annotation.
agents:
  ci-watcher:
    enabled: false
    prompt: |
      You are a CI watcher agent for the jomcgi/homelab GitHub repository.

      Your job is to continuously monitor open pull requests for CI failures
      and fix them. Loop forever:

      1. List open PRs: gh pr list --state open --json number,title,statusCheckRollup
      2. For each PR with failing checks:
         a. Check out the PR branch
         b. Read the CI failure logs (use BuildBuddy MCP tools)
         c. Diagnose and fix the issue
         d. Commit and push the fix
         e. Wait for CI to re-run and verify it passes
      3. Sleep 60 seconds, then repeat from step 1

      Important:
      - Never force-push or rewrite history
      - Create fixup commits, not amends
      - If you can't fix a failure after 2 attempts, skip it and move on
      - Use conventional commit messages: fix(scope): description
    resources:
      requests:
        cpu: "1"
        memory: 2Gi
      limits:
        cpu: "4"
        memory: 8Gi
```

Note: `enabled: false` in the base chart — the prod overlay enables it.

**Step 2: Validate with helm lint**

Run: `helm lint charts/goose-sandboxes/`
Expected: PASS

**Step 3: Render and verify full output**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ --set agents.ci-watcher.enabled=true | grep -E 'kind:|name: agent-'`
Expected: Should show `ConfigMap` named `agent-prompt-ci-watcher` and `Deployment` named `agent-ci-watcher`.

**Step 4: Verify prompt checksum annotation is present**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ --set agents.ci-watcher.enabled=true | grep 'checksum/prompt'`
Expected: Should show a sha256sum annotation.

**Step 5: Commit**

```bash
git add charts/goose-sandboxes/values.yaml
git commit -m "feat(goose-sandboxes): add ci-watcher agent definition to values"
```

---

### Task 4: Enable CI watcher in prod overlay

**Files:**
- Modify: `overlays/prod/goose-sandboxes/values.yaml` — add agent enablement

**Step 1: Add agent enablement to prod overlay**

Append to `overlays/prod/goose-sandboxes/values.yaml`:

```yaml
agents:
  ci-watcher:
    enabled: true
```

**Step 2: Render with prod overlay to verify**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ -f overlays/prod/goose-sandboxes/values.yaml --set agents.ci-watcher.enabled=true | grep -E 'kind:|name: agent-'`
Expected: ConfigMap and Deployment for ci-watcher visible in output.

**Step 3: Commit**

```bash
git add overlays/prod/goose-sandboxes/values.yaml
git commit -m "feat(goose-sandboxes): enable ci-watcher agent in prod"
```

---

### Task 5: Full render validation and lint

**Step 1: Lint the chart**

Run: `helm lint charts/goose-sandboxes/`
Expected: PASS

**Step 2: Full render with prod overlay**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ -f overlays/prod/goose-sandboxes/values.yaml > /tmp/rendered.yaml && echo "OK"`
Expected: OK — no template errors.

**Step 3: Verify all expected resources in rendered output**

Run: `grep 'kind:' /tmp/rendered.yaml | sort | uniq -c`
Expected: Should include ConfigMap, Deployment, LimitRange, OnePasswordItem, ResourceQuota, SandboxTemplate, SandboxWarmPool, ServiceAccount.

**Step 4: Verify disabled agents produce no output**

Run: `helm template goose-sandboxes charts/goose-sandboxes/ | grep 'agent-ci-watcher' | wc -l`
Expected: 0 (base values have `enabled: false`).

**Step 5: Run format check**

Run: `format`
Expected: No changes needed — templates are already formatted.

**Step 6: Commit if any formatting changes**

```bash
git add -A
git commit -m "style(goose-sandboxes): format templates"
```

---

### Task 6: Push and create PR

**Step 1: Push branch**

```bash
git push -u origin feat/long-lived-agents
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "feat(goose-sandboxes): add long-lived agent Deployments" \
  --body "$(cat <<'EOF'
## Summary
- Adds ConfigMap + Deployment templates to `charts/goose-sandboxes/` for long-lived agents
- Agents are defined in `values.yaml` under an `agents` map — each entry generates a ConfigMap (prompt) and Deployment (Goose runner)
- Checksum annotation on pod template triggers rollout when prompts change
- First agent: CI watcher that monitors open PRs for CI failures and fixes them
- `enabled: false` in base values, enabled in prod overlay

## Design
See `docs/plans/2026-03-07-long-lived-agents-design.md`

## Test plan
- [ ] `helm lint charts/goose-sandboxes/` passes
- [ ] `helm template` with `enabled: true` renders ConfigMap + Deployment
- [ ] `helm template` with `enabled: false` (default) renders no agent resources
- [ ] Checksum annotation present on pod template
- [ ] CI passes (BuildBuddy format check + test)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Enable auto-merge**

```bash
gh pr merge --auto --rebase
```
