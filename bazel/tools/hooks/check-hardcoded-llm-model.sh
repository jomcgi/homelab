#!/bin/bash
# PreToolUse hook: warns when writing/editing Python files that contain hardcoded
# LLM model name strings (e.g. "gemma-4-26b-a4b", "llama-3.1-8b", "mistral-7b",
# "claude-3-sonnet"). Hardcoded model names make it painful to swap models or
# promote config to env vars — they should live in an environment variable or
# a named constant, not scattered inline in API call payloads.
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

# Only warn for Python files
if ! echo "$FILE_PATH" | grep -qE '\.py$'; then
	exit 0
fi

# Match model name families followed by a version/size identifier:
#   gemma-4-26b-a4b, gemma-3-27b, llama-3.1-8b, llama-3-70b,
#   mistral-7b, mistral-nemo, claude-3-sonnet, claude-3-5-haiku, etc.
if echo "$CONTENT" | grep -qiE '"(gemma|llama|mistral|claude)-[0-9a-z]'; then
	cat >&2 <<-'EOF'
		WARNING: Python file contains a hardcoded LLM model name string.
		Hardcoded model names (e.g. "gemma-4-26b-a4b", "llama-3.1-8b") make it
		difficult to swap models across environments or promote config to a
		central place. Use an environment variable or a named module-level
		constant instead.
		Example:
		  MODEL = os.environ.get("LLM_MODEL", "gemma-4-26b-a4b")
		  ...
		  "model": MODEL,
		See: CLAUDE.md anti-patterns
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
