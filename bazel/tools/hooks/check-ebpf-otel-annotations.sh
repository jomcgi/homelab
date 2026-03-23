#!/bin/bash
# PreToolUse hook: blocks instrumentation.opentelemetry.io/inject-* annotations
# in deploy/values*.yaml and deploy/application.yaml files.
# eBPF-based OTel injection requires CAP_NET_ADMIN or CAP_BPF which are
# incompatible with the `drop: ALL` securityContext used in this cluster.
# Use SDK-based instrumentation instead.
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

# Only check deploy/values*.yaml and deploy/application.yaml files
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/values.*\.yaml$|.*/deploy/application\.yaml$'; then
	exit 0
fi

if echo "$CONTENT" | grep -qE 'instrumentation\.opentelemetry\.io/inject-'; then
	cat >&2 <<-'EOF'
		BLOCK: instrumentation.opentelemetry.io/inject-* annotations use eBPF-based
		auto-instrumentation which requires CAP_NET_ADMIN or CAP_BPF capabilities.
		These are incompatible with the `drop: ALL` securityContext used in this
		cluster and will cause pod admission failures or runtime errors.
		Use SDK-based OpenTelemetry instrumentation instead.
		See: PRs #1446 and #1455 which removed these annotations.
	EOF
	exit 2
fi

exit 0
