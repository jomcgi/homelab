# Fix: BuildBuddy Remote Cache Eviction for Large Models

## Problem

CI builds were failing with:
```
ERROR: remote cache evicted: Lost inputs no longer available remotely:
models/qwen3_30b_a3b_awq_amd64/blobs/sha256/181ab3a... (5GB+)
```

### Root Cause

The Qwen3-30B-A3B-AWQ model has 4 safetensors weight files (~5GB each, ~16GB total).
When packaged as an OCI image:
- Each weight file creates a separate layer (for efficient caching)
- Layers are built for both amd64 and arm64 platforms
- This creates ~8 large OCI layer blobs in BuildBuddy's remote cache
- BuildBuddy evicts large blobs due to LRU cache policies
- CI fails when trying to build/push the model and cached layers are missing

## Solution

**Exclude large models from `//images:push_all` in CI.**

### Changes Made

1. **Tagged qwen3 model as "manual"** (`models/BUILD`)
   - Prevents accidental inclusion in bulk operations
   - Model can still be pushed manually: `bazel run //models:qwen3_30b_a3b_awq.push`

2. **Added tag support to model packaging rules** (`models/internal/*.bzl`)
   - `safetensors_image()` and `gguf_image()` now accept `tags` parameter
   - Tags propagate to all generated targets (oci_image, oci_push, pkg_tar, etc.)

3. **Disabled remote cache for Tar actions in CI** (`.bazelrc`)
   - Added `build:ci --modify_execution_info=Tar=+no-remote-cache`
   - Prevents remote cache eviction for ALL Tar operations during CI builds
   - Local builds still benefit from Tar caching

4. **Excluded large models from push_all** (`scripts/generate-push-all.sh`)
   - Added grep filter to exclude qwen3_30b_a3b_awq.push
   - Small models (<1GB) continue to push in CI without issues

5. **Regenerated images/BUILD**
   - push_all now contains 12 targets instead of 13
   - qwen3 model excluded

### Trade-offs

**Before:** All models pushed in CI, but large model failures blocked entire pipeline

**After:**
- Small models (<1GB): Push in CI automatically ✅
- Large models (>1GB): Push manually when needed ✅
- CI unblocked from cache eviction issues ✅

### Manual Push Workflow for Large Models

When you need to push the qwen3 model:

```bash
# Build and push manually
bazel run //models:qwen3_30b_a3b_awq.push

# Or via local development (uses local Bazel cache, no remote cache issues)
```

## Long-term Solutions (Future Work)

1. **Hybrid storage approach** (recommended by cache-researcher agent):
   - Store model configs/metadata in OCI images (Bazel-built)
   - Store large weight files in GHCR or object storage
   - Download weights at container runtime via init container

2. **Increase BuildBuddy cache retention**:
   - Configure larger cache size (100GB+ instead of default)
   - Longer TTL for large artifacts
   - Enable compression for network efficiency

3. **Use --distdir for CI**:
   - Pre-populate large model files in shared storage
   - BuildBuddy runners mount this directory
   - Avoids re-downloads and cache eviction

## Testing

Verify the fix:

```bash
# Check that push_all excludes qwen3 by inspecting generated BUILD file
grep qwen images/BUILD

# Should see:
#   "//models:qwen2_5_0_5b_gguf.push",
#   "//models:qwen2_5_0_5b_st.push",
# But NOT:
#   "//models:qwen3_30b_a3b_awq.push",

# Verify qwen3 can still be pushed manually
bazel run //models:qwen3_30b_a3b_awq.push --config=ci

# Verify Tar operations skip remote cache in CI
bazel build //models:qwen3_30b_a3b_awq --config=ci --explain=explain.log
grep "no-remote-cache" explain.log
```

## References

- BuildBuddy invocation: https://app.buildbuddy.io/invocation/872ceb0e-5151-46ff-9e0e-830b5b306c7c
- Original error: Remote cache evicted 5GB+ OCI layer blobs
- Related PR: #357 (added qwen3 model originally)
