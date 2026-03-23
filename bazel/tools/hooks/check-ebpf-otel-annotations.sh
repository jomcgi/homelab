#!/bin/bash
# PreToolUse hook: blocks writing eBPF-based OpenTelemetry auto-instrumentation
# annotations to deploy files. These annotations add init containers that can
# crash or hang pods at startup in this cluster.
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

# Only check deploy-related files (values*.yaml or deploy/*.yaml or application.yaml)
IS_DEPLOY_FILE=false
if echo "$FILE_PATH" | grep -qE '(^|/)values[^/]*\.yaml$'; then
	IS_DEPLOY_FILE=true
elif echo "$FILE_PATH" | grep -qE '/deploy/[^/]+\.yaml$'; then
	IS_DEPLOY_FILE=true
fi

if ! $IS_DEPLOY_FILE; then
	exit 0
fi

if echo "$CONTENT" | grep -qF 'instrumentation.opentelemetry.io/inject-'; then
	cat >&2 <<-'EOF'
		BLOCK: eBPF-based OpenTelemetry auto-instrumentation is not supported in this cluster.
		The `instrumentation.opentelemetry.io/inject-*` annotations add init containers that
		can crash or hang pods at startup when securityContext has `drop: ALL` capabilities.
		Use manual OTel SDK instrumentation instead — import the SDK directly in your
		application code and configure it via environment variables.
		See: bazel/semgrep/rules/yaml/no-ebpf-otel-annotations.yaml
	EOF
	exit 2
fi

exit 0
