#!/usr/bin/env bash
# scripts/create-argocd-snapshot.sh
# Creates a Docker snapshot of a Kind cluster with ArgoCD pre-installed

set -euo pipefail

SNAPSHOT_TAG="${SNAPSHOT_TAG:-homelab/argocd-preview:latest}"
CLUSTER_NAME="argocd-snapshot-temp"

echo "🏗️  Creating temporary Kind cluster..."
kind create cluster --name "$CLUSTER_NAME" --wait 2m

echo "📦 Installing ArgoCD..."
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "⏳ Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s \
  deployment/argocd-server -n argocd

# Get the Kind container name
CONTAINER_NAME="${CLUSTER_NAME}-control-plane"

echo "📸 Creating Docker snapshot..."
docker commit "$CONTAINER_NAME" "$SNAPSHOT_TAG"

echo "🧹 Cleaning up temporary cluster..."
kind delete cluster --name "$CLUSTER_NAME"

echo ""
echo "✅ Snapshot created: $SNAPSHOT_TAG"
echo ""
echo "Image size:"
docker images "$SNAPSHOT_TAG" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
echo ""
echo "Usage:"
echo "  # Start from snapshot"
echo "  docker run -d --privileged --name argocd-preview $SNAPSHOT_TAG"
echo ""
echo "  # Access ArgoCD"
echo "  kubectl --context kind-argocd-preview get svc -n argocd"
