#!/usr/bin/env bash
# helm-assert-annotations.sh - Renders a Helm chart and asserts specific
# pod template annotations are present in the rendered output.
#
# Usage: helm-assert-annotations.sh <helm> <release> <chart> <namespace> [--set K=V ...] [key:value ...]
#
# Optional --set K=V flags (must come before annotation assertions) are forwarded
# to helm template so the chart can be rendered with non-default values.
#
# Each annotation argument should be KEY:VALUE. The script checks that the
# rendered output contains:  KEY: "VALUE"
#
# Exit code 0 = all assertions pass, non-zero = at least one assertion failed.

set -euo pipefail

if [[ $# -lt 4 ]]; then
	echo "Usage: $0 <helm-binary> <release-name> <chart-path> <namespace> [--set K=V ...] [key:value ...]"
	exit 1
fi

HELM="$1"
RELEASE="$2"
CHART="$3"
NAMESPACE="$4"
shift 4

# Collect optional --set K=V flags that precede annotation assertions.
SET_FLAGS=()
while [[ $# -gt 0 && "$1" == "--set" ]]; do
	SET_FLAGS+=("--set" "$2")
	shift 2
done

echo "Rendering chart for annotation assertions:"
echo "  Release:   $RELEASE"
echo "  Chart:     $CHART"
echo "  Namespace: $NAMESPACE"
if [[ ${#SET_FLAGS[@]} -gt 0 ]]; then
	echo "  Set flags: ${SET_FLAGS[*]}"
fi
echo ""

RENDERED=$("$HELM" template "$RELEASE" "$CHART" --namespace "$NAMESPACE" "${SET_FLAGS[@]+"${SET_FLAGS[@]}"}")

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
