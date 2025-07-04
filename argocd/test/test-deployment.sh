#!/bin/bash
set -e

echo "🧪 Testing ArgoCD deployment..."

# Check if ArgoCD is running
echo "Checking ArgoCD status..."
kubectl get pods -n argocd

# Check if ApplicationSet created applications
echo "Checking ApplicationSet applications..."
kubectl get applications -n argocd

# Check if services are being synced
echo "Checking application sync status..."
for app in $(kubectl get applications -n argocd -o jsonpath='{.items[*].metadata.name}'); do
    echo "📋 Application: $app"
    kubectl get application $app -n argocd -o jsonpath='{.status.sync.status}' || echo "N/A"
    echo ""
done

# Check for any failed applications
echo "Checking for failed applications..."
FAILED_APPS=$(kubectl get applications -n argocd -o jsonpath='{.items[?(@.status.health.status=="Degraded")].metadata.name}')
if [ -n "$FAILED_APPS" ]; then
    echo "❌ Failed applications: $FAILED_APPS"
    for app in $FAILED_APPS; do
        echo "🔍 Details for $app:"
        kubectl describe application $app -n argocd
    done
else
    echo "✅ No failed applications found"
fi

# Check if 1Password operator is running
echo "Checking 1Password operator status..."
kubectl get pods -n onepassword-operator || echo "1Password operator not deployed (expected for testing)"

# Summary
echo ""
echo "📊 Test Summary:"
echo "ArgoCD Pods:"
kubectl get pods -n argocd --no-headers | wc -l
echo "Applications:"
kubectl get applications -n argocd --no-headers | wc -l
echo "Healthy Applications:"
kubectl get applications -n argocd -o jsonpath='{.items[?(@.status.health.status=="Healthy")].metadata.name}' | wc -w

echo ""
echo "🎉 Test completed! Check the output above for any issues."