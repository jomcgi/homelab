#!/bin/bash
# PreToolUse hook: warns when writing/editing Python files that contain
# session.add() inside a for/while loop body without a nearby begin_nested()
# savepoint. Batch inserts without savepoints cause one bad row to roll back
# the entire batch — see commits aabff202 and 8ab28069.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)

set -euo pipefail

INPUT=$(cat)

# Extract file path and content from Write (content) or Edit (new_string) tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Only check Python files
if ! echo "$FILE_PATH" | grep -qE '\.py$'; then
	exit 0
fi

# Check if content contains session.add(
if ! echo "$CONTENT" | grep -qF 'session.add('; then
	exit 0
fi

# Check if content contains a for or while loop
if ! echo "$CONTENT" | grep -qE '^\s*(for|while)\s+'; then
	exit 0
fi

# Check if begin_nested is already present — if so, the caller has handled it
if echo "$CONTENT" | grep -qF 'begin_nested'; then
	exit 0
fi

cat >&2 <<-'EOF'
	WARNING: Python file contains session.add() inside a loop without begin_nested().
	Batch inserts without per-iteration savepoints cause one bad row to roll back the
	entire batch. Wrap each iteration in a savepoint to isolate failures:

	    for item in items:
	        try:
	            with session.begin_nested():
	                session.add(MyModel(...))
	        except Exception as e:
	            logger.warning("skipping %s: %s", item, e)

	See: commits aabff202 and 8ab28069 for examples of this bug.
EOF

# Always allow — this is a warning, not a blocker
exit 0
