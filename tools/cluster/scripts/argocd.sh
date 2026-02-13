#!/usr/bin/env bash
set -euo pipefail

# Show ArgoCD application sync status.
# Read-only: uses only kubectl get commands.

if ! command -v kubectl &>/dev/null; then
	echo "ERROR: kubectl not found in PATH" >&2
	exit 1
fi

echo "=== ArgoCD Application Status ==="
echo ""

if ! kubectl get namespace argocd &>/dev/null; then
	echo "ERROR: argocd namespace not found" >&2
	exit 1
fi

# Get all ArgoCD Applications with their sync and health status
kubectl get applications.argoproj.io -n argocd \
	-o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision' \
	2>/dev/null || echo "  (Could not retrieve ArgoCD applications)"
echo ""

# Show any out-of-sync applications
echo "--- Out-of-Sync Applications ---"
out_of_sync=$(kubectl get applications.argoproj.io -n argocd \
	--no-headers \
	-o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status' \
	2>/dev/null | grep -v "Synced" || true)

if [ -z "$out_of_sync" ]; then
	echo "  All applications are synced."
else
	echo "$out_of_sync" | while IFS= read -r line; do
		echo "  $line"
	done
fi
echo ""
