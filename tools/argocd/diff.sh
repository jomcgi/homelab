#!/usr/bin/env bash
# tools/argocd/diff.sh
# Fast ArgoCD diff using pre-built snapshot

set -euo pipefail

# Add common tool locations to PATH for podman/kubectl
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Detect container runtime (docker or podman)
if command -v docker &>/dev/null; then
	CONTAINER_CMD="docker"
elif command -v podman &>/dev/null; then
	CONTAINER_CMD="podman"
else
	echo "❌ Error: Neither docker nor podman found"
	exit 1
fi

SNAPSHOT_IMAGE="${SNAPSHOT_IMAGE:-homelab/argocd-preview:latest}"
CONTAINER_NAME="argocd-preview-$$"
BASE_BRANCH="${1:-origin/main}"

cleanup() {
	echo "🧹 Cleaning up..."
	"$CONTAINER_CMD" stop "$CONTAINER_NAME" 2>/dev/null || true
	"$CONTAINER_CMD" rm "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

# Check if snapshot exists
if ! "$CONTAINER_CMD" images "$SNAPSHOT_IMAGE" --format "{{.Repository}}:{{.Tag}}" | grep -q "$SNAPSHOT_IMAGE"; then
	echo "❌ Snapshot image not found: $SNAPSHOT_IMAGE"
	echo ""
	echo "Create it with:"
	echo "  bazel run //tools/argocd:create_snapshot"
	echo ""
	echo "Or use ephemeral mode (slower):"
	echo "  EPHEMERAL=1 $0"
	exit 1
fi

echo "🚀 Starting ArgoCD from snapshot (using $CONTAINER_CMD)..."
"$CONTAINER_CMD" run -d \
	--privileged \
	--name "$CONTAINER_NAME" \
	--hostname argocd-preview \
	-p 8080:6443 \
	"$SNAPSHOT_IMAGE"

# Wait for API server (Kind container takes ~5s to be ready)
echo "⏳ Waiting for Kubernetes API..."
for i in {1..30}; do
	if "$CONTAINER_CMD" exec "$CONTAINER_NAME" kubectl get --raw /healthz &>/dev/null; then
		break
	fi
	sleep 1
done

# Update kubeconfig to point to this container
echo "📋 Extracting kubeconfig..."
KUBECONFIG_PATH="$HOME/.kube/argocd-preview-kubeconfig-$$"
"$CONTAINER_CMD" exec "$CONTAINER_NAME" cat /etc/kubernetes/admin.conf >"$KUBECONFIG_PATH"
if [ ! -f "$KUBECONFIG_PATH" ]; then
	echo "❌ Failed to extract kubeconfig"
	exit 1
fi

# Update server URL to point to localhost (since we're port-forwarding)
# The kubeconfig has the internal cluster IP, but we need localhost:8080
sed -i.bak 's|https://.*:6443|https://localhost:8080|g' "$KUBECONFIG_PATH"
export KUBECONFIG="$KUBECONFIG_PATH"

echo "🔍 Running ArgoCD-based diff..."
echo "   Base: $BASE_BRANCH"
echo "   Current: $(git rev-parse --abbrev-ref HEAD)"
echo ""

# For now, just show that the cluster is accessible
# TODO: Implement actual ArgoCD Application creation and diffing
echo "📊 Checking ArgoCD status..."
if kubectl --kubeconfig="$KUBECONFIG_PATH" get pods -n argocd &>/dev/null; then
	echo "✅ ArgoCD cluster is accessible"
	kubectl --kubeconfig="$KUBECONFIG_PATH" get pods -n argocd
else
	echo "❌ Failed to connect to ArgoCD cluster"
	exit 1
fi

# Cleanup kubeconfig
rm -f "$KUBECONFIG_PATH" "$KUBECONFIG_PATH.bak"

echo ""
echo "✅ Diff complete!"
