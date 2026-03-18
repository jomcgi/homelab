#!/bin/bash
# PreToolUse hook: warns when writing/editing file content that contains a
# stale copyright year (Copyright 2025). The current year is 2026.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)

set -euo pipefail

INPUT=$(cat)

# Extract content from Write tool (content field) or Edit tool (new_string field)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

if echo "$CONTENT" | grep -q 'Copyright 2025'; then
	cat >&2 <<-EOF
		WARNING: File content contains stale copyright year "Copyright 2025".
		The current year is 2026 — please update the copyright header to:
		    Copyright 2026 Block, Inc.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
