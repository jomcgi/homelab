# Contributing Guide

This document covers common tasks and workflows for contributing to the homelab.

## Adding a New Service

1. Create Helm chart in `charts/<name>/` with default values
2. Choose the appropriate overlay environment:
   - `overlays/cluster-critical/` - Core infrastructure (argocd, longhorn, monitoring)
   - `overlays/prod/` - Production services
   - `overlays/dev/` - Development/experimental services
3. Create service directory in `overlays/<env>/<name>/` with:
   - `application.yaml` - ArgoCD Application pointing to your chart
     ```yaml
     valueFiles:
       - values.yaml  # Chart defaults
       - ../../overlays/<env>/<name>/values.yaml  # Environment overrides
     ```
   - `kustomization.yaml` - Reference to application.yaml
   - `values.yaml` - Environment-specific Helm value overrides
4. Add the service to `overlays/<env>/kustomization.yaml` resources list
5. Add health checks and observability to the chart
6. Test the complete deployment path:
   - `helm template <service> charts/<service>/ --namespace <namespace>` to verify rendering
   - Commit and push to Git
   - ArgoCD automatically discovers and syncs the new application to the cluster

## Format Command

Run before committing changes:

```bash
format
```

This command:
- **Formats code** (Go, Python, JavaScript, Shell, Starlark)
- **Updates apko lock files** (container image definitions)
- **Updates Python lock files** (from pyproject.toml)
- **Validates apko configurations**
- **Runs in parallel** using Bazel for fast builds

Note: Helm manifests are rendered by ArgoCD at deploy time, not committed to the repo.

## Adding Python Dependencies

When adding a new Python dependency to `pyproject.toml`:

```bash
# 1. Add dependency to pyproject.toml
# 2. Regenerate lock files (included in format command)
format
```

## CLI Tools

- **Directory tree viewer**: Use `lstr -L <depth> <path>` instead of `tree`
  - Example: `lstr -L 2 charts/` to view 2 levels deep
  - Use `-d` for directories only, `--icons` for file icons

## Development Workflow

1. **Make changes** in feature branch (via worktree)
2. **Run `format`** to format code and update lock files
3. **Verify deployment** works end-to-end
4. **Check observability** - metrics, logs, traces
5. **Create PR** - GitHub Actions runs integration tests
6. **Merge** - ArgoCD automatically syncs changes to production cluster

## Testing Philosophy

We test **actual behavior**, not implementation details:

**Good Tests:**
- Deploy the actual service to a test cluster
- Verify the service responds correctly via HTTP
- Confirm metrics are exported and observable
- Test the complete user journey

**Bad Tests:**
- Unit tests that mock everything
- Tests that verify internal implementation
- Tests that don't exercise real deployment paths
