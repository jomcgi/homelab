#!/bin/bash
# Consolidated PreToolUse hook for Write|Edit operations.
# Runs all checks in a single process with one jq parse.
#
# Checks:
#   1. plan-worktree: blocks plan/design file writes to the main worktree (exit 2)
#   2. chart-version-sync: warns when editing Chart.yaml without application.yaml (warning)
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow (warnings may be emitted on stderr)
# Exit 2: block the operation

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# No file path — nothing to check
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi

# ── Check 1: plan-worktree ──────────────────────────────────────────────
# Plans must be written in a linked worktree, not the main repo.
if [[ "$FILE_PATH" == *"/docs/plans/"* ]]; then
	DIR=$(dirname "$FILE_PATH")
	if [ ! -d "$DIR" ]; then
		DIR=$(dirname "$DIR")
		[ -d "$DIR" ] || { exit 0; }
	fi

	REPO_ROOT=$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null) || exit 0
	GIT_DIR=$(cd "$REPO_ROOT" && git rev-parse --absolute-git-dir 2>/dev/null) || exit 0
	GIT_COMMON_DIR=$(cd "$REPO_ROOT" && git rev-parse --git-common-dir 2>/dev/null) || exit 0

	# Normalize relative path
	if [[ "$GIT_COMMON_DIR" != /* ]]; then
		GIT_COMMON_DIR=$(cd "$REPO_ROOT" && cd "$GIT_COMMON_DIR" && pwd)
	fi

	if [[ "$GIT_DIR" == "$GIT_COMMON_DIR" ]]; then
		cat >&2 <<-EOF
			BLOCKED: Plan/design files must be written to a worktree, not the main repo.
			File: $FILE_PATH

			Create a worktree first, then save plans there:
			  git worktree add -b docs/<topic> /tmp/claude-worktrees/<topic> origin/main

			Then write to the worktree's docs/plans/ directory instead.
		EOF
		exit 2
	fi
fi

# ── Check 2: chart-version-sync ─────────────────────────────────────────
# Editing Chart.yaml without updating deploy/application.yaml targetRevision.
if [[ "$FILE_PATH" == */chart/Chart.yaml ]]; then
	SERVICE_DIR=$(dirname "$(dirname "$FILE_PATH")")
	APP_YAML="$SERVICE_DIR/deploy/application.yaml"

	if [[ -f "$APP_YAML" ]]; then
		REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || true)
		if [[ -n "$REPO_ROOT" ]]; then
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
		fi
	fi
fi

exit 0
