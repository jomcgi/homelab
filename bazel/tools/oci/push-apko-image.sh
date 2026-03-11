#!/usr/bin/env bash
# Temporary workaround to push multi-platform apko images
# Uses crane from Bazel with --index flag
#
# Usage: ./tools/oci/push-apko-image.sh <bazel-target> <repository:tag>
#
# Example:
#   ./tools/oci/push-apko-image.sh //charts/ttyd-session-manager/backend:ttyd_image ghcr.io/jomcgi/homelab/projects/ttyd-session-manager/ttyd:2025.01.01.00.00.00-abc1234

set -euo pipefail

if [ $# -ne 2 ]; then
	echo "Usage: $0 <bazel-target> <repository:tag>"
	echo "Example: $0 //charts/ttyd-session-manager/backend:ttyd_image ghcr.io/jomcgi/homelab/projects/ttyd-session-manager/ttyd:latest"
	exit 1
fi

TARGET="$1"
REPO_TAG="$2"

# Build the image
echo "Building $TARGET..."
bazel build "$TARGET"

# Find the OCI layout directory
IMAGE_DIR=$(bazel cquery "$TARGET" --output=files 2>/dev/null)

if [ ! -d "$IMAGE_DIR" ]; then
	echo "Error: Could not find image directory at $IMAGE_DIR"
	exit 1
fi

echo "Found image at: $IMAGE_DIR"

# Check if it's multi-platform
MANIFEST_COUNT=$(jq -r '.manifests | length' "$IMAGE_DIR/index.json")
echo "Image has $MANIFEST_COUNT platform(s)"

# Get crane from bazel - use the runfiles from image.push
echo "Finding crane binary..."
bazel build //charts/ttyd-session-manager/backend:image.push >/dev/null 2>&1

# Find crane in runfiles
PUSH_DIR="bazel-out/darwin_arm64-fastbuild/bin/charts/ttyd-session-manager/backend"
RUNFILES="$PUSH_DIR/push_image.push.sh.runfiles"

# crane is in rules_oci++oci+oci_crane_<arch>/crane
CRANE_BIN=$(find "$RUNFILES" -name crane -type l 2>/dev/null | head -1)

if [ -z "$CRANE_BIN" ] || [ ! -f "$CRANE_BIN" ]; then
	echo "Error: Could not find crane binary"
	echo "Tried: $RUNFILES"
	ls -la "$RUNFILES" 2>/dev/null || true
	exit 1
fi

# Resolve symlink
CRANE_BIN=$(readlink -f "$CRANE_BIN" 2>/dev/null || realpath "$CRANE_BIN")

echo "Using crane at: $CRANE_BIN"

# Push with --index flag for multi-platform
# Note: --index push doesn't use digest, it pushes to a tag
echo "Pushing $REPO_TAG..."
"$CRANE_BIN" push --index "$IMAGE_DIR" "$REPO_TAG"

echo "✓ Successfully pushed $REPO_TAG"
