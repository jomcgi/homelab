#!/bin/bash
# PreToolUse hook: warns when writing/editing deploy files that contain hardcoded
# .svc.cluster.local URLs. Kubernetes service URLs change when a Helm release is
# renamed — they should be injected via values.yaml env vars, not hardcoded.
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

# Only warn for deploy-related files (values.yaml or deploy/*.yaml)
IS_DEPLOY_FILE=false
if echo "$FILE_PATH" | grep -qE '(^|/)values\.yaml$'; then
	IS_DEPLOY_FILE=true
elif echo "$FILE_PATH" | grep -qE '/deploy/[^/]+\.yaml$'; then
	IS_DEPLOY_FILE=true
fi

if ! $IS_DEPLOY_FILE; then
	exit 0
fi

if echo "$CONTENT" | grep -qF '.svc.cluster.local'; then
	cat >&2 <<-'EOF'
		WARNING: File content contains a hardcoded .svc.cluster.local URL.
		Kubernetes service URLs change when a Helm release is renamed — hardcoding
		them causes silent breakage. Inject service URLs via values.yaml env vars instead.
		Example in values.yaml:  myService: { env: { TARGET_URL: "http://release-svc.ns.svc.cluster.local" } }
		Example in Go:           url := envOr("TARGET_URL", "")  // no default — set in values.yaml
		See: CLAUDE.md anti-patterns and semgrep rule no-hardcoded-k8s-service-url
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
