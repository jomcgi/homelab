#!/bin/bash
# PreToolUse hook: warn when Write/Edit content contains create_subprocess_exec
# with a hardcoded '--model' string literal argument.
#
# Using a hardcoded model name means the model can only be changed by editing
# and redeploying code. Reading the model from an env var (e.g. CLAUDE_MODEL)
# allows runtime configuration without a code change.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr — advisory only)
# Exit 2: block (not used)

set -euo pipefail

INPUT=$(cat)

# Only check Python files
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi
if [[ "$FILE_PATH" != *.py ]]; then
	exit 0
fi

# Get the content being written (Write tool) or the replacement string (Edit tool)
NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty')
if [[ -z "$NEW_CONTENT" ]]; then
	exit 0
fi

# Only relevant if create_subprocess_exec is used
if ! echo "$NEW_CONTENT" | grep -q 'create_subprocess_exec'; then
	exit 0
fi

# Check for '--model' followed (on the same line or the next) by a string literal.
# This uses grep with -A1 (after context) to handle multi-line argument style.
if echo "$NEW_CONTENT" | grep -qE '"--model"|'"'"'--model'"'"; then
	# Check if there's a string literal near the --model flag.
	# We look for '--model' on a line and either:
	#   a) a string literal following it on the same line, or
	#   b) a string literal on the immediately following line.
	HAS_ISSUE=$(echo "$NEW_CONTENT" | awk '
		/create_subprocess_exec/ { in_call = 1 }
		in_call && /["'"'"']--model["'"'"']/ {
			# Same line: --model followed by a string literal?
			if (/["'"'"']--model["'"'"'][[:space:]]*,[[:space:]]*["'"'"']/) {
				print "yes"; exit
			}
			saw_model = 1
			next
		}
		saw_model {
			# Next line: is it a string literal argument?
			if (/^[[:space:]]*["'"'"']/) {
				print "yes"; exit
			}
			saw_model = 0
		}
	')

	if [[ "$HAS_ISSUE" == "yes" ]]; then
		cat >&2 <<-EOF
			WARNING: create_subprocess_exec called with a hardcoded '--model' string literal.

			File: $FILE_PATH

			Hardcoded model names require a code change + redeploy to switch models.
			Read the model from an environment variable instead:

			  model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")
			  await asyncio.create_subprocess_exec("claude", "--model", model, ...)

			The semgrep rule 'no-hardcoded-claude-model-subprocess' will flag this in CI.
		EOF
	fi
fi

exit 0
