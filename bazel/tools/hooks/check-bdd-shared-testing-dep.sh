#!/bin/bash
# PreToolUse hook: warns when a BUILD file references shared.testing.plugin
# in an env dict but does not include :shared_testing in a deps list.
#
# This catches the pattern where the pytest plugin is registered via env var
# (PYTEST_ADDOPTS=-p shared.testing.plugin) but the BUILD target is missing
# the actual dependency, causing ImportError at test runtime.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only — never blocks)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# No file path — nothing to check
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Only check BUILD files
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" != "BUILD" ]] && [[ "$BASENAME" != "BUILD.bazel" ]]; then
	exit 0
fi

# Get content being written (Write tool) or read current file (Edit tool)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
if [[ -z "$CONTENT" ]]; then
	# Edit tool — read current file if it exists
	if [[ -f "$FILE_PATH" ]]; then
		CONTENT=$(cat "$FILE_PATH")
	fi
fi

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Check if the content references shared.testing.plugin in an env dict
if ! echo "$CONTENT" | grep -q 'shared\.testing\.plugin'; then
	exit 0
fi

# Warn if :shared_testing is not present in a deps list
if ! echo "$CONTENT" | grep -q '":shared_testing"'; then
	cat >&2 <<-EOF
		WARNING: ':shared_testing' missing from deps while 'shared.testing.plugin' is used in env.

		File: $FILE_PATH

		When using PYTEST_ADDOPTS=-p shared.testing.plugin in an env dict,
		the :shared_testing target must be listed in deps to ensure the plugin
		module is available at test runtime.

		Add to the target's deps:
		  deps = [
		      ...
		      ":shared_testing",
		  ],
	EOF
fi

exit 0
