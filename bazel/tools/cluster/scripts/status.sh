#!/usr/bin/env bash
set -euo pipefail

# Cluster overview: node status, namespace summary, key resource counts.
# Read-only: uses only kubectl get commands.

if ! command -v kubectl &>/dev/null; then
	echo "ERROR: kubectl not found in PATH" >&2
	exit 1
fi

echo "=== Cluster Status Overview ==="
echo ""

echo "--- Nodes ---"
kubectl get nodes -o wide 2>/dev/null
echo ""

echo "--- Namespace Summary ---"
kubectl get namespaces --no-headers 2>/dev/null | while IFS= read -r line; do
	echo "  $line"
done
echo ""

echo "--- Resource Counts ---"
pods_total=$(kubectl get pods -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
pods_running=$(kubectl get pods -A --no-headers --field-selector=status.phase=Running 2>/dev/null | wc -l | tr -d ' ')
pods_failed=$(kubectl get pods -A --no-headers --field-selector=status.phase=Failed 2>/dev/null | wc -l | tr -d ' ')
deployments=$(kubectl get deployments -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
services=$(kubectl get services -A --no-headers 2>/dev/null | wc -l | tr -d ' ')

echo "  Pods:        $pods_total total, $pods_running running, $pods_failed failed"
echo "  Deployments: $deployments"
echo "  Services:    $services"
echo ""

echo "--- Storage (Longhorn) ---"
(kubectl get volumes.longhorn.io -n longhorn-system --no-headers 2>/dev/null || true) | while IFS= read -r line; do
	echo "  $line"
done || echo "  (Longhorn volumes not available)"
echo ""
