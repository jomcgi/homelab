#!/bin/bash
# PreToolUse hook: warns when writing to a deploy/ directory that contains both
# Chart.yaml and application.yaml but the BUILD file lacks an argocd_app rule.
# Without an argocd_app BUILD target, the service won't get CI coverage via
# helm_template_test and semgrep validation.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only, not a blocker)

set -euo pipefail

INPUT=$(cat)

# Extract file path from Write (content) or Edit (new_string) tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Only check files under */deploy/ directories
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/'; then
	exit 0
fi

# Derive the deploy directory from the file path
DEPLOY_DIR=$(dirname "$FILE_PATH")

# Only warn if both Chart.yaml (chart/) and application.yaml exist alongside
# Wait - Chart.yaml is in the chart/ directory, one level up from deploy/
# Check if application.yaml exists in the deploy dir
if [[ ! -f "$DEPLOY_DIR/application.yaml" ]]; then
	exit 0
fi

# Check for Chart.yaml in the sibling chart/ directory
SERVICE_DIR=$(dirname "$DEPLOY_DIR")
if [[ ! -f "$SERVICE_DIR/chart/Chart.yaml" ]]; then
	exit 0
fi

# Check if BUILD file exists and has an argocd_app rule
BUILD_FILE="$DEPLOY_DIR/BUILD"
if [[ ! -f "$BUILD_FILE" ]]; then
	cat >&2 <<-'EOF'
		WARNING: This deploy/ directory has a Chart.yaml (custom chart) and
		application.yaml but is missing a BUILD file entirely. Add a BUILD file
		with an argocd_app rule for CI helm template and semgrep coverage.
		See bazel/rules/argocd_app.bzl for the rule definition.
	EOF
	exit 0
fi

if ! grep -q 'argocd_app' "$BUILD_FILE"; then
	cat >&2 <<-'EOF'
		WARNING: This deploy/ directory has a Chart.yaml (custom chart) and
		application.yaml but the BUILD file is missing an argocd_app rule.
		Add an argocd_app BUILD target to enable CI helm template testing and
		semgrep validation coverage for this service.
		See bazel/rules/argocd_app.bzl for the rule definition.
	EOF
fi

exit 0
