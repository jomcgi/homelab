#!/bin/bash
# PreToolUse hook: blocks mcp.run(transport="http") or mcp.run(transport='http')
# in Python files. The opaque server prevents adding custom routes like /healthz
# for Kubernetes liveness probes. Use mcp.http_app() + uvicorn instead.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation
# Exit 2: block the operation

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

if echo "$CONTENT" | grep -qE 'mcp\.run\(' && echo "$CONTENT" | grep -qE "transport=['\"]http['\"]"; then
	cat >&2 <<-'EOF'
		BLOCK: mcp.run(transport="http") spawns an opaque server that prevents adding
		custom routes like /healthz for Kubernetes liveness probes. Use the pattern:
		  app = mcp.http_app()
		  uvicorn.run(app, host="0.0.0.0", port=8080)
		This allows adding /healthz and other custom routes alongside the MCP server.
		See: bazel/semgrep/rules/python/no-mcp-run-http.yaml and PR #1441
	EOF
	exit 2
fi

exit 0
