# Shared Helm Library Enhancements Design

## Goal

Extend `projects/shared/helm/homelab-library/chart/` (v0.3.0 → v0.4.0) with three enhancements to unblock migration of remaining custom deployments in grimoire and ships.

## Changes

### 1. StatefulSet template (`_statefulset.tpl`)

New `homelab.statefulset` template mirroring `homelab.deployment` but rendering a StatefulSet.

**Usage:**

```yaml
{ { - include "homelab.statefulset" (dict "context" . "component" "api") } }
```

**Additional config under `.<component>.persistence`:**

- `size` (required) — PVC storage size (e.g. `20Gi`)
- `storageClassName` (optional) — Kubernetes storage class
- `mountPath` (required) — container mount path for the volume

Adds `serviceName` (set to the component's fullname, required by StatefulSet spec).

Shares all existing deployment features: image config, probes, env, resources, volumes, volumeMounts, podAnnotations, security contexts, imagePullSecrets, nodeSelector/affinity/tolerations.

### 2. Exec probe support

Both `_deployment.tpl` and `_statefulset.tpl` support probe type switching:

- If `probes.liveness.exec` is set (list of command strings) → renders `exec` probe
- Otherwise → renders `httpGet` probe (existing behavior, fully backward compatible)
- Same logic for `readinessProbe`

**Example values for exec probes:**

```yaml
redis:
  probes:
    liveness:
      exec:
        - redis-cli
        - -a
        - $(REDIS_PASSWORD)
        - ping
      initialDelaySeconds: 5
```

### 3. Custom container `args`

Both templates support an optional `args` field:

```yaml
redis:
  args:
    - --requirepass
    - $(REDIS_PASSWORD)
```

Backward compatible — omitting `args` renders no `args:` block.

## What this unblocks

| Service  | Component | Migration path                                                         |
| -------- | --------- | ---------------------------------------------------------------------- |
| ships    | api       | `homelab.statefulset` replaces 200-line dual-mode template             |
| grimoire | redis     | `homelab.deployment` with exec probes + args                           |
| grimoire | frontend  | Already works via existing `podAnnotations` + `volumes`/`volumeMounts` |

## Not included

Configmap checksum annotations — the existing `podAnnotations` passthrough already supports this. Grimoire's frontend can compute `checksum/nginx-config` in its own template and pass it through.

## Version

Library chart bumps from `0.3.0` to `0.4.0`.
