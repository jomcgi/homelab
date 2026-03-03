#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep against source files with given rules
#
# Usage: semgrep-test.sh <semgrep-binary> <pysemgrep-binary> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.

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

# Collect rule files until we hit the -- separator
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	RULES+=("--config" "$(pwd)/$1")
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

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$SCAN_DIR"; then
	echo "PASSED: No semgrep findings"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations"
	exit 1
fi
