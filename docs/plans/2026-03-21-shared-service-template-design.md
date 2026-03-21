# Shared Service Template Design

## Goal

Add a `homelab.service` template to the shared Helm library (`homelab-library`) that eliminates boilerplate Service definitions across all services, enforcing consistent labels, selectors, and structure.

## Template API

Mirrors the existing `homelab.deployment` contract:

```yaml
{{- include "homelab.service" (dict "context" . "component" "api") }}
{{- include "homelab.service" (dict "context" . "component" "wsGateway" "componentName" "ws-gateway") }}
```

### Dict keys

| Key             | Required | Description                                                        |
| --------------- | -------- | ------------------------------------------------------------------ |
| `context`       | yes      | Root Helm context (`.`)                                            |
| `component`     | yes      | Key into `.Values` (e.g. `"api"`, `"redis"`)                       |
| `componentName` | no       | Override for metadata/labels when values key differs from K8s name |

### Values convention

Read from `.Values.<component>.service`:

```yaml
redis:
  enabled: true # default: true
  service:
    type: ClusterIP # default: ClusterIP
    port: 6379 # required — the service port
    portName: redis # default: "http"
    targetPort: redis # default: portName value
    # Multi-port alternative (overrides port/portName/targetPort):
    # ports:
    #   - port: 6379
    #     name: redis
    #     targetPort: redis
    #   - port: 9090
    #     name: metrics
```

### Rendered output

- `enabled` guard wraps the whole resource
- `metadata.labels` via `homelab.componentLabels`
- `spec.selector` via `homelab.componentSelectorLabels` — matches Deployment pod labels
- Single-port shorthand covers 8/9 existing services; `ports` list for multi-port

## Migration scope

9 hand-written Service templates across 5 services replaced with one-liner includes:

| Service         | Files replaced               | Values changes needed                                         |
| --------------- | ---------------------------- | ------------------------------------------------------------- |
| trips           | `services.yaml` (3 services) | Add `service.port` to api (8000), nginx (80), imgproxy (8080) |
| ships           | 3 `*-service.yaml` files     | None — already parametrized                                   |
| grimoire        | 3 `*-service.yaml` files     | Add `portName: redis`, `targetPort: redis` to redis.service   |
| stargazer       | `service-api.yaml`           | None                                                          |
| mcp/oauth-proxy | `service.yaml`               | None                                                          |

## Version bumps

- `homelab-library`: `0.2.0` → `0.3.0` (new feature)
- Each consuming chart: minor version bump + `deploy/application.yaml` `targetRevision` sync

## Validation

`helm template` each chart before/after migration to confirm rendered YAML is identical (minus cosmetic whitespace).
