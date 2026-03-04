#!/usr/bin/env bash
# semgrep-manifest-test.sh - Renders Helm manifests and scans with semgrep
#
# Usage: semgrep-manifest-test.sh <semgrep> <pysemgrep> <helm> <release> <chart> <namespace> <rules...> -- <values-files...>
#
# Combines helm template rendering with semgrep scanning in a single test.
# Exit code 0 = no findings, non-zero = violations found or render failure.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated rule IDs to skip (matched against YAML filename)
#      SEMGREP_PRO_ENGINE     — path to semgrep-core-proprietary binary; enables --pro

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

# Set up pro engine if available — semgrep looks for semgrep-core-proprietary
# next to semgrep-core. We use SEMGREP_CORE_BIN to redirect both to a temp dir.
PRO_FLAG=""
if [[ -n "${SEMGREP_PRO_ENGINE:-}" ]]; then
	SEMGREP_CORE=$(find . -name "semgrep-core" -not -name "*proprietary*" -type f 2>/dev/null | head -1)
	if [[ -z "$SEMGREP_CORE" ]]; then
		echo "ERROR: SEMGREP_PRO_ENGINE is set but semgrep-core binary was not found in sandbox"
		exit 1
	fi
	PRO_DIR="${TEST_TMPDIR}/pro_bin"
	mkdir -p "$PRO_DIR"
	cp "$SEMGREP_CORE" "$PRO_DIR/semgrep-core"
	chmod 755 "$PRO_DIR/semgrep-core"
	cp "$SEMGREP_PRO_ENGINE" "$PRO_DIR/semgrep-core-proprietary"
	chmod 755 "$PRO_DIR/semgrep-core-proprietary"
	export SEMGREP_CORE_BIN="$PRO_DIR/semgrep-core"
	PRO_FLAG="--pro"
fi

# Build comma-delimited exclude string for simple substring matching
EXCLUDE_LIST=",${SEMGREP_EXCLUDE_RULES:-},"

# Collect rule files until -- separator, skipping excluded rules
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	rule_name="$(basename "$1" .yaml)"
	if [[ "$EXCLUDE_LIST" != *",$rule_name,"* ]]; then
		RULES+=("--config" "$1")
	fi
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
echo "  Rules: ${RULES[*]:-none}"
echo ""

if [[ ${#RULES[@]} -eq 0 ]]; then
	echo "PASSED: All rules excluded, nothing to scan"
	exit 0
fi

if "$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore "$MANIFESTS"; then
	echo "PASSED: No semgrep findings in rendered manifests"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations in rendered manifests"
	exit 1
fi
