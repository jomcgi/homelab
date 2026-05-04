#!/bin/bash
# PreToolUse hook: warn when Chart.yaml version and application.yaml targetRevision are out of sync.
#
# A chart version bump that is not reflected in the ArgoCD application's targetRevision means
# ArgoCD will continue deploying the old chart version. Conversely, bumping targetRevision
# without updating Chart.yaml points ArgoCD at a version that doesn't exist yet.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr — advisory only)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger on chart/Chart.yaml or deploy/application.yaml edits
[[ "$FILE_PATH" == */chart/Chart.yaml ]] || [[ "$FILE_PATH" == */deploy/application.yaml ]] || exit 0

# Determine service root:
#   - for chart/Chart.yaml  → two levels up (service/chart/Chart.yaml → service/)
#   - for deploy/application.yaml → one level up (service/deploy/application.yaml → service/)
if [[ "$FILE_PATH" == */chart/Chart.yaml ]]; then
	SERVICE_ROOT=$(dirname "$(dirname "$FILE_PATH")")
else
	SERVICE_ROOT=$(dirname "$(dirname "$FILE_PATH")")
fi

CHART_YAML="$SERVICE_ROOT/chart/Chart.yaml"
APP_YAML="$SERVICE_ROOT/deploy/application.yaml"

# Handle missing files gracefully
[[ -f "$CHART_YAML" ]] || exit 0
[[ -f "$APP_YAML" ]] || exit 0

# Extract chart version (first ^version: line)
CHART_VERSION=$(grep -m1 '^version:' "$CHART_YAML" 2>/dev/null | awk '{print $2}' | tr -d '"' | tr -d "'") || exit 0
[[ -n "$CHART_VERSION" ]] || exit 0

# Extract targetRevision — first occurrence that is NOT HEAD or main
TARGET_REVISION=$(grep 'targetRevision:' "$APP_YAML" 2>/dev/null | grep -v 'HEAD\|main' | head -1 | awk '{print $2}' | tr -d '"' | tr -d "'") || exit 0
[[ -n "$TARGET_REVISION" ]] || exit 0

# Compare and warn if out of sync
if [[ "$CHART_VERSION" != "$TARGET_REVISION" ]]; then
	cat >&2 <<-EOF
		WARNING: Chart.yaml version and application.yaml targetRevision are out of sync.

		  chart/Chart.yaml version : $CHART_VERSION
		  deploy/application.yaml targetRevision: $TARGET_REVISION

		ArgoCD pulls the chart by targetRevision — a mismatch means it will deploy the
		wrong chart version (or fail if the version doesn't exist in the OCI registry).
		Update both files to the same version before merging.

		Files:
		  $CHART_YAML
		  $APP_YAML
	EOF
fi

exit 0
