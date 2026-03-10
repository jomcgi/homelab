# ArgoCD App Colocation Design

## Goal

Colocate ArgoCD Application definitions with their service code, replacing the `overlays/` and `clusters/` directories. A single `projects/home-cluster/` directory becomes the ArgoCD root, with an auto-generated kustomization that discovers all apps via convention.

## Motivation

The current structure splits service configuration across three directories:

```
clusters/homelab/kustomization.yaml     # ArgoCD root
overlays/{env}/{service}/               # ArgoCD app + values
projects/{service}/deploy/              # Chart definition
```

Navigating a service requires jumping between all three. Since this is a single-cluster homelab with no dev/prod environment split, the overlay abstraction adds complexity without value.

## Architecture

### Project Layout Convention

Every service colocates its deployment config:

```
projects/{service}/
  chart/                    # Only if custom/augmented chart
    Chart.yaml
    templates/
    values.yaml             # Chart defaults (publishable)
  deploy/
    application.yaml        # ArgoCD Application CR
    values.yaml             # This cluster's value overrides
    imageupdater.yaml       # Optional: image updater config
    kustomization.yaml      # resources: [application.yaml, imageupdater.yaml]
```

**When to use `chart/` vs `deploy/` only:**

- **Custom chart** (grimoire, ships, etc.): `chart/` + `deploy/`. The chart is publishable; `deploy/` has instance config.
- **Augmented upstream** (wrapping/combining upstream subcharts): `chart/` + `deploy/`.
- **Pure upstream chart** (cert-manager, signoz, etc.): `deploy/` only. The `application.yaml` points to the upstream chart repo directly.

### Auto-Discovery

A convention-based script generates the ArgoCD root kustomization:

1. `bazel/images/generate-home-cluster.sh` scans for `**/deploy/kustomization.yaml` under `projects/`
2. Generates `projects/home-cluster/kustomization.yaml` listing all discovered paths
3. Pre-commit hook keeps it in sync (same pattern as `generate-push-all.sh`)
4. `bazel/images/validate-generate-scripts.sh` cross-checks against actual state

### ArgoCD Root

`projects/home-cluster/` replaces both `clusters/` and `overlays/`:

```
projects/home-cluster/
  kustomization.yaml    # Auto-generated: lists all deploy/ paths
```

ArgoCD watches this single path. Adding a new service is: create `projects/{service}/deploy/application.yaml`, run `format`, commit.

### valueFiles

For custom charts, the application.yaml references both chart defaults and cluster overrides:

```yaml
spec:
  source:
    path: projects/{service}/chart
    helm:
      valueFiles:
        - values.yaml # Chart defaults
        - ../../deploy/values.yaml # Cluster overrides
```

For upstream charts, values sit in `deploy/` directly — no relative path gymnastics.

## What Gets Deleted

- `overlays/` — app definitions and values move into `projects/*/deploy/`
- `clusters/` — replaced by `projects/home-cluster/`

## Migration

Each service migration is independent:

1. Move `overlays/{env}/{service}/application.yaml` → `projects/{service}/deploy/application.yaml`
2. Merge overlay `values.yaml` into `projects/{service}/deploy/values.yaml`
3. Update `application.yaml` source path and valueFiles references
4. Add `imageupdater.yaml` if applicable
5. Create `deploy/kustomization.yaml`
6. Remove old overlay directory

After all services migrate, delete `overlays/` and `clusters/`, update ArgoCD to watch `projects/home-cluster/`.

## Future: Published Charts

Long-term, custom charts get published as OCI artifacts. At that point:

- `chart/` remains the source of truth for chart development
- CI publishes charts via `helm push` (like `generate-push-all.sh` for images)
- `application.yaml` references the published chart version instead of a repo path
- ArgoCD Image Updater or similar handles chart version bumps

This design supports that transition — the `chart/` vs `deploy/` separation means switching from repo-path to published-chart only changes the `application.yaml` source, not the directory structure.
