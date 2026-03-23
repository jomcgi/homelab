#!/bin/bash
# PreToolUse hook: blocks empty itemPath in OnePasswordItem resources inside
# deploy/values*.yaml files. An empty itemPath causes the 1Password Operator
# to fail silently — the secret is never synced, leading to pods crashing with
# missing environment variables.
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

# Only check deploy/values*.yaml files
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/values.*\.yaml$'; then
	exit 0
fi

if echo "$CONTENT" | grep -qE 'itemPath:\s*["'"'"']?["'"'"']?\s*$'; then
	cat >&2 <<-'EOF'
		BLOCK: itemPath is empty in a OnePasswordItem resource. An empty itemPath
		causes the 1Password Operator to fail silently — the Kubernetes secret is
		never populated, which leads to pods crashing with missing env variables.
		Set itemPath to the full 1Password item path, e.g.:
		  itemPath: "vaults/My Vault/items/my-secret"
		See: bazel/semgrep/rules/kubernetes/no-empty-1password-itempath.yaml
	EOF
	exit 2
fi

exit 0
