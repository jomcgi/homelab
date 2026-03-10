---
name: add-service
description: Use when adding a new service to the homelab GitOps repository. Creates ArgoCD Application, Kustomization, and values.yaml boilerplate in projects/{service}/deploy/.
---

# Add Service to Homelab

This skill scaffolds the GitOps boilerplate for deploying a new service via ArgoCD.

## Usage

```
/add-service <service-name>
```

Arguments:

- `<service-name>`: Name of the service (e.g., `myapp`, `api-gateway`)

Examples:

```
/add-service myapp
/add-service test-service
/add-service monitoring-agent
```

## What This Skill Creates

The skill generates three files in `projects/{service}/deploy/`:

### 1. application.yaml

ArgoCD Application manifest that:

- Points to `charts/{service}` in the homelab repo
- References both chart defaults and deploy values
- Enables automated sync with prune and self-heal
- Creates namespace automatically

### 2. kustomization.yaml

Kustomize manifest that:

- Makes the Application discoverable by ArgoCD
- Lists `application.yaml` as a resource
- Can be extended with additional resources (alerts, image updaters, etc.)

### 3. values.yaml

Helm values override file with:

- Comment header indicating the service
- Placeholder sections for common configurations
- Ready for customization

## Generated Files

### application.yaml Template

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: { service }
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: charts/{service}
    helm:
      releaseName: { service }
      valueFiles:
        - values.yaml
        - ../../projects/{service}/deploy/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: { service }
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### kustomization.yaml Template

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
```

### values.yaml Template

**Important:** If you plan to add an image updater (via `/add-image-updater`), the `image` keys must be **uncommented** — not just present as comments. The image updater's git write-back fails on empty YAML files. Always seed the values with the actual image config.

```yaml
# Cluster values for {service}
# Override chart defaults here

# Image configuration — uncomment if using /add-image-updater
# image:
#   repository: ghcr.io/jomcgi/homelab/services/{service}
#   tag: main

# Example: Resource limits
# resources:
#   requests:
#     cpu: 100m
#     memory: 128Mi
#   limits:
#     cpu: 500m
#     memory: 512Mi

# Example: Enable image pull secret for private GHCR registry
# imagePullSecret:
#   enabled: true
```

## After Running This Skill

The user needs to:

1. **Create the Helm chart** at `charts/{service}/`:

   ```
   charts/{service}/
   ├── Chart.yaml
   ├── values.yaml
   ├── templates/
   │   ├── deployment.yaml
   │   ├── service.yaml
   │   └── _helpers.tpl
   └── CLAUDE.md (optional)
   ```

2. **Customize values.yaml** with service-specific overrides

3. **Run `format`** to regenerate `projects/home-cluster/kustomization.yaml`

4. **Optional: Add supporting resources**:
   - Image updater: `imageupdater.yaml` for automatic image updates
   - HTTP checks: `{service}-httpcheck-alert.yaml` for monitoring
   - Update `kustomization.yaml` to include new resources

## Example: Adding a Service

```
/add-service blog
```

Creates:

- `projects/blog/deploy/application.yaml`
- `projects/blog/deploy/kustomization.yaml`
- `projects/blog/deploy/values.yaml`

Then customize `values.yaml`:

```yaml
# Production values for blog

image:
  repository: ghcr.io/jomcgi/homelab/services/blog
  tag: v1.0.0

cloudflare:
  publicHostname: blog.jomcgi.dev

persistence:
  storageClass: longhorn
  size: 10Gi

imagePullSecret:
  enabled: true
```

## Common Add-ons

After creating the base service, use these skills to add supporting resources:

- `/add-image-updater` — automatic container image updates via ArgoCD Image Updater
- `/add-httpcheck-alert` — SigNoz HTTP health check monitoring

## Workflow Summary

1. Run `/add-service {name}` to create boilerplate
2. Create Helm chart at `charts/{name}/`
3. Customize `projects/{name}/deploy/values.yaml`
4. Commit and push - ArgoCD syncs automatically
5. Optionally add image updater, alerts, etc.
