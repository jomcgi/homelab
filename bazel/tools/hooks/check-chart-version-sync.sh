#!/bin/bash
# PreToolUse hook: warns when editing chart/Chart.yaml without a corresponding
# deploy/application.yaml update (targetRevision must stay in sync).
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning)
# Exit 2: block the operation

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check Chart.yaml edits
if [[ -z "$FILE_PATH" ]] || [[ "$FILE_PATH" != */chart/Chart.yaml ]]; then
	exit 0
fi

# Extract service root: .../projects/<service>/chart/Chart.yaml -> .../projects/<service>
SERVICE_DIR=$(dirname "$(dirname "$FILE_PATH")")
APP_YAML="$SERVICE_DIR/deploy/application.yaml"

if [[ ! -f "$APP_YAML" ]]; then
	# No application.yaml — not a standard service layout, skip
	exit 0
fi

# Check if application.yaml is already staged, modified, or in the working tree
REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$REPO_ROOT" ]]; then
	exit 0
fi

APP_YAML_REL="${APP_YAML#$REPO_ROOT/}"
CHANGED=$(git -C "$REPO_ROOT" status --porcelain "$APP_YAML_REL" 2>/dev/null || true)
DIFF_CHANGED=$(git -C "$REPO_ROOT" diff --name-only HEAD -- "$APP_YAML_REL" 2>/dev/null || true)

if [[ -z "$CHANGED" ]] && [[ -z "$DIFF_CHANGED" ]]; then
	cat >&2 <<-EOF
		WARNING: Editing chart/Chart.yaml without updating deploy/application.yaml.

		When bumping the chart version in Chart.yaml, you MUST also update
		targetRevision in $APP_YAML_REL to match.

		ArgoCD pulls charts from OCI by version — a stale targetRevision means
		the new chart version never deploys.

		Please also edit: $APP_YAML
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
