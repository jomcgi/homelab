#!/bin/bash
# PreToolUse hook: warns when writing/editing file content that references
# stale repository paths from the old layout (overlays/prod/, //services/,
# //charts/). The canonical location for all services is projects/<service>/.
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

WARNED=false

if echo "$CONTENT" | grep -qE 'overlays/prod/'; then
	cat >&2 <<-'EOF'
		WARNING: File content references stale path "overlays/prod/".
		The correct layout uses projects/<service>/deploy/ for all service configs.
		Example: projects/trips/deploy/values.yaml
	EOF
	WARNED=true
fi

if echo "$CONTENT" | grep -qE '//services/[a-z]'; then
	cat >&2 <<-'EOF'
		WARNING: File content references stale Bazel path "//services/<name>".
		The correct path is //projects/<service>/... — all services live under projects/.
		Example: //projects/trips/... or //projects/platform/...
	EOF
	WARNED=true
fi

if echo "$CONTENT" | grep -qE '//charts/[a-z]'; then
	cat >&2 <<-'EOF'
		WARNING: File content references stale Bazel path "//charts/<name>".
		The correct path is //projects/<service>/chart/... — charts are colocated with services.
		Example: //projects/trips/chart/...
	EOF
	WARNED=true
fi

# Always allow — this is a warning, not a blocker
exit 0
