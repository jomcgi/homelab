# ArgoCD Gazelle Extension

Gazelle extension that auto-generates Bazel BUILD files for ArgoCD applications, creating `argocd_diff` targets for accurate manifest diffing.

## What It Does

Scans directories for `application.yaml` files and automatically generates:
- `argocd_diff` rules that use ArgoCD snapshot-based diffing
- Multi-cluster support with cluster-specific diff targets
- No manual BUILD file maintenance needed

## Usage

### Basic Setup

1. **Run Gazelle** to auto-generate BUILD files:
   ```bash
   bazel run //:gazelle
   ```

2. **Use the generated targets**:
   ```bash
   bazel run //overlays/prod/n8n:diff  # Compare with origin/main
   ```

### Generated BUILD File Example

For `overlays/prod/n8n/application.yaml`, Gazelle generates:

```starlark
load("//tools/argocd-gazelle:defs.bzl", "argocd_diff")

argocd_diff(
    name = "diff",
    application = "application.yaml",
    base_branch = "origin/main",
)
```

Run with: `bazel run //overlays/prod/n8n:diff`

## Multi-Cluster Support

Configure clusters using Gazelle directives in `kustomization.yaml` or BUILD files:

```yaml
# gazelle:argocd_clusters cluster1,cluster2,production

# Optional: Specify cluster-specific snapshot images
# gazelle:argocd_cluster_snapshot cluster1=ghcr.io/jomcgi/argocd-preview:cluster1
# gazelle:argocd_cluster_snapshot cluster2=ghcr.io/jomcgi/argocd-preview:cluster2
```

This generates cluster-specific targets:

```bash
bazel run //overlays/prod/n8n:diff              # Default (latest snapshot)
bazel run //overlays/prod/n8n:diff_cluster1     # cluster1 snapshot
bazel run //overlays/prod/n8n:diff_cluster2     # cluster2 snapshot
```

## Gazelle Directives

Control BUILD file generation with these directives:

| Directive | Values | Description |
|-----------|--------|-------------|
| `argocd` | `enabled`, `disabled` | Enable/disable BUILD generation |
| `argocd_enabled` | (none) | Enable BUILD generation |
| `argocd_base_branch` | branch name | Default base branch for diffs |
| `argocd_clusters` | cluster1,cluster2 | Generate cluster-specific targets |
| `argocd_cluster_snapshot` | cluster=image | Map cluster to snapshot image |

### Example Configuration

```yaml
# overlays/prod/kustomization.yaml

# Enable ArgoCD diff generation
# gazelle:argocd_enabled

# Compare against develop instead of main
# gazelle:argocd_base_branch origin/develop

# Generate targets for multiple clusters
# gazelle:argocd_clusters homelab,staging,production

# Use cluster-specific snapshots
# gazelle:argocd_cluster_snapshot staging=ghcr.io/jomcgi/argocd-preview:staging
# gazelle:argocd_cluster_snapshot production=ghcr.io/jomcgi/argocd-preview:production

resources:
  - n8n/application.yaml
  - cloudflare-tunnel/application.yaml
```

After running `bazel run //:gazelle`, each application directory gets:

```starlark
# overlays/prod/n8n/BUILD (auto-generated)
argocd_diff(name = "diff", ...)
argocd_diff(name = "diff_homelab", cluster = "homelab", ...)
argocd_diff(name = "diff_staging", cluster = "staging", snapshot_image = "ghcr.io/.../staging", ...)
argocd_diff(name = "diff_production", cluster = "production", snapshot_image = "ghcr.io/.../production", ...)
```

## Benefits

### vs Manual Helm Rendering
- ✅ 100% ArgoCD parity (uses real ArgoCD)
- ✅ Works with Helm, Kustomize, plugins, SSA
- ✅ No guessing at what ArgoCD will render

### vs Manual BUILD Files
- ✅ Zero maintenance - Gazelle generates everything
- ✅ Consistent pattern across all apps
- ✅ Automatically discovers new applications

## Architecture

```
┌──────────────────────────────────────────────────┐
│ Gazelle Discovers application.yaml Files        │
├──────────────────────────────────────────────────┤
│  overlays/prod/n8n/application.yaml              │
│  overlays/prod/cloudflare-tunnel/application.yaml│
│  overlays/dev/freshrss/application.yaml          │
└──────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Generates argocd_diff Rules                      │
├──────────────────────────────────────────────────┤
│  //overlays/prod/n8n:diff                        │
│  //overlays/prod/cloudflare-tunnel:diff          │
│  //overlays/dev/freshrss:diff                    │
└──────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ Rules Call //tools/argocd:diff                   │
├──────────────────────────────────────────────────┤
│  - Starts ArgoCD from snapshot                   │
│  - Renders both branches                         │
│  - Shows diff                                    │
│  - 100% accurate (real ArgoCD!)                  │
└──────────────────────────────────────────────────┘
```

## Implementation

The extension consists of:

- `language.go` - Gazelle language interface
- `config.go` - Directive parsing and configuration
- `generate.go` - BUILD file generation logic
- `defs.bzl` - Public API (argocd_diff rule)
- `private/diff.bzl` - Rule implementation

## Future Enhancements

- [ ] Auto-detect clusters from `clusters/` directory structure
- [ ] Support for ApplicationSet resources
- [ ] Helm dependency pre-loading in snapshots
- [ ] Progressive diff (show only changed resources)

## See Also

- [//tools/argocd/README.md](../argocd/README.md) - Snapshot-based diffing architecture
- [.github-templates/workflows/](../../.github-templates/workflows/) - CI/CD snapshot automation
