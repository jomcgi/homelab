#!/bin/bash
# PreToolUse hook: warns when editing the homelab-library Chart.yaml version field.
# After bumping the library version, run 'format' to propagate the change to all
# consuming charts via sync-helm-deps.sh.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning to stderr)
# Exit 2: block the operation (never used — warning only)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only fire for the homelab-library Chart.yaml
if [[ -z "$FILE_PATH" ]] || [[ "$FILE_PATH" != */homelab-library/chart/Chart.yaml ]]; then
	exit 0
fi

# For Edit tool: check if new_string contains a version line
NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
# For Write tool: check if content contains a version line
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')

HAS_VERSION_CHANGE=false
if [[ -n "$NEW_STRING" ]] && echo "$NEW_STRING" | grep -qE '^version:'; then
	HAS_VERSION_CHANGE=true
fi
if [[ -n "$CONTENT" ]] && echo "$CONTENT" | grep -qE '^version:'; then
	HAS_VERSION_CHANGE=true
fi

if $HAS_VERSION_CHANGE; then
	cat >&2 <<-EOF
		WARNING: Bumping homelab-library chart version.

		After changing the version in homelab-library/chart/Chart.yaml, run:

		    format

		This propagates the new library version to all consuming charts via
		sync-helm-deps.sh, keeping Chart.lock files up to date.

		Skipping 'format' will leave dependent charts referencing the old version.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
