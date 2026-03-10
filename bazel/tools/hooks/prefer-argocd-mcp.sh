#!/bin/bash
# PreToolUse hook: redirects argocd CLI commands to ArgoCD MCP tools.
# Blocks all argocd CLI usage — MCP tools cover all read operations,
# and write operations should go through GitOps.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the command
# Exit 2: block the command (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only block the argocd CLI binary — not commands that mention "argocd"
# in paths or labels (e.g. bazel test //overlays/.../argocd:semgrep_test).
if [[ ! "$COMMAND" =~ (^|[;&|[:space:]])argocd([[:space:]]|$) ]]; then
	exit 0
fi

cat >&2 <<-'EOF'
	BLOCKED: Use ArgoCD MCP tools instead of the `argocd` CLI.

	MCP equivalents (use ToolSearch with +argocd to load):
	  - argocd-mcp-list-applications              List all applications
	  - argocd-mcp-get-application                 Get application details
	  - argocd-mcp-get-application-resource-tree   Get resource tree (replaces `app diff`)
	  - argocd-mcp-get-application-managed-resources  List managed resources
	  - argocd-mcp-get-application-events          Get application events
	  - argocd-mcp-get-application-workload-logs   Get workload logs
	  - argocd-mcp-get-resources                   Get specific resources
	  - argocd-mcp-get-resource-events             Get resource events
	  - argocd-mcp-get-resource-actions            Get available actions
	  - argocd-mcp-sync-application                Sync an application

	For write operations (create/update/delete), prefer GitOps:
	  Edit projects/<project>/<service>/deploy/values.yaml -> commit -> push -> ArgoCD auto-syncs.
EOF
exit 2
