# Conditional Image Pushing

## Overview

The CI pipeline now uses **conditional image pushing** to only build and push container images when their content actually changes. This prevents creating unnecessary image tags in GHCR and reduces build/push time.

## How It Works

### Change Detection

The `scripts/detect-changed-images.sh` script:

1. **Compares against base commit** to find changed files
   - PR builds: compares against target branch (e.g., `origin/main`)
   - Main builds: compares against previous commit (`HEAD~1`)

2. **Maps changed files to image targets**
   - Maintains a mapping of image push targets to their source packages
   - Checks if any changed file affects each image's package

3. **Detects common dependency changes**
   - If core build files change (`MODULE.bazel`, `REPO.bazel`, `tools/oci/*`, etc.)
   - Triggers rebuild of ALL images (they might all be affected)

### CI Integration

The Bazel CI workflow (`.github/workflows/bazel-ci.yaml`) now:

1. **Detects changed images** first
2. **Builds only changed images** (or all if forced)
3. **Pushes only changed images** to GHCR
4. **Skips push entirely** if no images changed

## Behavior Modes

### Normal Mode (Default)

**When:** Regular commits to `main`, PR builds

**Behavior:**
- Only builds/pushes images affected by changes
- Checks changed files against image package mapping
- Skips push if no images changed

**Example:**
```bash
# Changed: operators/cloudflare/internal/controller/tunnel.go
# Result: Only pushes //operators/cloudflare:image.push
```

### Force All Mode

**When:**
- Weekly scheduled builds (`cron: '0 2 * * 0'`)
- Manual workflow_dispatch with `force_push_all=true`

**Behavior:**
- Builds and pushes ALL images
- Ignores change detection
- Ensures all images get periodic rebuilds

**Use cases:**
- Security updates to base images
- Ensuring all images are fresh
- Testing full build pipeline

## Image to Package Mapping

Currently tracked images:

| Image Target | Source Package |
|-------------|----------------|
| `//operators/cloudflare:image.push` | `operators/cloudflare` |
| `//charts/ttyd-session-manager/backend:image.push` | `charts/ttyd-session-manager/backend` |
| `//charts/ttyd-session-manager/backend:ttyd_worker_image.push` | `charts/ttyd-session-manager/backend` |
| `//charts/ttyd-session-manager/frontend:image.push` | `charts/ttyd-session-manager/frontend` |
| `//services/hikes/update_forecast:update_image.push` | `services/hikes/update_forecast` |

## Adding New Images

When you add a new image to the codebase:

1. **Add image target to mapping** in `scripts/detect-changed-images.sh`:

```bash
IMAGE_PACKAGES=(
    # ... existing entries ...
    ["//my-service:image.push"]="path/to/my-service"
)
```

2. **Verify the mapping** works:

```bash
# Make a change to your service
echo "# test" >> path/to/my-service/main.go

# Run detection script
./scripts/detect-changed-images.sh HEAD

# Should output: //my-service:image.push
```

## Manual Testing

### Test change detection locally:

```bash
# Compare against main branch
./scripts/detect-changed-images.sh origin/main

# Compare against previous commit
./scripts/detect-changed-images.sh HEAD~1

# Compare against specific commit
./scripts/detect-changed-images.sh abc123
```

### Force push all images:

```bash
# Via GitHub UI:
# Actions → Bazel CI → Run workflow
# ✓ Check "Force push all images"
```

## Benefits

### 1. **Meaningful Tags**
- Tags in GHCR now represent when image content actually changed
- No more "noise" tags from unrelated commits

### 2. **Faster CI**
- Skips building/pushing unchanged images
- Reduces CI time for non-image changes (e.g., docs, Helm charts)

### 3. **Reduced Storage**
- Fewer duplicate images in GHCR
- Lower storage costs

### 4. **Better Observability**
- Clear indication of what changed in each build
- Easy to track image update history

## Example Scenarios

### Scenario 1: Documentation Change

```bash
# Changed: README.md
# Result: No images pushed ✓
```

### Scenario 2: Backend Change

```bash
# Changed: charts/ttyd-session-manager/backend/main.go
# Result: Pushes backend image + ttyd_worker_image ✓
```

### Scenario 3: Build Tool Change

```bash
# Changed: MODULE.bazel
# Result: Pushes ALL images (common dependency) ✓
```

### Scenario 4: Helm Values Change

```bash
# Changed: charts/ttyd-session-manager/values.yaml
# Result: No images pushed (only affects Helm chart) ✓
```

## Troubleshooting

### Image not detected when it should be

1. Check if package mapping exists in `detect-changed-images.sh`
2. Verify changed files are in the correct package directory
3. Run script locally with debug output

### False positives (rebuilding when not needed)

1. Check if changed file is in common dependencies list
2. Verify package path matching logic
3. Consider narrowing package paths if too broad

### Force rebuild a specific image

**Option 1:** Use force_push_all mode (rebuilds all)

**Option 2:** Make a trivial change to force detection:
```bash
# Add/remove a comment in the image's source
echo "# trigger rebuild" >> path/to/source/file.go
git commit -am "chore: trigger image rebuild"
```

## Future Improvements

Potential enhancements:

1. **Content-based tagging**: Use image digest in tag for idempotency
2. **Bazel query integration**: Use `bazel query` for dynamic dependency detection
3. **Parallel builds**: Build multiple changed images concurrently
4. **Build caching**: Leverage Bazel's remote cache more effectively

---

**Last Updated:** 2025-01-16
**Maintainer:** GitOps Team
