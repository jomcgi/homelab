#!/usr/bin/env bash
set -euo pipefail

# Show recent cluster events sorted by timestamp.
# Read-only: uses only kubectl get commands.

if ! command -v kubectl &>/dev/null; then
	echo "ERROR: kubectl not found in PATH" >&2
	exit 1
fi

echo "=== Recent Cluster Events ==="
echo ""
kubectl get events -A --sort-by='.lastTimestamp' 2>/dev/null | tail -50
