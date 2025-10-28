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

echo "🚀 Building and pushing all images in parallel..."
# shellcheck disable=SC2086
bazel build $PUSH_TARGETS

echo "✅ All images pushed successfully"
