---
name: add-service
description: Use when adding a new service to the homelab GitOps repository. Creates ArgoCD Application, Kustomization, and values.yaml boilerplate in overlays/{env}/{service}/.
---

# Add Service to Homelab

This skill scaffolds the GitOps boilerplate for deploying a new service via ArgoCD.

## Usage

```
/add-service <service-name> <environment>
```

Arguments:
- `<service-name>`: Name of the service (e.g., `myapp`, `api-gateway`)
- `<environment>`: Target environment - one of `prod`, `dev`, or `cluster-critical`

Examples:
```
/add-service myapp prod
/add-service test-service dev
/add-service monitoring-agent cluster-critical
```

## What This Skill Creates

The skill generates three files in `overlays/{env}/{service}/`:

### 1. application.yaml

ArgoCD Application manifest that:
- Points to `charts/{service}` in the homelab repo
- References both chart defaults and overlay values
- Enables automated sync with prune and self-heal
- Creates namespace automatically

### 2. kustomization.yaml

Kustomize manifest that:
- Makes the Application discoverable by ArgoCD
- Lists `application.yaml` as a resource
- Can be extended with additional resources (alerts, image updaters, etc.)

### 3. values.yaml

Helm values override file with:
- Comment header indicating the environment
- Placeholder sections for common configurations
- Ready for customization

## Generated Files

### application.yaml Template

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {service}
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jomcgi/homelab.git
    targetRevision: HEAD
    path: charts/{service}
    helm:
      releaseName: {service}
      valueFiles:
        - values.yaml
        - ../../overlays/{env}/{service}/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: {service}
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

```yaml
# {Environment} values for {service}
# Override chart defaults here

# Example: Image configuration
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

2. **Customize values.yaml** with environment-specific overrides

3. **Add to environment kustomization** (if not auto-discovered):
   - Edit `overlays/{env}/kustomization.yaml`
   - Add `- {service}` to the resources list

4. **Optional: Add supporting resources**:
   - Image updater: `imageupdater.yaml` for automatic image updates
   - HTTP checks: `{service}-httpcheck-alert.yaml` for monitoring
   - Update `kustomization.yaml` to include new resources

## Environment-Specific Notes

### prod
- Services accessible to users
- Typically exposed via Cloudflare tunnel
- Should have production-grade resource limits

### dev
- Testing and development services
- May have relaxed security or resource limits
- Good for iterating on new features

### cluster-critical
- Infrastructure services (cert-manager, argocd, longhorn, etc.)
- Often has finalizers to prevent accidental deletion
- May need `ServerSideApply=true` for CRDs
- Consider adding retry policies for stability

## Example: Adding a Production Service

```
/add-service blog prod
```

Creates:
- `overlays/prod/blog/application.yaml`
- `overlays/prod/blog/kustomization.yaml`
- `overlays/prod/blog/values.yaml`

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

After creating the base service, you may want to add:

### Image Updater (for auto-updating container images)

Create `overlays/{env}/{service}/imageupdater.yaml`:
```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: {service}
  namespace: argocd
spec:
  applicationRefs:
    - images:
        - alias: {service}
          commonUpdateSettings:
            updateStrategy: digest
            forceUpdate: false
          imageName: ghcr.io/jomcgi/homelab/charts/{service}:main
          manifestTargets:
            helm:
              name: image.repository
              tag: image.tag
      namePattern: {service}
  writeBackConfig:
    method: git:secret:argocd/argocd-image-updater-token
    gitConfig:
      repository: https://github.com/jomcgi/homelab.git
      branch: main
      writeBackTarget: helmvalues:../../overlays/{env}/{service}/values.yaml
```

Then update `kustomization.yaml`:
```yaml
resources:
  - application.yaml
  - imageupdater.yaml
```

### HTTP Check Alert (for monitoring)

Create `overlays/{env}/{service}/{service}-httpcheck-alert.yaml` with SigNoz alert rules.

## Workflow Summary

1. Run `/add-service {name} {env}` to create boilerplate
2. Create Helm chart at `charts/{name}/`
3. Customize `overlays/{env}/{name}/values.yaml`
4. Commit and push - ArgoCD syncs automatically
5. Optionally add image updater, alerts, etc.
