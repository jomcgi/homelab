#!/bin/bash
set -e

echo "🧹 Cleaning up old GitHub Actions workflows..."

# List of workflows to remove after ArgoCD migration
OLD_WORKFLOWS=(
    ".github/workflows/k8s-deploy-otel-collector.yaml"
    ".github/workflows/k8s-deploy-open-webui.yaml"
    ".github/workflows/k8s-deploy-obsidian-mcp.yaml"
    ".github/workflows/k8s-deploy-longhorn-crd.yaml"
    ".github/workflows/k8s-deploy-grafana-cloud.yaml"
    ".github/workflows/k8s-deploy-external-secrets-crd.yaml"
    ".github/workflows/k8s-deploy-cloudflare-tunnel.yaml"
)

echo "📋 Workflows to be removed:"
for workflow in "${OLD_WORKFLOWS[@]}"; do
    if [ -f "$workflow" ]; then
        echo "  ✅ $workflow"
    else
        echo "  ❌ $workflow (not found)"
    fi
done

echo ""
read -p "Are you sure you want to remove these workflows? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 1
fi

echo "🗑️  Removing old workflows..."
for workflow in "${OLD_WORKFLOWS[@]}"; do
    if [ -f "$workflow" ]; then
        rm "$workflow"
        echo "  ✅ Removed $workflow"
    fi
done

# Remove External Secrets CRD if it exists
if [ -f "cluster/crds/external-secrets-crd.yaml" ]; then
    echo "🗑️  Removing External Secrets CRD..."
    rm "cluster/crds/external-secrets-crd.yaml"
    echo "  ✅ Removed External Secrets CRD"
fi

echo ""
echo "🎉 Cleanup complete!"
echo "📋 Next steps:"
echo "  1. Commit these changes"
echo "  2. Push to trigger ArgoCD sync"
echo "  3. Verify all services are running via ArgoCD"
echo ""
echo "⚠️  Note: Keep the bootstrap-argocd.yaml workflow for future cluster setups"