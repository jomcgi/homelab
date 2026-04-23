#!/bin/bash
# PreToolUse hook: warn when embedding a large multi-line string block in a values YAML file.
#
# Inline Jinja2 / prompt templates > 30 lines make values files hard to review,
# diff, and audit. Large templates should live in their own file and be loaded
# at runtime (e.g. via a ConfigMap or mounted secret).
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr)
# Exit 2: block (not used — this is advisory only)

set -euo pipefail

INPUT=$(cat)

# Only trigger on values YAML files (deploy/values*.yaml)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ "$FILE_PATH" == **/deploy/values*.yaml ]] || [[ "$FILE_PATH" == */deploy/values*.yaml ]] || exit 0

# Get the new content being written (Write tool) or the replacement string (Edit tool)
NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty')
[[ -n "$NEW_STRING" ]] || exit 0

# Check for YAML block scalar indicators (| or >) followed by more than 30 lines
# We look for any block scalar that introduces a run of > 30 lines before the next
# non-indented key or end of string.
LINE_COUNT=$(echo "$NEW_STRING" | awk '
  /[|>][+-]?[[:space:]]*$/ { in_block=1; count=0; next }
  in_block && /^[[:space:]]+/ { count++; if (count > 30) { print count; exit } }
  in_block && !/^[[:space:]]/ { in_block=0; count=0 }
' | head -1)

if [[ -n "$LINE_COUNT" ]]; then
	cat >&2 <<-EOF
		WARNING: Large inline multi-line block (${LINE_COUNT}+ lines) in a values YAML file.

		Embedding long Jinja2 templates, prompts, or configuration blocks directly in
		deploy/values*.yaml makes files hard to review, diff, and audit in pull requests.

		Consider:
		  - Moving the template to a standalone file and loading it via a ConfigMap
		  - Referencing the content via a 1Password secret
		  - Splitting the template into a dedicated chart/templates/ file

		If this is intentional (e.g. a short example), proceed.
	EOF
fi

exit 0
