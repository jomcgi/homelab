#!/usr/bin/env bash
# Push all OCI images in parallel using Bazel query
set -euo pipefail

echo "🔍 Discovering all oci_push targets..."
PUSH_TARGETS=$(bazel query 'kind("oci_push", //...)' 2>/dev/null)

if [ -z "$PUSH_TARGETS" ]; then
  echo "❌ No oci_push targets found"
  exit 1
fi

echo "📦 Found $(echo "$PUSH_TARGETS" | wc -l) image(s) to push:"
echo "$PUSH_TARGETS" | sed 's/^/  - /'
echo ""

echo "🚀 Building push scripts..."
# shellcheck disable=SC2086
bazel build $PUSH_TARGETS

echo "🚢 Executing push scripts in parallel..."
# Run all push scripts in parallel using background jobs
pids=()
for target in $PUSH_TARGETS; do
  echo "  Pushing: $target"
  bazel run "$target" &
  pids+=($!)
done

# Wait for all background jobs to complete
failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=$((failed + 1))
  fi
done

if [ $failed -eq 0 ]; then
  echo "✅ All images pushed successfully"
else
  echo "❌ $failed image(s) failed to push"
  exit 1
fi
