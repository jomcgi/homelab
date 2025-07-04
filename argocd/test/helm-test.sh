#!/bin/bash
set -e

echo "🧪 Testing ArgoCD + 1Password with Helm in minikube..."

# Start minikube if not running
if ! minikube status >/dev/null 2>&1; then
    echo "🚀 Starting minikube..."
    minikube start --memory=4096 --cpus=2 --disk-size=20g --driver=docker
fi

# Check if Helm is installed
if ! command -v helm &> /dev/null; then
    echo "📦 Installing Helm..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Add Helm repositories
echo "📦 Adding Helm repositories..."
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add 1password https://1password.github.io/connect-helm-charts
helm repo update

# Install ArgoCD
echo "🎯 Installing ArgoCD with Helm..."
helm upgrade --install argocd argo/argo-cd \
    --namespace argocd \
    --create-namespace \
    --values ../helm/argocd/values.yaml \
    --wait

# Wait for ArgoCD to be ready
echo "⏳ Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Test 1Password Connect (without real credentials)
echo "🔐 Testing 1Password Connect chart (dry-run)..."
helm template onepassword-connect 1password/connect \
    --namespace onepassword \
    --set connect.connectHost="http://test.local" \
    --set connect.connectToken="test-token" \
    --set operator.create=true \
    > /tmp/onepassword-test.yaml

echo "✅ 1Password template validation passed"

# Apply ApplicationSet
echo "📋 Applying ApplicationSet..."
kubectl apply -f ../apps/homelab-services.yaml

# Get ArgoCD admin password
echo "🔑 Getting ArgoCD admin credentials..."
ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)

echo ""
echo "🎉 Helm test complete!"
echo ""
echo "📋 Test results:"
echo "  ✅ ArgoCD installed via Helm"
echo "  ✅ 1Password chart validated"
echo "  ✅ ApplicationSet applied"
echo ""
echo "🌐 Access ArgoCD:"
echo "  kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "  Username: admin"
echo "  Password: ${ARGOCD_PASSWORD}"
echo ""
echo "🧹 Cleanup minikube cluster..."
read -p "Delete minikube cluster? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    minikube delete
    echo "✅ Minikube cluster deleted"
else
    echo "ℹ️  Minikube cluster preserved"
    echo "   Run 'minikube delete' to clean up manually"
fi