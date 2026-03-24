#!/bin/bash
# PreToolUse hook: warns when editing */deploy/values.yaml or */deploy/templates/*
# in a deploy/ directory that contains a sibling Chart.yaml, but the Chart.yaml
# has no uncommitted changes (meaning the chart version wasn't bumped).
#
# This catches the pattern from PRs #1499/#1505/#1511 where values.yaml was
# changed but the OCI chart version wasn't bumped, so ArgoCD kept pulling the
# old chart.
#
# Also checks the */chart/Chart.yaml pattern for services that keep their chart
# in a sibling chart/ directory.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only, not a blocker)

set -euo pipefail

INPUT=$(cat)

# Extract file path from Write or Edit tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Only check files inside a deploy/ directory
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/'; then
	exit 0
fi

# Only check values.yaml and templates/* files
if ! echo "$FILE_PATH" | grep -qE '.*/deploy/(values[^/]*\.yaml|templates/.+)$'; then
	exit 0
fi

# Derive the deploy/ directory from the file path
DEPLOY_DIR=$(echo "$FILE_PATH" | sed 's|\(/deploy/\).*|\1|' | sed 's|/$||')

# ---- Pattern 1: Chart.yaml lives directly inside deploy/ ----
CHART_YAML_IN_DEPLOY="${DEPLOY_DIR}/Chart.yaml"

# ---- Pattern 2: Chart.yaml lives in a sibling chart/ directory ----
SERVICE_DIR=$(dirname "$DEPLOY_DIR")
CHART_YAML_IN_CHART="${SERVICE_DIR}/chart/Chart.yaml"

# Pick whichever Chart.yaml exists (prefer deploy/, then chart/)
CHART_YAML=""
if [[ -f "$CHART_YAML_IN_DEPLOY" ]]; then
	CHART_YAML="$CHART_YAML_IN_DEPLOY"
elif [[ -f "$CHART_YAML_IN_CHART" ]]; then
	CHART_YAML="$CHART_YAML_IN_CHART"
fi

if [[ -z "$CHART_YAML" ]]; then
	# No Chart.yaml found — not a chart-versioned service, skip
	exit 0
fi

# Check if Chart.yaml has any staged or unstaged changes
REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$REPO_ROOT" ]]; then
	exit 0
fi

CHART_YAML_REL="${CHART_YAML#$REPO_ROOT/}"

# git status --porcelain covers staged, modified, and untracked changes
CHANGED=$(git -C "$REPO_ROOT" status --porcelain "$CHART_YAML_REL" 2>/dev/null || true)
# Also check uncommitted changes vs HEAD (handles new files in working tree)
DIFF_CHANGED=$(git -C "$REPO_ROOT" diff --name-only HEAD -- "$CHART_YAML_REL" 2>/dev/null || true)

if [[ -z "$CHANGED" ]] && [[ -z "$DIFF_CHANGED" ]]; then
	cat >&2 <<-EOF
		WARNING: Editing ${FILE_PATH##*/} under deploy/ but ${CHART_YAML_REL} has no uncommitted changes.

		ArgoCD pulls Helm charts from OCI by version. If you are changing deploy
		values or templates, you likely need to bump the chart version in:

		  $CHART_YAML

		Without a version bump, ArgoCD will continue pulling the old chart from OCI,
		and your changes will never take effect in the cluster.

		See PRs #1499/#1505/#1511 for context on this pattern.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
