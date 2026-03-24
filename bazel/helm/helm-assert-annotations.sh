#!/usr/bin/env bash
# helm-assert-annotations.sh - Renders a Helm chart and asserts specific
# pod template annotations are present in the rendered output.
#
# Usage: helm-assert-annotations.sh <helm> <release> <chart> <namespace> [key:value ...]
#
# Each annotation argument should be KEY:VALUE. The script checks that the
# rendered output contains:  KEY: "VALUE"
#
# Exit code 0 = all assertions pass, non-zero = at least one assertion failed.

set -euo pipefail

if [[ $# -lt 4 ]]; then
	echo "Usage: $0 <helm-binary> <release-name> <chart-path> <namespace> [key:value ...]"
	exit 1
fi

HELM="$1"
RELEASE="$2"
CHART="$3"
NAMESPACE="$4"
shift 4

echo "Rendering chart for annotation assertions:"
echo "  Release:   $RELEASE"
echo "  Chart:     $CHART"
echo "  Namespace: $NAMESPACE"
echo ""

RENDERED=$("$HELM" template "$RELEASE" "$CHART" --namespace "$NAMESPACE")

FAILED=0
for assertion in "$@"; do
	KEY="${assertion%%:*}"
	VALUE="${assertion#*:}"
	if echo "$RENDERED" | grep -qF "${KEY}: \"${VALUE}\""; then
		echo "PASSED: ${KEY}: \"${VALUE}\" found in rendered output"
	else
		echo "FAILED: ${KEY}: \"${VALUE}\" NOT found in rendered output"
		echo "  This annotation is required for the pod to function correctly."
		FAILED=1
	fi
done

if [[ $FAILED -eq 0 ]]; then
	echo ""
	echo "All annotation assertions passed."
fi

exit $FAILED
