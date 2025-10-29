# GitHub Actions Workflow Templates

This directory contains GitHub Actions workflow templates that cannot be automatically committed by Claude due to GitHub App permissions.

## Installation

To enable the ArgoCD snapshot CI/CD workflows:

```bash
# Copy workflows to .github/workflows/
cp .github-templates/workflows/argocd-snapshot-*.yml .github/workflows/

# Commit manually
git add .github/workflows/argocd-snapshot-*.yml
git commit -m "ci: enable ArgoCD snapshot CI/CD"
git push
```

## Workflows

### argocd-snapshot-pr.yml
Builds PR-specific ArgoCD snapshots for fast, accurate diffs.
- Triggers on PR pushes affecting ArgoCD files
- Builds incremental snapshot from latest
- Pushes to ghcr.io/.../argocd-preview:pr-N
- Comments on PR with usage instructions

### argocd-snapshot-main.yml
Promotes PR snapshots to latest on merge to main.
- Fast path: Re-tags PR snapshot as :latest (~2s)
- Slow path: Incremental build if no PR found (~15s)
- Tags with commit SHA for history

## Permissions Required

These workflows require:
- `contents: read` - To checkout the repository
- `packages: write` - To push to GitHub Container Registry (ghcr.io)

These are already configured in the workflow files.
