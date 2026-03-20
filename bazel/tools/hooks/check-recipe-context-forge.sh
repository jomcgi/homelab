#!/bin/bash
# PreToolUse hook: warns when writing/editing a recipe YAML that contains a
# type: builtin extension but does NOT contain a type: streamable_http extension.
# This prevents accidentally shipping recipes without context-forge integration
# (the bug fixed by PR #1377 where 3 recipes were missing context-forge).
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check recipe YAML files
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi
if ! echo "$FILE_PATH" | grep -qE '/recipes/[^/]+\.yaml$'; then
	exit 0
fi

# Extract content from Write tool (content field) or Edit tool (new_string field)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Warn if the recipe declares a builtin extension but has no streamable_http extension
if echo "$CONTENT" | grep -q 'type: builtin' && ! echo "$CONTENT" | grep -q 'type: streamable_http'; then
	cat >&2 <<-EOF
		WARNING: Recipe YAML contains a 'type: builtin' extension but no 'type: streamable_http' extension.

		Recipes that use builtin extensions without a corresponding streamable_http
		extension are missing context-forge integration (see PR #1377 where 3 recipes
		had this bug).

		If this recipe should expose context-forge, add a streamable_http extension block.
		If context-forge is intentionally excluded, you can ignore this warning.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
