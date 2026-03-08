#!/usr/bin/env bash
# rules_helm/render-manifests.sh
# Render Helm manifests from ArgoCD Application spec

set -euo pipefail

# Use Bazel-provided helm binary if available
HELM_BIN="${HELM:-helm}"

# Add common tool locations to PATH for fallback
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Required env vars set by Bazel
CHART_PATH="${CHART_PATH:-}"
RELEASE_NAME="${RELEASE_NAME:-}"
NAMESPACE="${NAMESPACE:-default}"
OUTPUT_FILE="${OUTPUT_FILE:-manifests/all.yaml}"

# Optional: Space-separated list of values files
VALUES_FILES="${VALUES_FILES:-}"

if [ -z "$CHART_PATH" ]; then
	echo "❌ Error: CHART_PATH not set"
	exit 1
fi

if [ -z "$RELEASE_NAME" ]; then
	echo "❌ Error: RELEASE_NAME not set"
	exit 1
fi

# Get the repository root
REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
	echo "❌ Error: Cannot determine repository root"
	exit 1
fi

# Check if helm CLI is available
if ! command -v "$HELM_BIN" &>/dev/null; then
	echo "❌ Error: helm CLI not found"
	exit 1
fi

echo "📦 Rendering Helm manifests"
echo "   Chart: $CHART_PATH"
echo "   Release: $RELEASE_NAME"
echo "   Namespace: $NAMESPACE"
echo ""

# Build helm template command
HELM_CMD=("$HELM_BIN" template "$RELEASE_NAME" "$REPO_ROOT/$CHART_PATH" --namespace "$NAMESPACE")

# Add values files
if [ -n "$VALUES_FILES" ]; then
	for vf in $VALUES_FILES; do
		if [ -f "$REPO_ROOT/$vf" ]; then
			echo "   Values: $vf"
			HELM_CMD+=(--values "$REPO_ROOT/$vf")
		else
			echo "⚠️  Warning: Values file not found: $vf"
		fi
	done
fi

echo ""
echo "🔨 Running: ${HELM_CMD[*]}"
echo ""

# Create output directory
OUTPUT_DIR=$(dirname "$REPO_ROOT/$OUTPUT_FILE")
mkdir -p "$OUTPUT_DIR"

# Run helm template and write to output file
"${HELM_CMD[@]}" >"$REPO_ROOT/$OUTPUT_FILE"

echo "✅ Manifests written to: $OUTPUT_FILE"
echo ""
echo "📊 Summary:"
echo "   Total resources: $(grep -c '^kind:' "$REPO_ROOT/$OUTPUT_FILE" || echo 0)"
echo "   File size: $(du -h "$REPO_ROOT/$OUTPUT_FILE" | cut -f1)"
