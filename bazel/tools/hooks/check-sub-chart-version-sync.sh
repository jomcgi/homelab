#!/bin/bash
# PreToolUse hook: reminds the developer to also update the parent umbrella
# chart's dependencies[].version when editing a sub-chart Chart.yaml.
#
# A sub-chart lives at chart/<subchartname>/Chart.yaml — distinct from the
# top-level chart/Chart.yaml handled by check-chart-version-sync.sh.
# When the sub-chart version changes, the parent chart/Chart.yaml dependencies
# entry for that sub-chart must also be bumped or Helm will pull the old version.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check sub-chart Chart.yaml edits.
# Pattern: */chart/<subchartname>/Chart.yaml (two levels deep inside chart/)
# This is distinct from */chart/Chart.yaml (top-level chart) handled by
# check-chart-version-sync.sh.
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# Match: ends with /chart/<something>/Chart.yaml
# The path must have at least chart/<name>/Chart.yaml
if ! echo "$FILE_PATH" | grep -qE '/chart/[^/]+/Chart\.yaml$'; then
	exit 0
fi

cat >&2 <<-'EOF'
	WARNING: You are editing a sub-chart Chart.yaml.

	Remember to also bump the matching dependencies[].version entry in the
	parent chart/Chart.yaml to keep them in sync. If the parent chart version
	is not updated, Helm will continue to use the old sub-chart version.
EOF

# Always allow — this is a warning, not a blocker
exit 0
