#!/bin/bash
set -e

echo "🚀 Setting up minikube for ArgoCD testing..."

# Start minikube with sufficient resources
echo "Starting minikube..."
minikube start --memory=4096 --cpus=2 --disk-size=20g --driver=docker

# Enable required addons
echo "Enabling minikube addons..."
minikube addons enable ingress
minikube addons enable registry

# Apply ArgoCD CRDs (required for ArgoCD operator)
echo "Installing ArgoCD CRDs..."
kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/crds/application-crd.yaml
kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/crds/applicationset-crd.yaml
kubectl apply -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/crds/appproject-crd.yaml

# Install ArgoCD operator CRDs
echo "Installing ArgoCD operator CRDs..."
kubectl apply -f https://raw.githubusercontent.com/argoproj-labs/argocd-operator/master/deploy/crds/argoproj.io_argocds_crd.yaml

# Create namespaces
echo "Creating namespaces..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace onepassword-operator --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Minikube setup complete!"
echo "📋 Next steps:"
echo "   1. Run ./deploy-argocd.sh to install ArgoCD"
echo "   2. Run ./test-deployment.sh to verify everything works"