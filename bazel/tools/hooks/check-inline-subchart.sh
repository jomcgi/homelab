#!/bin/bash
# PreToolUse hook: warns when a Chart.yaml is written inside another chart's
# directory (i.e. projects/*/chart/<subdir>/Chart.yaml) without the subdirectory
# being declared as a file:// dependency in the parent chart's Chart.yaml.
#
# This catches the anti-pattern of vendoring a subchart inline inside a parent
# chart's chart/ directory without declaring it as a Helm dependency.
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

# Only check Chart.yaml files nested inside a chart directory
# Pattern: .../chart/<subdir>/Chart.yaml  (but NOT .../chart/Chart.yaml itself)
if ! echo "$FILE_PATH" | grep -qE '.*/chart/[^/]+/Chart\.yaml$'; then
	exit 0
fi

# Extract the subdirectory name and parent chart/Chart.yaml path
# e.g. projects/foo/chart/memgraph/Chart.yaml -> subdir=memgraph, parent=projects/foo/chart/Chart.yaml
CHART_SUBDIR=$(basename "$(dirname "$FILE_PATH")")
PARENT_CHART_DIR=$(dirname "$(dirname "$FILE_PATH")")
PARENT_CHART_YAML="$PARENT_CHART_DIR/Chart.yaml"

if [[ ! -f "$PARENT_CHART_YAML" ]]; then
	# No parent Chart.yaml — not a standard Helm chart layout, skip
	exit 0
fi

# Check if the subdirectory is declared as a file:// dependency in the parent Chart.yaml
if ! grep -qF "file://$CHART_SUBDIR" "$PARENT_CHART_YAML" &&
	! grep -qF "file://./$CHART_SUBDIR" "$PARENT_CHART_YAML"; then
	cat >&2 <<-EOF
		WARNING: Writing Chart.yaml inside chart/$CHART_SUBDIR/ but '$CHART_SUBDIR' is not
		declared as a file:// dependency in $PARENT_CHART_YAML.

		If you are vendoring a subchart, add it to the parent Chart.yaml dependencies:

		  dependencies:
		    - name: $CHART_SUBDIR
		      version: "*"
		      repository: "file://$CHART_SUBDIR"

		Then run 'helm dependency update' in the chart directory to generate Chart.lock.
		See PRs #1488-#1489 for context on this pattern.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
