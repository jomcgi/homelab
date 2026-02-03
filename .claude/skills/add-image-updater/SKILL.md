---
name: add-image-updater
description: Add ArgoCD Image Updater configuration for automatic container image updates. Use when setting up automatic digest-based image updates for a service.
---

# Add ArgoCD Image Updater Configuration

This skill creates an ImageUpdater resource that enables automatic container image updates for an ArgoCD-managed service.

## Usage

```
/add-image-updater <service-name> [image-pattern]
```

**Arguments:**

- `<service-name>` (required): Name of the service (must match ArgoCD Application namePattern)
- `[image-pattern]` (optional): Custom image path. Defaults to `ghcr.io/jomcgi/homelab/charts/<service-name>:main`

**Examples:**

```
/add-image-updater myapp
/add-image-updater cloudflare-operator operators/cloudflare
/add-image-updater signoz-dashboard-sidecar signoz-dashboard-sidecar
```

## What This Creates

An `imageupdater.yaml` file in `overlays/<env>/<service>/` that:

1. Monitors a container image registry for digest changes
2. Updates the service's `values.yaml` when new images are pushed
3. Commits changes back to Git automatically

## ImageUpdater Resource Structure

```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: <service-name>
  namespace: argocd
spec:
  applicationRefs:
    - images:
        - alias: <service-name>
          commonUpdateSettings:
            updateStrategy: digest
            forceUpdate: false
          imageName: ghcr.io/jomcgi/homelab/<image-path>:main
          manifestTargets:
            helm:
              name: image.repository
              tag: image.tag
      namePattern: <argocd-app-name>
  namespace: argocd
  writeBackConfig:
    method: git:secret:argocd/argocd-image-updater-token
    gitConfig:
      repository: https://github.com/jomcgi/homelab.git
      branch: main
      writeBackTarget: helmvalues:<relative-path-to-values.yaml>
```

## Field Reference

| Field | Description |
|-------|-------------|
| `metadata.name` | Must match the service name |
| `spec.applicationRefs[].namePattern` | Must match the ArgoCD Application name |
| `spec.applicationRefs[].images[].alias` | Identifier for this image (usually service name) |
| `spec.applicationRefs[].images[].imageName` | Full image path with tag (`:main` for main branch) |
| `spec.applicationRefs[].images[].manifestTargets.helm.name` | Helm value path for repository |
| `spec.applicationRefs[].images[].manifestTargets.helm.tag` | Helm value path for tag |
| `spec.writeBackConfig.writeBackTarget` | Relative path from repo root to values.yaml |

## Step-by-Step Guide

### Step 1: Determine the Service Location

Identify where the service overlay lives:

```
overlays/<env>/<service>/
  - application.yaml    # ArgoCD Application
  - kustomization.yaml  # Includes imageupdater.yaml
  - values.yaml         # Helm values (target for write-back)
```

### Step 2: Find the ArgoCD Application Name

Check the Application's `metadata.name` in `application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: todo  # <-- This is the namePattern (no env prefix)
```

### Step 3: Determine the Image Path

Images follow these patterns:

| Type | Pattern |
|------|---------|
| Chart-based service | `ghcr.io/jomcgi/homelab/charts/<name>:main` |
| Operator | `ghcr.io/jomcgi/homelab/operators/<name>:main` |
| Standalone image | `ghcr.io/jomcgi/homelab/<name>:main` |

### Step 4: Calculate the Relative Path

The `writeBackTarget` path is relative from where ArgoCD renders manifests (typically `charts/<chart>/`).

Common patterns:

| Service Location | Relative Path |
|-----------------|---------------|
| `overlays/prod/<service>/` | `../../overlays/prod/<service>/values.yaml` |
| `overlays/dev/<service>/` | `../../overlays/dev/<service>/values.yaml` |
| `overlays/cluster-critical/<service>/` | `../../overlays/cluster-critical/<service>/values.yaml` |

For operators with nested charts:

| Service Location | Relative Path |
|-----------------|---------------|
| `overlays/dev/<operator>/` | `../../../../overlays/dev/<operator>/values.yaml` |

### Step 5: Create the ImageUpdater File

Create `overlays/<env>/<service>/imageupdater.yaml`:

```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: <service-name>
  namespace: argocd
spec:
  applicationRefs:
    - images:
        - alias: <service-name>
          commonUpdateSettings:
            updateStrategy: digest
            forceUpdate: false
          imageName: ghcr.io/jomcgi/homelab/charts/<service-name>:main
          manifestTargets:
            helm:
              name: image.repository
              tag: image.tag
      namePattern: <argocd-app-name>
  namespace: argocd
  writeBackConfig:
    method: git:secret:argocd/argocd-image-updater-token
    gitConfig:
      repository: https://github.com/jomcgi/homelab.git
      branch: main
      writeBackTarget: helmvalues:../../overlays/<env>/<service>/values.yaml
```

### Step 6: Add to Kustomization

Update `overlays/<env>/<service>/kustomization.yaml` to include the new file:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - imageupdater.yaml  # <-- Add this line
```

## Custom Helm Value Paths

If your chart uses non-standard value paths for images, adjust `manifestTargets`:

**Standard (most charts):**

```yaml
manifestTargets:
  helm:
    name: image.repository
    tag: image.tag
```

**Operator pattern:**

```yaml
manifestTargets:
  helm:
    name: controllerManager.image.repository
    tag: controllerManager.image.tag
```

**Nested image config:**

```yaml
manifestTargets:
  helm:
    name: app.container.image.repository
    tag: app.container.image.tag
```

## Update Strategy

The `digest` strategy:

- Tracks image digests (SHA256 hashes)
- Triggers updates when new images are pushed to the same tag
- Does NOT update `values.yaml` tag value (stays as `:main`)
- Updates are based on digest changes only

Other strategies (not commonly used here):

- `semver`: Follow semantic versioning
- `latest`: Always use latest tag
- `name`: Match by tag name pattern

## Verification

After creating the ImageUpdater:

1. Commit and push changes
2. ArgoCD syncs the ImageUpdater resource
3. Check Image Updater logs:
   ```bash
   kubectl logs -n argocd -l app.kubernetes.io/name=argocd-image-updater
   ```
4. Verify it detects your application:
   ```bash
   kubectl get imageupdater -n argocd
   ```

## Complete Example

For a new service `myapp` in `overlays/prod/myapp/`:

**overlays/prod/myapp/imageupdater.yaml:**

```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: myapp
  namespace: argocd
spec:
  applicationRefs:
    - images:
        - alias: myapp
          commonUpdateSettings:
            updateStrategy: digest
            forceUpdate: false
          imageName: ghcr.io/jomcgi/homelab/charts/myapp:main
          manifestTargets:
            helm:
              name: image.repository
              tag: image.tag
      namePattern: myapp
  namespace: argocd
  writeBackConfig:
    method: git:secret:argocd/argocd-image-updater-token
    gitConfig:
      repository: https://github.com/jomcgi/homelab.git
      branch: main
      writeBackTarget: helmvalues:../../overlays/prod/myapp/values.yaml
```

**overlays/prod/myapp/kustomization.yaml:**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - imageupdater.yaml
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Image not updating | Check `namePattern` matches ArgoCD Application name exactly |
| Git write-back fails | Verify `argocd-image-updater-token` secret exists in argocd namespace |
| Wrong values file updated | Check `writeBackTarget` relative path is correct |
| Digest not changing | Ensure CI is pushing to the correct image tag (`:main`) |
