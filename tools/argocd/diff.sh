#!/usr/bin/env bash
# tools/argocd/diff.sh
# Fast ArgoCD diff using pre-built snapshot

set -euo pipefail

SNAPSHOT_IMAGE="${SNAPSHOT_IMAGE:-homelab/argocd-preview:latest}"
CONTAINER_NAME="argocd-preview-$$"
BASE_BRANCH="${1:-origin/main}"

cleanup() {
  echo "🧹 Cleaning up..."
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

# Check if snapshot exists
if ! docker images "$SNAPSHOT_IMAGE" --format "{{.Repository}}:{{.Tag}}" | grep -q "$SNAPSHOT_IMAGE"; then
  echo "❌ Snapshot image not found: $SNAPSHOT_IMAGE"
  echo ""
  echo "Create it with:"
  echo "  ./scripts/create-argocd-snapshot.sh"
  echo ""
  echo "Or use ephemeral mode (slower):"
  echo "  EPHEMERAL=1 $0"
  exit 1
fi

echo "🚀 Starting ArgoCD from snapshot..."
docker run -d \
  --privileged \
  --name "$CONTAINER_NAME" \
  --hostname argocd-preview \
  -p 8080:6443 \
  "$SNAPSHOT_IMAGE"

# Wait for API server (Kind container takes ~5s to be ready)
echo "⏳ Waiting for Kubernetes API..."
for i in {1..30}; do
  if docker exec "$CONTAINER_NAME" kubectl get --raw /healthz &>/dev/null; then
    break
  fi
  sleep 1
done

# Update kubeconfig to point to this container
docker exec "$CONTAINER_NAME" cat /etc/kubernetes/admin.conf > /tmp/argocd-preview-kubeconfig
export KUBECONFIG=/tmp/argocd-preview-kubeconfig

# Get ArgoCD URL
ARGOCD_URL="https://localhost:8080"

echo "🔍 Running ArgoCD diff preview..."
echo "   Base: $BASE_BRANCH"
echo "   Current: $(git rev-parse --abbrev-ref HEAD)"
echo ""

# Run argocd-diff-preview
docker run --rm \
  --network host \
  -v "$(pwd):/repo" \
  -v /tmp/argocd-preview-kubeconfig:/kubeconfig \
  -e KUBECONFIG=/kubeconfig \
  -w /repo \
  dagandersen/argocd-diff-preview:latest \
  --argocd-url "$ARGOCD_URL" \
  --argocd-insecure \
  --base "$BASE_BRANCH"

echo ""
echo "✅ Diff complete!"
