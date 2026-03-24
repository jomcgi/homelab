#!/bin/bash
# PreToolUse hook: warns when application.yaml files contain overrideable Helm
# values (podAnnotations, podLabels, resources, nodeSelector, tolerations, env)
# inside a valuesObject block. These values should live in values.yaml so they
# get CI coverage via helm_template_test.
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

# Only check */deploy/application.yaml files
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/application\.yaml$'; then
	exit 0
fi

# Only warn if the file contains a valuesObject block
if ! echo "$CONTENT" | grep -qF 'valuesObject:'; then
	exit 0
fi

# Check for overrideable Helm values inside valuesObject
if echo "$CONTENT" | grep -qE '^\s*(podAnnotations|podLabels|resources|nodeSelector|tolerations|env):'; then
	cat >&2 <<-'EOF'
		WARNING: application.yaml contains overrideable Helm values (podAnnotations,
		podLabels, resources, nodeSelector, tolerations, or env) inside a valuesObject
		block. These values should live in values.yaml so they receive CI coverage via
		helm_template_test. Move them to the service's deploy/values.yaml instead.
		See PRs #1488-#1499 for examples of this pattern.
	EOF
fi

exit 0
