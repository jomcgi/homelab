#!/bin/bash
# PreToolUse hook: warns when a service deploy directory has an ArgoCD Application
# but is missing imageupdater.yaml. Services using custom-built container images
# need imageupdater.yaml to automate digest updates — without it, images go stale
# and pods crash with ImagePullBackOff.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only, not a blocker)

set -euo pipefail

INPUT=$(cat)

# Extract file path and content from Write (content) or Edit (new_string) tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Only check */deploy/kustomization.yaml files
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/kustomization\.yaml$'; then
	exit 0
fi

# If application.yaml is not in the resources list, nothing to check
if ! echo "$CONTENT" | grep -qF 'application.yaml'; then
	exit 0
fi

# If imageupdater.yaml is already present, all good
if echo "$CONTENT" | grep -qF 'imageupdater.yaml'; then
	exit 0
fi

cat >&2 <<-'EOF'
	WARNING: This service has an ArgoCD Application but no imageupdater.yaml.
	If this service uses custom-built container images (not upstream charts),
	add an imageupdater.yaml to automate digest updates and prevent
	ImagePullBackOff from stale digests.
	See projects/agent_platform/cluster_agents/deploy/imageupdater.yaml for an example.
EOF

exit 0
