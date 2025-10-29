# ArgoCD Diff Preview with Snapshots

Fast, accurate ArgoCD manifest diffing using Docker snapshots.

## Why This Approach?

**Problem:** We need to see what ArgoCD will deploy, but:
- ❌ Direct `helm template` doesn't match ArgoCD exactly (plugins, transformations, SSA)
- ❌ Spinning up ephemeral clusters takes 60-80 seconds every time
- ❌ Running persistent clusters wastes resources

**Solution:** Docker container snapshots!
- ✅ 100% ArgoCD parity (using real ArgoCD)
- ✅ Fast: ~5-10 second startup from snapshot
- ✅ Simple: Just Docker commands
- ✅ Portable: Share snapshots via registry

## Architecture

```
┌──────────────────────────────────────────────────┐
│ ONE-TIME SETUP (~60 seconds)                     │
├──────────────────────────────────────────────────┤
│                                                  │
│  1. kind create cluster                          │
│  2. Install ArgoCD                               │
│  3. docker commit → snapshot image               │
│  4. Delete temp cluster                          │
│                                                  │
│  Result: homelab/argocd-preview:latest           │
│                                                  │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ EVERY DIFF (~10 seconds)                         │
├──────────────────────────────────────────────────┤
│                                                  │
│  1. docker run snapshot image                    │
│     ↓ (5s - container starts with ArgoCD ready)  │
│                                                  │
│  2. argocd-diff-preview renders both branches    │
│     ↓ (5s - actual ArgoCD rendering)             │
│                                                  │
│  3. Show diff                                    │
│                                                  │
│  4. Cleanup (docker stop)                        │
│                                                  │
└──────────────────────────────────────────────────┘
```

## Usage

### 1. One-Time Setup

Create the ArgoCD snapshot:

```bash
# Create snapshot (~60 seconds)
bazel run //tools/argocd:create_snapshot

# Or directly:
./scripts/create-argocd-snapshot.sh
```

This creates `homelab/argocd-preview:latest` - a Docker image with:
- Kind cluster node
- Kubernetes API server
- ArgoCD installed and ready
- ~500MB total size

### 2. Run Diffs (Fast!)

```bash
# Compare current branch with main
bazel run //tools/argocd:diff

# Compare with specific branch
bazel run //tools/argocd:diff -- origin/develop

# Or directly:
./tools/argocd/diff.sh origin/main
```

**Performance:** ~10 seconds total
- 5s: Start container from snapshot
- 5s: Render manifests with ArgoCD

## How It Works

### Snapshot Creation

1. **Create temporary cluster:**
   ```bash
   kind create cluster --name argocd-snapshot-temp
   ```

2. **Install ArgoCD:**
   ```bash
   kubectl apply -f argocd-manifests.yaml
   ```

3. **Commit Docker container state:**
   ```bash
   docker commit argocd-snapshot-temp-control-plane homelab/argocd-preview:latest
   ```

4. **Cleanup:**
   ```bash
   kind delete cluster --name argocd-snapshot-temp
   ```

### Diff Execution

1. **Start from snapshot:**
   ```bash
   docker run -d --privileged homelab/argocd-preview:latest
   ```
   The container starts with:
   - Kubernetes API server already running
   - ArgoCD already installed
   - Ready to accept Applications

2. **Run diff:**
   ```bash
   argocd-diff-preview \
     --argocd-url <container-url> \
     --base origin/main
   ```
   This:
   - Applies Applications from both branches to ArgoCD
   - Renders manifests using ArgoCD (Helm, Kustomize, plugins all work)
   - Compares the rendered output
   - Shows the diff

3. **Cleanup:**
   ```bash
   docker stop <container>
   ```

## Benefits

### vs Ephemeral Clusters
- **60-80s** per diff → **~10s** per diff
- Same ArgoCD parity
- Same accuracy

### vs Persistent Clusters
- No background resource usage
- No "did I remember to start it?"
- Can version snapshots (Git, registry)

### vs Direct Helm/Kustomize
- **100% ArgoCD parity** (it IS ArgoCD)
- Works with plugins, transformations, SSA
- Supports all ArgoCD features

## Advanced Usage

### Version Snapshots in Git

Store the snapshot in your repository:

```bash
# Export snapshot
docker save homelab/argocd-preview:latest | gzip > .devcontainer/argocd-snapshot.tar.gz

# Load snapshot
docker load < .devcontainer/argocd-snapshot.tar.gz
```

**Pros:**
- Everyone gets exact same ArgoCD version
- No need to rebuild
- Works in CI immediately

**Cons:**
- ~200MB compressed file in repo

### Push to Registry

Share via container registry:

```bash
# Tag for registry
docker tag homelab/argocd-preview:latest \
  ghcr.io/jomcgi/argocd-preview:latest

# Push
docker push ghcr.io/jomcgi/argocd-preview:latest

# Pull on other machines
docker pull ghcr.io/jomcgi/argocd-preview:latest
```

### Update ArgoCD Version

When ArgoCD releases a new version:

```bash
# Recreate snapshot with new version
./scripts/create-argocd-snapshot.sh

# Push updated snapshot
docker push ghcr.io/jomcgi/argocd-preview:latest
```

## CI Integration

### Automated Snapshot Builds

The repository includes GitHub Actions workflows that automatically manage snapshots:

#### On PR Push (.github/workflows/argocd-snapshot-pr.yml)

```
1. Load latest snapshot from registry
2. Apply PR changes incrementally
3. Push as ghcr.io/.../argocd-preview:pr-123
4. Comment on PR with usage instructions
```

**Benefits:**
- ✅ PR-specific snapshots ready immediately
- ✅ Fast iteration (rebuilds use PR snapshot as base)
- ✅ Image cached in registry for team
- ✅ ~15s build time

#### On Merge to Main (.github/workflows/argocd-snapshot-main.yml)

```
Fast path (if from PR):
  1. Pull PR snapshot
  2. Re-tag as :latest
  3. Push (~2 seconds!)

Slow path (direct push):
  1. Load :latest snapshot
  2. Apply changes incrementally
  3. Push as :latest (~15 seconds)
```

**Benefits:**
- ✅ Instant promotion (just metadata update)
- ✅ No duplicate builds
- ✅ Always have warm cache

### Snapshot Versioning Strategy

```
ghcr.io/jomcgi/argocd-preview:latest          # Current main
ghcr.io/jomcgi/argocd-preview:pr-123          # PR-specific
ghcr.io/jomcgi/argocd-preview:main-abc123     # Main commit SHA
ghcr.io/jomcgi/argocd-preview:20250129-1430   # Timestamp backup
```

### Using PR Snapshots Locally

When working on a PR, use the PR-specific snapshot for instant diffs:

```bash
# Pull your PR's snapshot
docker pull ghcr.io/jomcgi/argocd-preview:pr-123

# Use it for diffs
SNAPSHOT_IMAGE=ghcr.io/jomcgi/argocd-preview:pr-123 \
  bazel run //tools/argocd:diff -- origin/main
```

The image is already warm and ready - no wait time!

## Troubleshooting

### "Snapshot image not found"

Create the snapshot:
```bash
./scripts/create-argocd-snapshot.sh
```

### "Container fails to start"

The snapshot might be corrupted. Recreate it:
```bash
docker rmi homelab/argocd-preview:latest
./scripts/create-argocd-snapshot.sh
```

### "ArgoCD API not responding"

The container needs a few seconds to start. The script waits automatically, but if you're debugging:
```bash
docker exec argocd-preview kubectl get pods -n argocd
```

### Snapshot is too large

The snapshot includes the full Kind node image plus ArgoCD. To reduce size:

1. Use a minimal Kind image
2. Clean up ArgoCD logs before committing
3. Compress when storing in Git

Typical size: ~500MB uncompressed, ~200MB compressed

## Comparison with Alternatives

| Approach | Speed | Accuracy | Resource Usage | Complexity |
|----------|-------|----------|----------------|------------|
| **Docker snapshot** ✅ | 10s | 100% | None (ephemeral) | Low |
| Ephemeral cluster | 60-80s | 100% | None (ephemeral) | Low |
| Persistent cluster | 5-10s | 100% | ~100MB RAM | Medium |
| Direct helm | 1-2s | ~95% | None | Medium |
| KWOK snapshot | 2-5s | ⚠️ Unknown | None | High |

## Future Enhancements

- [ ] Bazel rule to auto-rebuild snapshot when ArgoCD version changes
- [ ] Pre-load common chart repos in snapshot
- [ ] Multiple snapshot variants (different ArgoCD versions)
- [ ] Cached layer optimization for faster commits

## References

- [argocd-diff-preview](https://github.com/dag-andersen/argocd-diff-preview)
- [Kind documentation](https://kind.sigs.k8s.io/)
- [Docker commit reference](https://docs.docker.com/engine/reference/commandline/commit/)
