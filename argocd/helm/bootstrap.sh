#!/bin/bash
set -e

echo "🚀 Bootstrapping ArgoCD + 1Password with Helm..."

# Check if kubectl is configured
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "❌ kubectl is not configured or cluster is unreachable"
    exit 1
fi

# Add Helm repositories
echo "📦 Adding Helm repositories..."
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add 1password https://1password.github.io/connect-helm-charts
helm repo update

# Validate required environment variables
if [[ -z "${ONEPASSWORD_CONNECT_HOST}" || -z "${ONEPASSWORD_CONNECT_TOKEN}" ]]; then
    echo "❌ Missing required 1Password environment variables:"
    echo "   ONEPASSWORD_CONNECT_HOST"
    echo "   ONEPASSWORD_CONNECT_TOKEN"
    echo ""
    echo "Set these in your environment or GitHub Secrets before running."
    exit 1
fi

if [[ -z "${GITHUB_TOKEN}" ]]; then
    echo "❌ Missing GitHub Personal Access Token:"
    echo "   GITHUB_TOKEN"
    echo ""
    echo "Create a GitHub PAT with 'repo' scope and set it as an environment variable."
    exit 1
fi

# Install ArgoCD
echo "🎯 Installing ArgoCD..."
helm upgrade --install argocd argo/argo-cd \
    --namespace argocd \
    --create-namespace \
    --values argocd/values.yaml \
    --wait

# Wait for ArgoCD to be ready
echo "⏳ Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Configure GitHub repository access
echo "🔐 Configuring GitHub repository access..."
kubectl create secret generic homelab-repo-secret \
    --namespace argocd \
    --from-literal=url=https://github.com/jomcgi/homelab.git \
    --from-literal=username=jomcgi \
    --from-literal=password="${GITHUB_TOKEN}" \
    --dry-run=client -o yaml | kubectl apply -f -

# Label the secret for ArgoCD to recognize it
kubectl label secret homelab-repo-secret -n argocd argocd.argoproj.io/secret-type=repository

# Install 1Password Connect
echo "🔐 Installing 1Password Connect..."
helm upgrade --install onepassword-connect 1password/connect \
    --namespace onepassword \
    --create-namespace \
    --set connect.connectHost="${ONEPASSWORD_CONNECT_HOST}" \
    --set connect.connectToken="${ONEPASSWORD_CONNECT_TOKEN}" \
    --set operator.create=true \
    --wait

# Apply ApplicationSet and other ArgoCD configs
echo "📋 Applying ApplicationSet and configurations..."
kubectl apply -f argocd/apps/

# Get ArgoCD admin password
echo "🔑 Getting ArgoCD admin credentials..."
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)

echo ""
echo "🎉 Bootstrap complete!"
echo ""
echo "📋 Installed components:"
echo "  ✅ ArgoCD (namespace: argocd)"
echo "  ✅ 1Password Connect + Operator (namespace: onepassword)"
echo "  ✅ ApplicationSet for service discovery"
echo ""
echo "🌐 Access ArgoCD:"
echo "  kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "  URL: https://localhost:8080"
echo "  Username: admin"
echo "  Password: ${ARGOCD_PASSWORD}"
echo ""
echo "🔄 ArgoCD will now manage all services in cluster/services/*"