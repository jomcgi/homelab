# Shared Deployment Template for homelab-library

**Date:** 2026-03-20
**Status:** Approved

## Problem

10 deployment templates across 4 charts (ships, grimoire, stargazer, trips) share ~80% identical structure. Each hand-writes the same metadata, selector, pod spec, security context, probes, and scheduling blocks. Changes to conventions (e.g. security context defaults) require updating every template individually.

## Decision

Add a `homelab.deployment` template to the shared `homelab-library` chart that renders a complete Deployment from a standardized values structure.

### Scope

**In scope (standard deployments):** trips/api, trips/nginx, trips/imgproxy, ships/frontend, ships/ingest, stargazer/api, grimoire/ws-gateway — 7 deployments.

**Out of scope (for now):** ships/api (StatefulSet with persistence toggle), grimoire/redis (exec probes, uid 999), grimoire/frontend (6 nginx volume mounts, configmap checksum).

## Design

### Calling convention

Each chart's deployment file becomes a one-liner:

```yaml
{ { - include "homelab.deployment" (dict "context" . "component" "api") } }
```

The template reads all config from `.Values.<component>`.

### Naming and labels

Uses `homelab.*` helpers directly with component variants:

- Name: `{{ homelab.fullname }}-{{ component }}`
- Labels: `homelab.componentLabels` (includes `app.kubernetes.io/component`)
- Selectors: `homelab.componentSelectorLabels`

This eliminates the need for per-chart component wrapper defines in `_helpers.tpl`.

### Values schema

Each component follows this structure under `.Values.<component>`:

```yaml
api:
  enabled: true # optional, defaults true
  replicas: 1 # optional, defaults 1
  image:
    repository: ghcr.io/jomcgi/homelab/trips-api
    tag: latest
    pullPolicy: IfNotPresent
  containerPort: 8000 # optional, defaults 8080
  probes: # optional block
    liveness:
      path: /health # defaults /health
      initialDelaySeconds: 10 # defaults 10
      periodSeconds: 10 # defaults 10
      timeoutSeconds: 1 # defaults 1
      failureThreshold: 3 # defaults 3
    readiness:
      path: /health # defaults /health
      initialDelaySeconds: 5 # defaults 5
      periodSeconds: 5 # defaults 5
      timeoutSeconds: 1 # defaults 1
      failureThreshold: 3 # defaults 3
  env: [] # optional, list of env var objects
  resources: {} # optional
  volumes: [] # optional, extra volumes
  volumeMounts: [] # optional, extra volume mounts
  podAnnotations: {} # optional
  podSecurityContext: {} # optional, overrides global
  securityContext: {} # optional, overrides global
```

### Template behavior

1. **Conditional rendering** — skipped if `<component>.enabled` is false
2. **Metadata** — name `{{ fullname }}-{{ component }}`, component labels
3. **Image pull secrets** — from global `imagePullSecret.enabled` pattern
4. **Service account** — via `homelab.serviceAccountName`
5. **Pod security context** — component-level falls back to global `.Values.podSecurityContext`
6. **Container security context** — component-level falls back to global `.Values.securityContext`
7. **tmp volume** — always mounted at `/tmp` (emptyDir), merged with extra volumes/mounts
8. **HTTP probes** — liveness and readiness with configurable paths and timing, sensible defaults
9. **Scheduling** — nodeSelector, affinity, tolerations from global `.Values`

### Migration path

For each standard deployment:

1. Restructure the component's values to match the schema (move env vars, volumes, annotations into values)
2. Replace the deployment template file contents with the one-liner `include`
3. Remove unused component wrapper defines from `_helpers.tpl`
4. Verify with `helm template` that output matches before/after

### Out of scope (future work)

- StatefulSet support (ships/api with persistence toggle)
- Exec probes (grimoire/redis)
- Multi-container pods / init containers
- Shared service template (`homelab.service`)
