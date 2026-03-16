#!/bin/bash
# PreToolUse hook: redirects bazel/bazelisk commands to bb remote.
# Blocks direct bazel invocations so all builds run on BuildBuddy cloud runners.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the command
# Exit 2: block the command (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check commands that contain bazel
if [[ ! "$COMMAND" == *bazel* ]]; then
	exit 0
fi

# Allow git commands (commit messages may mention bazel)
if [[ "$COMMAND" == git\ * ]]; then
	exit 0
fi

# Allow format command (runs gazelle which wraps bazel internally)
if [[ "$COMMAND" == format* ]]; then
	exit 0
fi

# Allow bb commands (already using BuildBuddy CLI)
if [[ "$COMMAND" == bb\ * ]] || [[ "$COMMAND" == */bb\ * ]]; then
	exit 0
fi

# Block direct bazel/bazelisk invocations
if [[ "$COMMAND" == bazel\ * ]] || [[ "$COMMAND" == bazelisk\ * ]] || [[ "$COMMAND" == *"&& bazel"* ]] || [[ "$COMMAND" == *"; bazel"* ]]; then
	cat >&2 <<-'EOF'
		BLOCKED: Use `bb remote` instead of direct bazel/bazelisk commands.

		All Bazel commands should run on BuildBuddy cloud runners — no local bazel server.

		Examples:
		  bb remote test //...                    # Run all tests
		  bb remote build //path/to:target        # Build a target
		  bb remote query "deps(//path/to:target)" # Query build graph
		  bb remote run @rules_apko//apko -- lock path/to/apko.yaml

		For CI debugging, use the /buildbuddy skill or:
		  bb view <invocation_id>
		  bb print --invocation_id=<id>
		  bb ask "why did this fail?" --invocation_id=<id>
	EOF
	exit 2
fi

exit 0
