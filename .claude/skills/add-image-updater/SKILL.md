---
name: add-image-updater
description: Add ArgoCD Image Updater configuration for automatic container image updates. Use when setting up automatic digest-based image updates for a service.
---

# Add ArgoCD Image Updater Configuration

This skill creates an ImageUpdater resource that enables automatic container image updates for an ArgoCD-managed service.

## Automatic Update Loop

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: New Image Pushed to GHCR                               │
│  - CI builds and pushes image to ghcr.io/jomcgi/homelab/...     │
│  - Image has same tag (:main) but new digest (SHA256 hash)      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: ArgoCD Image Updater Detects New Digest                │
│  - Polls GHCR every 2 minutes (configurable)                    │
│  - Compares current digest in values.yaml with registry         │
│  - Detects new digest available                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Image Updater Modifies Git                             │
│  - Clones homelab repo                                          │
│  - Updates projects/<service>/deploy/values.yaml:                │
│      image:                                                      │
│        repository: ghcr.io/jomcgi/homelab/projects/myapp        │
│        tag: main@sha256:abc123...  ← new digest                 │
│  - Commits and pushes to main branch                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: ArgoCD Detects Git Change                              │
│  - Sees values.yaml updated in Git                              │
│  - Re-renders Helm chart with new image digest                  │
│  - Syncs deployment to cluster (rollout restart)                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Kubernetes Pulls New Image                             │
│  - Pulls image by digest from GHCR                              │
│  - Starts new pods with updated image                           │
│  - Terminates old pods (rolling update)                         │
└─────────────────────────────────────────────────────────────────┘
        │
        └─────► Loop repeats on next image push
```

## Usage

```
/add-image-updater <service-name> [image-pattern]
```

**Arguments:**

- `<service-name>` (required): Name of the service (must match ArgoCD Application namePattern)
- `[image-pattern]` (optional): Custom image path. Defaults to `ghcr.io/jomcgi/homelab/projects/<service-name>:main`

**Examples:**

```
/add-image-updater myapp
/add-image-updater cloudflare-operator operators/cloudflare
/add-image-updater signoz-dashboard-sidecar signoz-dashboard-sidecar
```

## What This Creates

An `imageupdater.yaml` file in `projects/<service>/deploy/` that:

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

| Field                                                       | Description                                        |
| ----------------------------------------------------------- | -------------------------------------------------- |
| `metadata.name`                                             | Must match the service name                        |
| `spec.applicationRefs[].namePattern`                        | Must match the ArgoCD Application name             |
| `spec.applicationRefs[].images[].alias`                     | Identifier for this image (usually service name)   |
| `spec.applicationRefs[].images[].imageName`                 | Full image path with tag (`:main` for main branch) |
| `spec.applicationRefs[].images[].manifestTargets.helm.name` | Helm value path for repository                     |
| `spec.applicationRefs[].images[].manifestTargets.helm.tag`  | Helm value path for tag                            |
| `spec.writeBackConfig.writeBackTarget`                      | Relative path from repo root to values.yaml        |

## Step-by-Step Guide

### Step 1: Determine the Service Location

Identify where the service deploy config lives:

```
projects/<service>/deploy/
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
  name: todo # <-- This is the namePattern (no env prefix)
```

### Step 3: Determine the Image Path

Images follow these patterns:

| Type        | Pattern                                       |
| ----------- | --------------------------------------------- |
| Any service | `ghcr.io/jomcgi/homelab/projects/<path>:main` |

### Step 4: Calculate the Relative Path

The `writeBackTarget` path is relative from where ArgoCD renders manifests (typically `charts/<chart>/`).

Common patterns:

| Service Location             | Relative Path                                 |
| ---------------------------- | --------------------------------------------- |
| `projects/<service>/deploy/` | `../../projects/<service>/deploy/values.yaml` |

### Step 5: Create the ImageUpdater File

Create `projects/<service>/deploy/imageupdater.yaml`:

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
          imageName: ghcr.io/jomcgi/homelab/projects/<service-name>:main
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
      writeBackTarget: helmvalues:../../projects/<service>/deploy/values.yaml
```

### Step 6: Add to Kustomization

Update `projects/<service>/deploy/kustomization.yaml` to include the new file:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - application.yaml
  - imageupdater.yaml # <-- Add this line
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

## Critical: Seed the Write-Back Target

The deploy `values.yaml` **must contain a valid YAML mapping** with the image keys before the image updater can write to it. If the file is empty or contains only comments, the updater will fail with:

```
failed to set image parameter version value: unexpected type  for root
```

When creating an image updater, always ensure the deploy `values.yaml` includes the image structure that matches the `manifestTargets.helm` paths:

```yaml
# Example: for helm.name=image.repository and helm.tag=image.tag
image:
  repository: ghcr.io/jomcgi/homelab/projects/myapp
  tag: main

# Example: for helm.name=sandboxTemplate.image.repository
sandboxTemplate:
  image:
    repository: ghcr.io/jomcgi/homelab/projects/agent_platform/goose_agent/image
    tag: main
```

The updater will then overwrite the `tag` value with the digest-pinned version on each update cycle.

## Troubleshooting

| Issue                      | Solution                                                              |
| -------------------------- | --------------------------------------------------------------------- |
| Image not updating         | Check `namePattern` matches ArgoCD Application name exactly           |
| Git write-back fails       | Verify `argocd-image-updater-token` secret exists in argocd namespace |
| `unexpected type for root` | Overlay `values.yaml` is empty — seed it with the image key structure |
| Wrong values file updated  | Check `writeBackTarget` relative path is correct                      |
| Digest not changing        | Ensure CI is pushing to the correct image tag (`:main`)               |
