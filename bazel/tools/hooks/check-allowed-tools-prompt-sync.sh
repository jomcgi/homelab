#!/bin/bash
# PreToolUse hook: warn when a Python file contains --allowedTools on a subprocess
# call but tool names referenced in nearby prompt/docstring strings are missing
# from that --allowedTools value.
#
# This catches "tool declaration drift" — where a Claude subprocess call lists
# tools in its prompt text (e.g. "use WebSearch to find...") but forgets to
# include them in --allowedTools, creating a silent capability gap at runtime.
#
# Scoped to .py files only. Advisory only — exits 0 always.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr — advisory only)
# Exit 2: block (not used by this hook)

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

# Only relevant when --allowedTools appears in the file
if ! echo "$NEW_CONTENT" | grep -q -- '--allowedTools'; then
	exit 0
fi

# Known tool names to look for
TOOL_NAMES=(WebSearch WebFetch Read Write Edit Bash Glob Grep)

DRIFT=()
for TOOL in "${TOOL_NAMES[@]}"; do
	# Skip if this tool name doesn't appear anywhere in the content
	if ! echo "$NEW_CONTENT" | grep -q "$TOOL"; then
		continue
	fi

	# Tool name appears somewhere in the file. Now check whether it also
	# appears on every --allowedTools line.
	# We look at lines containing --allowedTools; if NONE of them mention
	# the tool, it may be declared in prompt text but blocked at runtime.
	if ! echo "$NEW_CONTENT" | grep -- '--allowedTools' | grep -q "$TOOL"; then
		DRIFT+=("$TOOL")
	fi
done

if [[ ${#DRIFT[@]} -gt 0 ]]; then
	TOOLS_LIST=$(
		IFS=', '
		echo "${DRIFT[*]}"
	)
	cat >&2 <<-EOF
		WARNING: Possible tool declaration drift in $FILE_PATH

		The following tool names appear in the file content but are not present
		in any --allowedTools flag value:
		  $TOOLS_LIST

		If these tools are referenced in a prompt string passed to a Claude
		subprocess (e.g. create_subprocess_exec with --allowedTools), the
		subprocess will be unable to call them at runtime, causing silent
		capability gaps.

		Add the missing tools to the --allowedTools argument, for example:
		  "--allowedTools", "Read,Write,WebSearch",

		(This is an advisory warning — the write will proceed.)
	EOF
fi

exit 0
