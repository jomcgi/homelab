# Digest-Based Image Pushing

## Overview

The CI pipeline uses **digest-based conditional pushing** to only create new image tags in GHCR when the image content actually changes. This is achieved by comparing the digest of locally built images with what exists in the registry.

## Why Digest Comparison?

**The Problem:** Previously, every commit to `main` created new image tags, even when image content was unchanged (e.g., documentation-only commits).

**The Solution:** Only push images when their digest is new:
1. Build all images (Bazel cache makes this fast for unchanged images)
2. Compare each image's digest with the registry
3. Only push if the digest is new or doesn't exist

**Advantages over git-based detection:**
- ✅ No manual package mapping required
- ✅ Bazel's content-addressable builds ensure identical inputs → identical digest
- ✅ Automatically handles transitive dependencies
- ✅ Works for new images without configuration
- ✅ More reliable than file-based heuristics

## How It Works

### 1. Build Phase (Always runs, but cached)
```bash
# Build all images - Bazel cache makes unchanged builds near-instant
bazel build //images:push_all --config=ci
```

**Why build all?** Bazel only rebuilds when inputs change. Unchanged images use cached artifacts (~1s vs ~30s).

### 2. Digest Comparison

For each image:
```bash
LOCAL_DIGEST=$(get_digest_from_bazel_output)
REMOTE_DIGEST=$(crane digest $REPOSITORY:$TAG)

if [ "$LOCAL_DIGEST" = "$REMOTE_DIGEST" ]; then
    skip_push  # Digest unchanged
else
    push_image  # New or changed digest
fi
```

### 3. Conditional Push

Only images with new digests are pushed to GHCR.

## Example Scenarios

### Scenario: Documentation Change
```
Changed: README.md

Build: 8s (all from cache)
Compare digests: All match registry
Result: 0 pushed, 5 skipped ✓
```

### Scenario: Backend Code Change
```
Changed: operators/cloudflare/controller.go

Build: 32s (1 rebuilt, 4 cached)
Compare digests: 1 new, 4 match
Result: 1 pushed, 4 skipped ✓
```

## Benefits

- **Meaningful tags**: Tags represent actual content changes
- **Faster CI**: Skip push for unchanged images (8s vs 4m)
- **Lower costs**: No duplicate images in registry
- **Zero configuration**: Works automatically for new images

## Adding New Images

No configuration needed! Just create the image target:

```python
go_image(
    name = "my_image",
    binary = ":my_binary",
    repository = "ghcr.io/jomcgi/homelab/my-service",
)
```

CI automatically detects and handles it.

## Force Push Mode

Weekly builds and manual triggers bypass digest comparison:
```
Actions → Bazel CI → Run workflow → ✓ force_push_all
```

Use for: security updates, base image refreshes.

## Implementation

**Key script:** `scripts/push-if-digest-changed.sh`
- Queries all `oci_push` targets
- Compares digests with registry via `crane`
- Only pushes new/changed digests

**Dependencies:** crane, jq, bazel

**Fallback:** If digest comparison fails, pushes all images unconditionally.

---

For more details, see the script comments in `scripts/push-if-digest-changed.sh`.
