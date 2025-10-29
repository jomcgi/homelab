#!/usr/bin/env bash
# scripts/update-argocd-snapshot.sh
# Incrementally update ArgoCD snapshot from previous version

set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/jomcgi}"
IMAGE_NAME="${IMAGE_NAME:-argocd-preview}"
BASE_TAG="${BASE_TAG:-latest}"
NEW_TAG="${NEW_TAG:-$(git rev-parse --short HEAD)}"
CONTAINER_NAME="argocd-snapshot-update-$$"

cleanup() {
  echo "🧹 Cleaning up..."
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

echo "📦 Incremental ArgoCD Snapshot Update"
echo "Base: $REGISTRY/$IMAGE_NAME:$BASE_TAG"
echo "New:  $REGISTRY/$IMAGE_NAME:$NEW_TAG"
echo ""

# Check if base snapshot exists locally
if ! docker images "$REGISTRY/$IMAGE_NAME:$BASE_TAG" --format "{{.Repository}}:{{.Tag}}" | grep -q "$BASE_TAG"; then
  echo "📥 Pulling base snapshot..."
  docker pull "$REGISTRY/$IMAGE_NAME:$BASE_TAG" || {
    echo "❌ Base snapshot not found. Creating from scratch..."
    exec "$(dirname "$0")/create-argocd-snapshot.sh"
  }
fi

echo "🚀 Starting from base snapshot..."
docker run -d \
  --privileged \
  --name "$CONTAINER_NAME" \
  --hostname argocd-snapshot \
  "$REGISTRY/$IMAGE_NAME:$BASE_TAG"

# Wait for Kubernetes API
echo "⏳ Waiting for Kubernetes API..."
for i in {1..30}; do
  if docker exec "$CONTAINER_NAME" kubectl get --raw /healthz &>/dev/null; then
    break
  fi
  sleep 1
done

echo "✅ Cluster ready from snapshot"

# Check ArgoCD version in chart vs installed
CHART_VERSION=$(yq '.appVersion' charts/argocd/Chart.yaml 2>/dev/null || echo "unknown")
INSTALLED_VERSION=$(docker exec "$CONTAINER_NAME" kubectl get deployment argocd-server -n argocd -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | grep -oP 'v\K[0-9.]+' || echo "unknown")

echo ""
echo "ArgoCD versions:"
echo "  Installed: $INSTALLED_VERSION"
echo "  Chart:     $CHART_VERSION"

# Update ArgoCD if version changed
if [[ "$CHART_VERSION" != "unknown" && "$CHART_VERSION" != "$INSTALLED_VERSION" ]]; then
  echo ""
  echo "📦 Updating ArgoCD to $CHART_VERSION..."
  docker exec "$CONTAINER_NAME" kubectl apply -n argocd \
    -f https://raw.githubusercontent.com/argoproj/argo-cd/v${CHART_VERSION}/manifests/install.yaml

  echo "⏳ Waiting for rollout..."
  docker exec "$CONTAINER_NAME" kubectl rollout status -n argocd deployment/argocd-server --timeout=120s
else
  echo "✅ ArgoCD version up to date"
fi

# Optional: Pre-load Helm charts to warm cache
if [[ "${PRELOAD_CHARTS:-false}" == "true" ]]; then
  echo ""
  echo "🎯 Pre-loading Helm charts to warm cache..."

  # Find all Chart.yaml files and add repos
  for chart in charts/*/Chart.yaml; do
    if [[ -f "$chart" ]]; then
      chart_dir=$(dirname "$chart")
      echo "  Loading $chart_dir..."

      # Extract dependencies and add repos
      if [[ -f "$chart_dir/Chart.lock" ]]; then
        docker exec "$CONTAINER_NAME" helm repo add --force-update \
          $(yq '.dependencies[].repository' "$chart_dir/Chart.yaml" 2>/dev/null | grep -v '^file:' | head -1) \
          2>/dev/null || true
      fi
    fi
  done

  docker exec "$CONTAINER_NAME" helm repo update 2>/dev/null || true
fi

# Optional: Apply Applications to render them once (warms ArgoCD cache)
if [[ "${APPLY_APPS:-false}" == "true" ]]; then
  echo ""
  echo "🎯 Applying Applications to warm ArgoCD cache..."

  for app in overlays/*/*/application.yaml; do
    if [[ -f "$app" ]]; then
      app_name=$(yq '.metadata.name' "$app")
      echo "  Applying $app_name..."
      docker cp "$app" "$CONTAINER_NAME:/tmp/app.yaml"
      docker exec "$CONTAINER_NAME" kubectl apply -f /tmp/app.yaml || true
    fi
  done

  # Wait a moment for ArgoCD to process
  sleep 5
fi

echo ""
echo "📸 Committing updated snapshot..."
docker commit "$CONTAINER_NAME" "$REGISTRY/$IMAGE_NAME:$NEW_TAG"

# Tag as latest
docker tag "$REGISTRY/$IMAGE_NAME:$NEW_TAG" "$REGISTRY/$IMAGE_NAME:latest"

# Also tag with timestamp for history
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
docker tag "$REGISTRY/$IMAGE_NAME:$NEW_TAG" "$REGISTRY/$IMAGE_NAME:$TIMESTAMP"

echo ""
echo "✅ Snapshot updated successfully!"
echo ""
echo "Tags created:"
echo "  - $REGISTRY/$IMAGE_NAME:$NEW_TAG"
echo "  - $REGISTRY/$IMAGE_NAME:latest"
echo "  - $REGISTRY/$IMAGE_NAME:$TIMESTAMP"
echo ""
echo "Image sizes:"
docker images "$REGISTRY/$IMAGE_NAME" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | head -4
echo ""

if [[ "${PUSH:-false}" == "true" ]]; then
  echo "🚀 Pushing to registry..."
  docker push "$REGISTRY/$IMAGE_NAME:$NEW_TAG"
  docker push "$REGISTRY/$IMAGE_NAME:latest"
  docker push "$REGISTRY/$IMAGE_NAME:$TIMESTAMP"
  echo "✅ Pushed to $REGISTRY/$IMAGE_NAME"
else
  echo "To push to registry, run:"
  echo "  docker push $REGISTRY/$IMAGE_NAME:$NEW_TAG"
  echo "  docker push $REGISTRY/$IMAGE_NAME:latest"
fi
