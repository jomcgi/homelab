---
name: helm
description: Use when testing Helm chart changes, validating templates, or inspecting chart values. For rendering and validation only - never for direct cluster deployment.
---

# Helm Chart Operations

## CRITICAL: Rendering Only

Helm is available for **testing and validation**. Never deploy directly to the cluster.

ArgoCD handles all deployments from Git.

## Allowed Operations

### Render Templates

```bash
# Render with overlay values
helm template <release> charts/<chart>/ \
  -f overlays/<env>/<service>/values.yaml \
  -n <namespace>

# Render specific template
helm template <release> charts/<chart>/ \
  -s templates/deployment.yaml \
  -f overlays/<env>/<service>/values.yaml

# Render with debug output
helm template <release> charts/<chart>/ \
  -f overlays/<env>/<service>/values.yaml \
  --debug
```

### Validate Charts

```bash
# Lint chart for issues
helm lint charts/<chart>/

# Lint with values
helm lint charts/<chart>/ -f overlays/<env>/<service>/values.yaml
```

### Inspect Values

```bash
# Show default values
helm show values charts/<chart>/

# Show all chart info
helm show all charts/<chart>/

# Show chart metadata
helm show chart charts/<chart>/
```

### Manage Dependencies

```bash
# Update chart dependencies
helm dependency update charts/<chart>/

# List dependencies
helm dependency list charts/<chart>/
```

## Forbidden Operations

**NEVER deploy directly to the cluster:**

```bash
helm install ...    # NO - use ArgoCD
helm upgrade ...    # NO - use ArgoCD
helm uninstall ...  # NO - remove from Git
helm rollback ...   # NO - revert in Git
```

## Workflow for Testing Changes

1. Edit chart templates or values
2. Render to verify output:
   ```bash
   helm template myapp charts/myapp/ -f overlays/prod/myapp/values.yaml
   ```
3. Run `format` to update rendered manifests (uses Bazel)
4. Review rendered manifests in `overlays/<env>/<service>/manifests/all.yaml`
5. Commit and push - ArgoCD deploys automatically

## Chart Structure

```
charts/<name>/
├── Chart.yaml          # Chart metadata
├── values.yaml         # Default values
├── templates/          # Kubernetes manifests
│   ├── deployment.yaml
│   ├── service.yaml
│   └── _helpers.tpl    # Template helpers
└── CLAUDE.md           # Chart-specific guidance
```

## Overlay Structure

```
overlays/<env>/<service>/
├── application.yaml    # ArgoCD Application
├── kustomization.yaml  # Makes app discoverable
├── values.yaml         # Environment-specific overrides
└── manifests/
    └── all.yaml        # Rendered output (auto-generated)
```

## Common Patterns

### Check What Changed

```bash
# Render before and after, then diff
helm template app charts/myapp/ -f overlays/prod/myapp/values.yaml > /tmp/before.yaml
# Make changes...
helm template app charts/myapp/ -f overlays/prod/myapp/values.yaml > /tmp/after.yaml
diff /tmp/before.yaml /tmp/after.yaml
```

### Validate Against Schema

```bash
# If chart has JSON schema
helm template app charts/myapp/ -f overlays/prod/myapp/values.yaml --validate
```
