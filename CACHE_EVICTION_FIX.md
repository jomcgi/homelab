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

**Disable remote caching for Tar operations in CI** to prevent BuildBuddy from evicting large model layers.

### Changes Made

1. **Disabled remote cache for Tar actions in CI** (`.bazelrc`)
   - Added `build:ci --modify_execution_info=Tar=+no-remote-cache`
   - Prevents BuildBuddy from caching large model tarballs remotely
   - ALL Tar operations in CI use local-only caching
   - Local builds still benefit from full remote + local Tar caching

2. **Simplified model BUILD file** (`models/BUILD`)
   - Removed "manual" tag from qwen3 model
   - Model now builds and pushes automatically in CI via `//images:push_all`
   - Updated comments to clarify .bazelrc is the mechanism, not tags

3. **Regenerated images/BUILD**
   - push_all now contains 13 targets including qwen3_30b_a3b_awq.push
   - All models push automatically in CI ✅

### Trade-offs

**Before:** All models pushed in CI, large model failures blocked entire pipeline

**After:**
- ✅ All models (small and large) push automatically in CI
- ✅ No cache eviction failures
- ✅ Local builds still use full remote cache
- ⚠️ CI Tar operations are local-only (no remote cache reuse)

The CI performance impact is minimal because:
- Small model tarballs build quickly (seconds)
- Large model tarballs would likely be evicted anyway
- We avoid build failures completely

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
# Check that push_all includes qwen3 by inspecting generated BUILD file
grep qwen images/BUILD

# Should see ALL qwen models:
#   "//models:qwen2_5_0_5b_gguf.push",
#   "//models:qwen2_5_0_5b_st.push",
#   "//models:qwen3_30b_a3b_awq.push",

# Verify .bazelrc configuration is active
bazel build //models:qwen3_30b_a3b_awq --config=ci --announce_rc 2>&1 | grep modify_execution_info
# Should show: --modify_execution_info=Tar=+no-remote-cache

# Verify Tar operations skip remote cache in CI
bazel build //models:qwen3_30b_a3b_awq --config=ci --explain=explain.log
grep "no-remote-cache" explain.log
```

## References

- BuildBuddy invocation: https://app.buildbuddy.io/invocation/872ceb0e-5151-46ff-9e0e-830b5b306c7c
- Original error: Remote cache evicted 5GB+ OCI layer blobs
- Related PR: #357 (added qwen3 model originally)
