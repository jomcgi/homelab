#!/bin/bash
# PreToolUse hook: warns when Chart.yaml version is bumped but only test files
# changed under chart/ or deploy/ — a chart version bump triggers a redeployment
# and is unnecessary if only test files were modified.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (warning only, never blocks)
# Exit 2: block (not used here)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check Chart.yaml files inside a chart/ or deploy/ directory
if [[ -z "$FILE_PATH" ]] || [[ "$FILE_PATH" != */Chart.yaml ]]; then
	exit 0
fi

if ! echo "$FILE_PATH" | grep -qE '/(chart|deploy)/Chart\.yaml$'; then
	exit 0
fi

# Extract new content: Edit tool uses new_string, Write tool uses content
NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
if [[ -z "$NEW_CONTENT" ]]; then
	NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
fi

if [[ -z "$NEW_CONTENT" ]]; then
	exit 0
fi

# Detect the new version value from the incoming content
NEW_VERSION=$(echo "$NEW_CONTENT" | grep -E '^version:' | head -1 | sed 's/^version:[[:space:]]*//' | tr -d '"'"'" || true)

if [[ -z "$NEW_VERSION" ]]; then
	exit 0
fi

# If the file already exists, check whether the version is actually changing
if [[ -f "$FILE_PATH" ]]; then
	OLD_VERSION=$(grep -E '^version:' "$FILE_PATH" 2>/dev/null | head -1 | sed 's/^version:[[:space:]]*//' | tr -d '"'"'" || true)
	if [[ "$OLD_VERSION" == "$NEW_VERSION" ]]; then
		# Version is not changing — no need to warn
		exit 0
	fi
fi

# Version is being bumped. Look for the repo root.
REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || true)
if [[ -z "$REPO_ROOT" ]]; then
	exit 0
fi

# Derive the service root: .../projects/<service>/chart/Chart.yaml
#                       -> .../projects/<service>
SERVICE_DIR=$(dirname "$(dirname "$FILE_PATH")")
SERVICE_DIR_REL="${SERVICE_DIR#$REPO_ROOT/}"
CHART_YAML_REL="${FILE_PATH#$REPO_ROOT/}"

# Collect all changed files under chart/ and deploy/ (staged, unstaged, working tree)
ALL_CHANGED=$(
	git -C "$REPO_ROOT" diff --cached --name-only -- \
		"${SERVICE_DIR_REL}/chart/" "${SERVICE_DIR_REL}/deploy/" 2>/dev/null || true
	git -C "$REPO_ROOT" diff --name-only HEAD -- \
		"${SERVICE_DIR_REL}/chart/" "${SERVICE_DIR_REL}/deploy/" 2>/dev/null || true
	git -C "$REPO_ROOT" status --porcelain -- \
		"${SERVICE_DIR_REL}/chart/" "${SERVICE_DIR_REL}/deploy/" 2>/dev/null \
		| awk '{print $NF}' || true
)

# Deduplicate, filter out the Chart.yaml itself and blank lines
CHANGED_FILES=""
if [[ -n "$ALL_CHANGED" ]]; then
	while IFS= read -r f; do
		[[ -z "$f" ]] && continue
		[[ "$f" == "$CHART_YAML_REL" ]] && continue
		CHANGED_FILES="${CHANGED_FILES:+$CHANGED_FILES$'\n'}$f"
	done < <(echo "$ALL_CHANGED" | sort -u)
fi

# If there are no other changed files, this may be a deliberate standalone bump
if [[ -z "$CHANGED_FILES" ]]; then
	exit 0
fi

# Check whether all changed files are test files
# Test patterns: *_test.py, *_test.go, *_test.ts, files under tests?/ fixtures?/ testdata/
NON_TEST_FILES=""
while IFS= read -r f; do
	[[ -z "$f" ]] && continue
	if ! echo "$f" | grep -qE '(_test\.(py|go|ts)$|/(tests?|fixtures?|testdata)/)'; then
		NON_TEST_FILES="${NON_TEST_FILES:+$NON_TEST_FILES$'\n'}$f"
	fi
done <<< "$CHANGED_FILES"

if [[ -z "$NON_TEST_FILES" ]]; then
	cat >&2 <<-EOF
		WARNING: Chart version bump detected but only test files changed.

		Chart bumps trigger redeployments — skip the version bump if no chart
		templates or values changed.
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
