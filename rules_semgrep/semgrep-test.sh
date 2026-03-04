#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep against source files with given rules
#
# Usage: semgrep-test.sh <semgrep-binary> <pysemgrep-binary> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated rule IDs to skip (matched against YAML filename)
# Env: SEMGREP_TEST_MODE — if set to "1", uses semgrep --test to validate rule
#      annotations (# ruleid: / # ok:) instead of scanning for violations
#      SEMGREP_PRO_ENGINE     — path to semgrep-core-proprietary binary; enables --pro
#      UPLOAD_SCRIPT          — path to upload binary; uploads results to Semgrep App

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

# Set up pro engine if available — semgrep looks for semgrep-core-proprietary
# next to semgrep-core. We use SEMGREP_CORE_BIN to redirect both to a temp dir.
# Graceful degradation: when the engine filegroup is empty (no token/digest),
# SEMGREP_PRO_ENGINE is empty → this block is skipped entirely.
PRO_FLAG=""
if [[ -n "${SEMGREP_PRO_ENGINE:-}" ]]; then
	if [[ ! -f "${SEMGREP_PRO_ENGINE}" ]]; then
		echo "INFO: Pro engine not available — running community analysis only"
	else
		SEMGREP_CORE=$(find . -name "semgrep-core" -not -name "*proprietary*" -type f 2>/dev/null | head -1)
		if [[ -z "$SEMGREP_CORE" ]]; then
			echo "INFO: semgrep-core not found — running community analysis only"
		else
			PRO_DIR="${TEST_TMPDIR}/pro_bin"
			mkdir -p "$PRO_DIR"
			cp "$SEMGREP_CORE" "$PRO_DIR/semgrep-core"
			chmod 755 "$PRO_DIR/semgrep-core"
			cp "$SEMGREP_PRO_ENGINE" "$PRO_DIR/semgrep-core-proprietary"
			chmod 755 "$PRO_DIR/semgrep-core-proprietary"
			export SEMGREP_CORE_BIN="$PRO_DIR/semgrep-core"
			PRO_FLAG="--pro"
		fi
	fi
fi

# Build comma-delimited exclude string for simple substring matching
EXCLUDE_LIST=",${SEMGREP_EXCLUDE_RULES:-},"

# Collect rule files until we hit the -- separator, skipping excluded rules
RULES=()
RULE_FILES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	rule_name="$(basename "$1" .yaml)"
	if [[ "$EXCLUDE_LIST" != *",$rule_name,"* ]]; then
		RULES+=("--config" "$(pwd)/$1")
		RULE_FILES+=("$1")
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

if [[ "${SEMGREP_TEST_MODE:-}" == "1" ]]; then
	# Test mode: validate # ruleid: / # ok: annotations in fixture files.
	# semgrep test requires rules and test files co-located in a single directory.
	TEST_DIR="${TEST_TMPDIR}/rule-test"
	mkdir -p "$TEST_DIR"
	for rf in "${RULE_FILES[@]}"; do
		cp "$(pwd)/$rf" "$TEST_DIR/"
	done
	for f in "$@"; do
		cp "$f" "$TEST_DIR/"
	done
	if "$SEMGREP" test "$TEST_DIR"; then
		echo "PASSED: All rule tests passed"
		exit 0
	else
		echo ""
		echo "FAILED: Rule test validation failed"
		exit 1
	fi
else
	SCAN_EXIT=0
	"$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore \
		--json --output "$TEST_TMPDIR/results.json" \
		"$SCAN_DIR" || SCAN_EXIT=$?

	# Best-effort upload (never affects exit code)
	if [[ -n "${SEMGREP_APP_TOKEN:-}" && -n "${UPLOAD_SCRIPT:-}" ]]; then
		"$UPLOAD_SCRIPT" "$TEST_TMPDIR/results.json" "$SCAN_EXIT" 2>&1 || true
	fi

	if [[ "$SCAN_EXIT" -eq 0 ]]; then
		echo "PASSED: No semgrep findings"
	else
		echo ""
		echo "FAILED: Semgrep found violations"
	fi
	exit "$SCAN_EXIT"
fi
