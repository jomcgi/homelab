#!/usr/bin/env bash
# scripts/create-argocd-snapshot.sh
# Creates a Docker snapshot of a Kind cluster with ArgoCD pre-installed

set -euo pipefail

# Use Bazel-provided kind binary if available, otherwise fall back to system kind
KIND_BIN="${KIND:-kind}"

# Add common tool locations to PATH for podman/kubectl
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Detect container runtime (docker or podman)
if command -v docker &>/dev/null; then
	CONTAINER_CMD="docker"
elif command -v podman &>/dev/null; then
	CONTAINER_CMD="podman"
	# Check if podman machine is running (required on macOS)
	if ! podman machine list --format json 2>/dev/null | grep -q '"Running": true'; then
		echo "❌ Error: Podman machine is not running"
		echo ""
		echo "Please start the podman machine with:"
		echo "  podman machine start"
		echo ""
		exit 1
	fi
else
	echo "❌ Error: Neither docker nor podman found"
	exit 1
fi

echo "Using container runtime: $CONTAINER_CMD"

SNAPSHOT_TAG="${SNAPSHOT_TAG:-homelab/argocd-preview:latest}"
CLUSTER_NAME="argocd-snapshot-temp"

# Clean up any existing cluster with the same name
if "$KIND_BIN" get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
	echo "🧹 Cleaning up existing cluster..."
	"$KIND_BIN" delete cluster --name "$CLUSTER_NAME"
fi

echo "🏗️  Creating temporary Kind cluster..."
"$KIND_BIN" create cluster --name "$CLUSTER_NAME" --wait 2m

echo "📦 Installing ArgoCD..."
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "⏳ Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s \
	deployment/argocd-server -n argocd

# Get the Kind container name
CONTAINER_NAME="${CLUSTER_NAME}-control-plane"

echo "📸 Creating container snapshot..."
"$CONTAINER_CMD" commit "$CONTAINER_NAME" "$SNAPSHOT_TAG"

echo "🧹 Cleaning up temporary cluster..."
"$KIND_BIN" delete cluster --name "$CLUSTER_NAME"

echo ""
echo "✅ Snapshot created: $SNAPSHOT_TAG"
echo ""
echo "Image size:"
"$CONTAINER_CMD" images "$SNAPSHOT_TAG" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
echo ""
echo "Usage:"
echo "  # Start from snapshot"
echo "  $CONTAINER_CMD run -d --privileged --name argocd-preview $SNAPSHOT_TAG"
echo ""
echo "  # Access ArgoCD"
echo "  kubectl --context kind-argocd-preview get svc -n argocd"
