# Long-Lived Agent Deployment Design

**Author:** Joe McGinley
**Created:** 2026-03-07
**Status:** Approved

---

## Problem

The current agent-sandbox architecture (`SandboxClaim` → warm pool → `goose run` → pod cleanup) is designed for one-shot tasks. Some agent use cases require long-lived, continuously running agents — for example, a CI watcher that monitors open PRs for failures and fixes them autonomously.

Claude Code handles long-running sessions via automatic context compression, making multi-hour/multi-day agent loops viable. The missing piece is Kubernetes lifecycle management: auto-restart on crash, prompt-driven configuration, and GitOps integration.

## Design Decisions

- **Deployment, not SandboxClaim** — Deployments provide `restartPolicy: Always` natively. SandboxClaims are designed for one-shot tasks with `shutdownPolicy: Delete`.
- **Same namespace** — Long-lived agents share the `goose-sandboxes` namespace, reusing existing secrets (claude-auth, agent-secrets), service account, LimitRange, and ResourceQuota.
- **ConfigMap-based prompts** — The agent prompt is stored in a ConfigMap and injected via environment variable. This decouples the agent's behaviour from the container image — same image, different ConfigMap = different agent.
- **Checksum annotation** — A `sha256sum` of the ConfigMap is added as a pod annotation so prompt changes trigger a rolling restart.
- **Stateless restart** — On crash/restart, the agent re-clones the repo and re-scans GitHub for open PRs. No persistent state needed.
- **Extend existing chart** — New templates are added to `charts/goose-sandboxes/` rather than creating a separate chart. Agents are defined in `values.yaml` under an `agents` map.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  goose-sandboxes namespace                           │
│                                                      │
│  ┌──────────────────┐   ┌─────────────────────────┐ │
│  │ SandboxWarmPool   │   │ Deployment: ci-watcher  │ │
│  │ (on-demand tasks) │   │                         │ │
│  │                   │   │ ConfigMap: prompt        │ │
│  │ agent-run CLI     │   │ restartPolicy: Always   │ │
│  │ creates claims    │   │ checksum/prompt anno     │ │
│  └──────────────────┘   └─────────────────────────┘ │
│                                                      │
│  Shared: claude-auth, agent-secrets, goose-agent SA, │
│          LimitRange, ResourceQuota, Context Forge    │
└─────────────────────────────────────────────────────┘
```

## Chart Changes

### New templates

**`templates/configmap-agents.yaml`** — One ConfigMap per enabled agent:

```yaml
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-prompt-{{ $name }}
  namespace: {{ $.Release.Namespace }}
data:
  prompt: {{ $agent.prompt | quote }}
---
{{- end }}
{{- end }}
```

**`templates/deployment-agents.yaml`** — One Deployment per enabled agent:

```yaml
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-{{ $name }}
  namespace: {{ $.Release.Namespace }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: agent-{{ $name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: agent-{{ $name }}
      annotations:
        checksum/prompt: {{ include (print $.Template.BasePath "/configmap-agents.yaml") $ | sha256sum }}
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

### Values changes

```yaml
# New section in values.yaml
agents:
  ci-watcher:
    enabled: true
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

### Adding future agents

Adding a new long-lived agent requires only a new key under `agents`:

```yaml
agents:
  ci-watcher:
    enabled: true
    prompt: |
      ...
  dependency-updater: # Future example
    enabled: false
    prompt: |
      ...
```

## Resource Impact

The CI watcher permanently consumes 1 pod (1 CPU request, 2Gi memory) from the namespace quota:

| Resource | Quota | Used (warm pool) | Used (CI watcher) | Remaining |
| -------- | ----- | ---------------- | ----------------- | --------- |
| Pods     | 5     | 1                | 1                 | 3         |
| CPU req  | 8     | 1                | 1                 | 6         |
| Memory   | 16Gi  | 2Gi              | 2Gi               | 12Gi      |

## Recovery Behaviour

1. Goose process exits (crash, error, context exhaustion)
2. Container exits → Kubernetes restarts the container (same pod, `restartPolicy: Always`)
3. If the pod itself is evicted/rescheduled, init container re-clones the repo
4. Goose starts fresh with the prompt, re-scans all open PRs
5. GitHub is the source of truth — no state is lost

## What This Does Not Cover

- **Observability** — OTel traces from long-lived agents to SigNoz (future work)
- **Alerting** — Alerting on agent crash loops or prolonged inactivity (future work)
- **Multiple replicas** — Each agent runs as a single replica; no leader election or work partitioning
