#!/bin/bash
# PreToolUse hook: blocks plan/design file writes to the main worktree.
# Plans should be written in a linked worktree so they land on the feature branch.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the write
# Exit 2: block the write (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only check Write and Edit tools
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
	exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check docs/plans/ files
if [[ "$FILE_PATH" != *"/docs/plans/"* ]]; then
	exit 0
fi

# Determine the git repo root for this file
DIR=$(dirname "$FILE_PATH")
if [ ! -d "$DIR" ]; then
	# Directory doesn't exist yet — check parent
	DIR=$(dirname "$DIR")
	[ -d "$DIR" ] || exit 0
fi

REPO_ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0

# Check if we're in a linked worktree by comparing --git-dir to --git-common-dir.
# In the main worktree these resolve to the same path; in a linked worktree they differ.
GIT_DIR=$(cd "$REPO_ROOT" && git rev-parse --absolute-git-dir 2>/dev/null) || exit 0
GIT_COMMON_DIR=$(cd "$REPO_ROOT" && git rev-parse --git-common-dir 2>/dev/null) || exit 0

# Normalize --git-common-dir (may be relative)
if [[ "$GIT_COMMON_DIR" != /* ]]; then
	GIT_COMMON_DIR=$(cd "$REPO_ROOT" && cd "$GIT_COMMON_DIR" && pwd)
fi

if [[ "$GIT_DIR" != "$GIT_COMMON_DIR" ]]; then
	# Linked worktree — allow the write
	exit 0
fi

# Main worktree — block the write
cat >&2 <<-EOF
	BLOCKED: Plan/design files must be written to a worktree, not the main repo.
	File: $FILE_PATH

	Create a worktree first, then save plans there:
	  git worktree add -b docs/<topic> /tmp/claude-worktrees/<topic> origin/main

	Then write to the worktree's docs/plans/ directory instead.
EOF
exit 2
