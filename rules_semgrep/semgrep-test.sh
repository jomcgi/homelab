#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep against source files with given rules
#
# Usage: semgrep-test.sh <semgrep-binary> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.

set -euo pipefail

if [[ $# -lt 3 ]]; then
	echo "Usage: $0 <semgrep-binary> <rule-files...> -- <source-files...>"
	exit 1
fi

SEMGREP="$1"
shift

# Collect rule files until we hit the -- separator
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	RULES+=("--config" "$1")
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and source files"
	exit 1
fi
shift # skip --

echo "Running semgrep scan:"
echo "  Rules: ${RULES[*]}"
echo "  Files: $*"
echo ""

if "$SEMGREP" "${RULES[@]}" --error --metrics=off --no-git-ignore "$@"; then
	echo "PASSED: No semgrep findings"
	exit 0
else
	echo ""
	echo "FAILED: Semgrep found violations"
	exit 1
fi
