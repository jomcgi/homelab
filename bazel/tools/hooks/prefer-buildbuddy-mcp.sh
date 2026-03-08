#!/bin/bash
# PreToolUse hook: redirects BuildBuddy API curl commands to MCP tools.
# Blocks curl commands targeting buildbuddy URLs.
# Non-buildbuddy curl commands pass through.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the command
# Exit 2: block the command (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check commands that contain both curl and buildbuddy
if [[ ! "$COMMAND" =~ curl ]] || [[ ! "$COMMAND" =~ buildbuddy ]]; then
	exit 0
fi

cat >&2 <<-'EOF'
	BLOCKED: Use BuildBuddy MCP tools instead of curl to the BuildBuddy API.

	MCP equivalents (use ToolSearch with +buildbuddy to load):
	  - buildbuddy-mcp-get-invocation     Get invocation details
	  - buildbuddy-mcp-get-log            Fetch build logs
	  - buildbuddy-mcp-get-target         Get target information
	  - buildbuddy-mcp-get-action         Get action details
	  - buildbuddy-mcp-get-file           Download files by URI
	  - buildbuddy-mcp-execute-workflow   Trigger a workflow

	MCP handles authentication automatically — no API key needed.

	Workflow: gh pr checks -> extract invocation ID -> MCP tools
EOF
exit 2
