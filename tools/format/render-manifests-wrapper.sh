#!/usr/bin/env bash
# Wrapper script to build all Helm manifests with Bazel caching
set -euo pipefail

echo "🔨 Rendering all Helm manifests (with caching)..."
bazel build //tools/argocd-parallel:render_all_parallel

echo "📋 Copying manifests from bazel-bin to source tree..."

# Get the actual bazel-bin path (works even in sandboxed environments)
BAZEL_BIN="$(bazel info bazel-bin 2>/dev/null)"

# Find all generated manifest files and copy them back to source
find "$BAZEL_BIN/overlays" -name "all.yaml" -path "*/manifests/all.yaml" 2>/dev/null | while read -r src; do
	# Convert bazel-bin/overlays/... to overlays/...
	dst="${src#$BAZEL_BIN/}"

	# Ensure destination directory exists
	mkdir -p "$(dirname "$dst")"

	# Copy the file (remove destination first if it exists, since Bazel outputs are read-only)
	rm -f "$dst"
	cp "$src" "$dst"
	chmod 644 "$dst"
	echo "  ✓ $dst"
done

echo "✅ All manifests rendered and copied!"
