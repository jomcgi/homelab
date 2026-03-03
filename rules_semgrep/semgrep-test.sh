#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep against source files with given rules
#
# Usage: semgrep-test.sh <semgrep-binary> <pysemgrep-binary> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated rule IDs to skip (matched against YAML filename)

set -euo pipefail

if [[ $# -lt 4 ]]; then
	echo "Usage: $0 <semgrep-binary> <pysemgrep-binary> <rule-files...> -- <source-files...>"
	exit 1
fi

SEMGREP="$1"
PYSEMGREP="$2"
shift 2

# osemgrep (native engine) execs pysemgrep at runtime — add it to PATH
export PATH="$(dirname "$PYSEMGREP"):$PATH"

# Build comma-delimited exclude string for simple substring matching
EXCLUDE_LIST=",${SEMGREP_EXCLUDE_RULES:-},"

# Collect rule files until we hit the -- separator, skipping excluded rules
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	rule_name="$(basename "$1" .yaml)"
	if [[ "$EXCLUDE_LIST" != *",$rule_name,"* ]]; then
		RULES+=("--config" "$(pwd)/$1")
	fi
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and source files"
	exit 1
fi
shift # skip --

# Copy source files to a temp directory — semgrep rejects Bazel sandbox symlinks
SCAN_DIR="${TEST_TMPDIR}/scan"
mkdir -p "$SCAN_DIR"
for f in "$@"; do
	mkdir -p "$SCAN_DIR/$(dirname "$f")"
	cp "$f" "$SCAN_DIR/$f"
done

if [[ ${#RULES[@]} -eq 0 ]]; then
	echo "PASSED: All rules excluded, nothing to scan"
	exit 0
fi

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$SCAN_DIR"; then
	echo "PASSED: No semgrep findings"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations"
	exit 1
fi
