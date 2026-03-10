# Contributing Guide

This document covers common tasks and workflows for contributing to the homelab.

## Repository Structure

This is a GitOps monorepo where related code and deployment configuration live together.

| Directory                | Purpose                                                                           |
| ------------------------ | --------------------------------------------------------------------------------- |
| `projects/<project>/`    | Project groups containing services, operators, and their deployment configs       |
| `charts/<service>/`      | Helm charts with templates, values, and source code for service-specific binaries |
| `projects/home-cluster/` | Auto-generated root kustomization that discovers all deploy/ directories          |
| `operators/`             | Custom Kubernetes operators                                                       |
| `services/`              | Standalone services not deployed via Helm                                         |
| `images/`                | Container image definitions (apko)                                                |

**Colocation principle:** Each service's deployment configuration (ArgoCD Application, Helm values) lives in a `deploy/` directory next to its source code, not in a separate overlays directory. This makes it easy to understand what belongs together.

## Adding a New Service

### ArgoCD Discovery Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  Step 1: Create Helm Chart (if needed)                              │
│  charts/<service>/                                                   │
│    ├── Chart.yaml                                                    │
│    ├── values.yaml (defaults)                                        │
│    └── templates/                                                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 2: Create Colocated deploy/ Directory                         │
│  projects/<project>/<service>/deploy/                                │
│    ├── application.yaml    (ArgoCD Application manifest)             │
│    ├── kustomization.yaml  (makes app discoverable)                  │
│    └── values.yaml         (Helm value overrides)                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 3: Auto-Discovery                                             │
│  Run: bazel/images/generate-home-cluster.sh                         │
│  This scans projects/ for deploy/ dirs containing                    │
│  application.yaml and regenerates                                    │
│  projects/home-cluster/kustomization.yaml                            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 4: ArgoCD Auto-Discovery                                      │
│  clusters/homelab/kustomization.yaml redirects to                    │
│  projects/home-cluster/ which lists all deploy/ dirs.                │
│                                                                      │
│  The "canada" Application is the root app-of-apps.                   │
│  ArgoCD runs "kustomize build" and discovers all                     │
│  Application manifests automatically.                                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 5: ArgoCD Syncs Application                                   │
│  - Renders Helm chart with value files                              │
│  - Applies manifests to cluster                                     │
│  - Monitors health and sync status                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Service Directory Structure

```
projects/
├── platform/              # Core infrastructure
│   ├── argocd/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── envoy/
│   ├── kyverno/
│   └── kustomization.yaml  ← references all platform services
│
├── agent_platform/        # Agent services
│   ├── agent-orchestrator/deploy/
│   ├── context-forge/deploy/
│   └── kustomization.yaml  ← references all agent services
│
├── grimoire/              # Individual project with colocated deploy/
│   ├── deploy/
│   │   ├── application.yaml
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   └── src/               # Source code lives alongside deploy/
│
└── home-cluster/          # Auto-generated root (DO NOT EDIT)
    └── kustomization.yaml  ← lists all deploy/ dirs
```

### Steps

1. Create Helm chart in `charts/<name>/` with default values (or use an upstream chart)
2. Create a `deploy/` directory colocated with your service source:
   - `projects/<project>/<service>/deploy/application.yaml` - ArgoCD Application pointing to your chart
   - `projects/<project>/<service>/deploy/kustomization.yaml` - Reference to application.yaml
   - `projects/<project>/<service>/deploy/values.yaml` - Helm value overrides
3. Run `bazel/images/generate-home-cluster.sh` to regenerate the root kustomization
4. Add health checks and observability to the chart
5. Test the complete deployment path:
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
