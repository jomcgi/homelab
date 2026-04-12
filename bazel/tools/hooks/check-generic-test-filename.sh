#!/bin/bash
# PreToolUse hook: warns when writing a test file with a generic or vague name.
#
# Generic names like coverage_test.py, gaps_test.go, remaining_test.go, or
# new_service_test.go don't describe what they test. Files should be named
# after the module or feature under test (e.g., auth_test.go, parser_test.py).
#
# Triggers on Write or Edit tool calls where file_path ends in _test.py or
# _test.go and the basename matches a known vague-name pattern.
#
# Flagged patterns (case-insensitive match in basename):
#   coverage, gaps, remaining, final_, new_, identified
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)

set -euo pipefail

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Only inspect test files
case "$FILE_PATH" in
*_test.py | *_test.go) ;;
*) exit 0 ;;
esac

BASENAME=$(basename "$FILE_PATH")

# Check for generic / vague keyword in the filename
if echo "$BASENAME" | grep -qiE '(coverage|gaps|remaining|final_|new_|identified)'; then
	cat >&2 <<-EOF
		WARNING: Generic test file name detected: "${BASENAME}"
		Vague names like coverage_test.py, gaps_test.go, or remaining_test.go
		make it unclear what is being tested. Name the file after the module or
		feature under test instead (e.g., auth_test.go, payment_processor_test.py).
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
