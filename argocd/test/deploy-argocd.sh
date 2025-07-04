#!/bin/bash
set -e

echo "🚀 Deploying ArgoCD to minikube..."

# Apply ArgoCD bootstrap manifests
echo "Applying ArgoCD bootstrap manifests..."
kubectl apply -f ../bootstrap/argocd-namespace.yaml
kubectl apply -f ../bootstrap/argocd-operator.yaml

# Wait for ArgoCD operator to be ready
echo "Waiting for ArgoCD operator to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-operator-controller-manager -n argocd

# Apply ArgoCD instance
echo "Creating ArgoCD instance..."
kubectl apply -f ../bootstrap/argocd-install.yaml

# Wait for ArgoCD to be ready
echo "Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=600s deployment/argocd-server -n argocd

# Apply 1Password operator (without secrets for testing)
echo "Installing 1Password operator CRDs..."
kubectl apply -f ../operators/onepassword-crd.yaml

# Apply ApplicationSet (this will try to sync services)
echo "Applying ApplicationSet..."
kubectl apply -f ../apps/homelab-services.yaml
kubectl apply -f ../apps/kaniko-build-hook.yaml

# Get ArgoCD admin password
echo "🔑 Getting ArgoCD admin password..."
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)

# Port forward ArgoCD UI
echo "🌐 Starting port-forward to ArgoCD UI..."
echo "ArgoCD UI will be available at: http://localhost:8080"
echo "Username: admin"
echo "Password: $ARGOCD_PASSWORD"
echo ""
echo "Press Ctrl+C to stop port forwarding"

kubectl port-forward svc/argocd-server -n argocd 8080:443