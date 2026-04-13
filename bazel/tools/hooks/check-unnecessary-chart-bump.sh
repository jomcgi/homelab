#!/bin/bash
# PreToolUse hook: warn when bumping Chart.yaml for test-only branch changes.
#
# A chart version bump triggers an ArgoCD redeploy and pod restart.
# If all other branch changes are in test files, the bump is likely unnecessary.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings emitted on stderr)
# Exit 2: block (not used — this is advisory only)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger on chart/Chart.yaml edits
[[ "$FILE_PATH" == */chart/Chart.yaml ]] || exit 0

REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null) || exit 0

# Get all files changed vs origin/main on the current branch
CHANGED_FILES=$(git -C "$REPO_ROOT" diff --name-only origin/main...HEAD 2>/dev/null) || exit 0

# Nothing staged yet — nothing to warn about
[[ -n "$CHANGED_FILES" ]] || exit 0

# Find non-test changes, excluding any Chart.yaml files themselves
NON_TEST=$(echo "$CHANGED_FILES" | grep -Ev '(chart/Chart\.yaml|_test\.(go|py)$)' | grep -Ev '^test_.*\.py$' || true)

if [[ -z "$NON_TEST" ]]; then
	cat >&2 <<-EOF
		WARNING: Bumping Chart.yaml when all branch changes appear to be test-only.

		Chart version bumps trigger an ArgoCD redeploy and pod restart.
		If no production code changed, skip the chart version bump.

		Branch changes so far:
		$(echo "$CHANGED_FILES" | head -10)

		If this bump is intentional (e.g. the chart itself changed), proceed.
		Otherwise, revert the version change in Chart.yaml.
	EOF
fi

exit 0
