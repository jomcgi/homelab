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

**Exclude large models from CI `//images:push_all`** to prevent cache eviction from blocking the pipeline.

### Why .bazelrc Alone Isn't Sufficient

Initially attempted `.bazelrc` with `--modify_execution_info=Tar=+no-remote-cache`, but this **does not prevent cache eviction** because:

1. **Tar operations** create tarballs from source files → affected by `.bazelrc`
2. **OCI image rules** (rules_oci) process tarballs into layer blobs → NOT affected by `.bazelrc`
3. **OCI layer blobs** (5GB+ each) get cached remotely and evicted by BuildBuddy's LRU policy

The `.bazelrc` only affects `Tar` mnemonic actions. OCI layer blob creation uses different mnemonics from rules_oci, so those outputs still get remotely cached and evicted.

Broader .bazelrc exclusion (disabling remote cache for all OCI actions) would hurt CI performance for small images.

### Changes Made

1. **Exclude large models from push_all** (`scripts/generate-push-all.sh`)
   - Added grep filter to exclude `qwen3_30b_a3b_awq.push`
   - Prevents cache eviction from blocking CI pipeline

2. **Tagged qwen3 model as "manual"** (`models/BUILD`)
   - Documents exclusion intent
   - Explains why .bazelrc alone isn't sufficient

3. **Keep .bazelrc Tar exclusion** (`.bazelrc`)
   - Reduces cache pressure (defense in depth)
   - Not the primary solution, but helps

4. **Regenerated images/BUILD**
   - push_all contains 12 targets (qwen3 excluded)

### Trade-offs

**Before:** All models in CI, cache eviction blocked entire pipeline

**After:**
- ✅ Small models (<1GB): Auto-push in CI
- ✅ Large models (>1GB): Manual push when needed
- ✅ CI: Never blocked by cache eviction

### Manual Push

```bash
bazel run //models:qwen3_30b_a3b_awq.push
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
# Verify qwen3 is EXCLUDED from push_all
grep qwen images/BUILD

# Should see small models ONLY:
#   "//models:qwen2_5_0_5b_gguf.push",
#   "//models:qwen2_5_0_5b_st.push",
# Should NOT see:
#   "//models:qwen3_30b_a3b_awq.push",

# Verify qwen3 can still be pushed manually
bazel run //models:qwen3_30b_a3b_awq.push

# Verify CI push_all succeeds without cache eviction
bazel run //images:push_all --config=ci
```

## References

- BuildBuddy invocation: https://app.buildbuddy.io/invocation/872ceb0e-5151-46ff-9e0e-830b5b306c7c
- Original error: Remote cache evicted 5GB+ OCI layer blobs
- Related PR: #357 (added qwen3 model originally)
