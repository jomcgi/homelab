#!/usr/bin/env bash
# semgrep-manifest-test.sh - Renders Helm manifests and scans with semgrep
#
# Usage: semgrep-manifest-test.sh <semgrep> <pysemgrep> <helm> <release> <chart> <namespace> <rules...> -- <values-files...>
#
# Combines helm template rendering with semgrep scanning in a single test.
# Exit code 0 = no findings, non-zero = violations found or render failure.

set -euo pipefail

if [[ $# -lt 7 ]]; then
	echo "Usage: $0 <semgrep> <pysemgrep> <helm> <release> <chart> <namespace> <rules...> -- <values...>"
	exit 1
fi

SEMGREP="$1"
PYSEMGREP="$2"
HELM="$3"
RELEASE="$4"
CHART="$5"
NAMESPACE="$6"
shift 6

# osemgrep (native engine) execs pysemgrep at runtime — add it to PATH
export PATH="$(dirname "$PYSEMGREP"):$PATH"

# Collect rule files until -- separator
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	RULES+=("--config" "$1")
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and values files"
	exit 1
fi
shift # skip --

# Build values arguments
VALUES_ARGS=()
for vf in "$@"; do
	VALUES_ARGS+=("--values" "$vf")
done

# Render manifests to a temp file with .yaml extension (semgrep needs it)
MANIFESTS="${TEST_TMPDIR}/rendered-manifests.yaml"

echo "Rendering manifests:"
echo "  Release:   $RELEASE"
echo "  Chart:     $CHART"
echo "  Namespace: $NAMESPACE"
echo "  Values:    $*"

if ! "$HELM" template "$RELEASE" "$CHART" \
	--namespace "$NAMESPACE" \
	"${VALUES_ARGS[@]}" >"$MANIFESTS"; then
	echo "FAILED: Helm template rendering failed"
	exit 1
fi

echo ""
echo "Scanning rendered manifests with semgrep:"
echo "  Rules: ${RULES[*]}"
echo ""

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$MANIFESTS"; then
	echo "PASSED: No semgrep findings in rendered manifests"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations in rendered manifests"
	exit 1
fi
