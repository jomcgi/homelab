#!/usr/bin/env bash
# helm-template-test.sh - Validates that a Helm chart renders successfully with given values
#
# Usage: helm-template-test.sh <helm-binary> <release-name> <chart-path> <namespace> [values-files...]
#
# This script is used by Bazel's helm_template_test rule to validate that
# Helm charts render without errors when combined with their values files.
# Exit code 0 = success, non-zero = rendering failed.

set -euo pipefail

if [[ $# -lt 4 ]]; then
	echo "Usage: $0 <helm-binary> <release-name> <chart-path> <namespace> [values-files...]"
	exit 1
fi

HELM="$1"
RELEASE_NAME="$2"
CHART_PATH="$3"
NAMESPACE="$4"
shift 4

# Build values arguments
VALUES_ARGS=()
for values_file in "$@"; do
	VALUES_ARGS+=("--values" "$values_file")
done

echo "Testing Helm template rendering:"
echo "  Release: $RELEASE_NAME"
echo "  Chart:   $CHART_PATH"
echo "  Namespace: $NAMESPACE"
echo "  Values:  $*"
echo ""

# Run helm template and discard output - we only care about exit code
# Errors will be printed to stderr
if "$HELM" template "$RELEASE_NAME" "$CHART_PATH" \
	--namespace "$NAMESPACE" \
	"${VALUES_ARGS[@]}" \
	>/dev/null; then
	echo "PASSED: Chart renders successfully"
	exit 0
else
	echo ""
	echo "FAILED: Chart rendering produced errors"
	exit 1
fi
