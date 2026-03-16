# Helm Library Chart Design

## Problem

Six custom Helm charts in the homelab repo duplicate nearly identical boilerplate:

- `_helpers.tpl` (name, fullname, chart, labels, selectorLabels, serviceAccountName) — 95% identical across all 6
- `serviceaccount.yaml` — 100% identical across 3 charts
- `image-pull-secret.yaml` (OnePasswordItem for GHCR) — 95% identical across 4 charts
- `imageupdater.yaml` (ArgoCD Image Updater CRD) — 100% identical across 2 charts

When a pattern needs updating (e.g., adding a new standard label), every chart must be changed independently.

## Decision

Create a Helm library chart at `projects/shared/helm/homelab-library/chart/` that exports shared templates. Consumers import it via `file://` relative path dependency and call templates as one-liners.

## Library Chart Structure

```
projects/shared/helm/homelab-library/chart/
├── Chart.yaml              # type: library, version: 0.1.0
├── templates/
│   ├── _helpers.tpl        # name, fullname, chart, labels, selectorLabels, serviceAccountName, componentLabels
│   ├── _serviceaccount.tpl # Full ServiceAccount resource
│   ├── _imagepullsecret.tpl # Full OnePasswordItem for GHCR pull secret
│   └── _imageupdater.tpl   # Full ArgoCD ImageUpdater CRD
└── values.yaml             # (empty — library charts don't have default values)
```

## Distribution

`file://` relative paths. No OCI publish step. Monorepo — everything versioned together via git.

Consumer dependency example:

```yaml
dependencies:
  - name: homelab-library
    version: "0.1.0"
    repository: "file://../../shared/helm/homelab-library/chart"
```

## Templates Provided

### \_helpers.tpl

Standard naming and labeling templates prefixed with `homelab.`:

| Template                          | Purpose                                                           |
| --------------------------------- | ----------------------------------------------------------------- |
| `homelab.name`                    | Chart name, truncated to 63 chars                                 |
| `homelab.fullname`                | Release-qualified name                                            |
| `homelab.chart`                   | Chart name + version for `helm.sh/chart` label                    |
| `homelab.labels`                  | Common labels (chart, selector, version, managed-by, extraLabels) |
| `homelab.selectorLabels`          | name + instance labels                                            |
| `homelab.serviceAccountName`      | ServiceAccount name with create/default logic                     |
| `homelab.componentLabels`         | Labels with optional `app.kubernetes.io/component`                |
| `homelab.componentSelectorLabels` | Selector labels with optional component                           |

Consumers alias these in a thin `_helpers.tpl`:

```yaml
{{- define "grimoire.labels" -}}{{ include "homelab.labels" . }}{{- end }}
```

### Variations handled via values

- **trips' `part-of` label** — `extraLabels: {"app.kubernetes.io/part-of": "yukon-tracker"}` in values
- **marine's component labels** — `homelab.componentLabels` / `homelab.componentSelectorLabels`
- **grimoire's automountServiceAccountToken** — rendered only if `serviceAccount.automount` key exists

### Resource templates

Each renders a complete Kubernetes resource, controlled by `.Values`:

- `homelab.serviceaccount` — ServiceAccount with optional annotations and automount
- `homelab.imagepullsecret` — OnePasswordItem for `kubernetes.io/dockerconfigjson`
- `homelab.imageupdater` — ArgoCD ImageUpdater CRD with write-back config

Consumer usage:

```yaml
# serviceaccount.yaml
{ { - include "homelab.serviceaccount" . } }
```

## Migration Scope

| Chart           | \_helpers.tpl | serviceaccount | image-pull-secret | imageupdater |
| --------------- | :-----------: | :------------: | :---------------: | :----------: |
| grimoire        |      yes      |      yes       |        yes        |     yes      |
| ships (marine)  |      yes      |      yes       |        yes        |      —       |
| stargazer       |      yes      |      yes       |        yes        |     yes      |
| trips           |      yes      |       —        |        yes        |      —       |
| context-forge   |      yes      |       —        |         —         |      —       |
| mcp-oauth-proxy |      yes      |       —        |         —         |      —       |

**Out of scope:** agent_platform umbrella chart and its sub-charts (orchestrator, sandboxes, mcp-servers). Can be migrated later.

## Verification

For each migrated chart:

1. `helm dependency update` to pull the library
2. `helm template` before and after — diff must be empty (identical output)

## Risks

- **Relative path depth** — `file://` paths vary per chart location. Charts deeper in the tree (e.g., `projects/mcp/context-forge-gateway/chart/`) need longer relative paths. This is a one-time setup cost.
- **Chart.lock churn** — `helm dependency update` generates/updates `Chart.lock` files. These should be committed.
