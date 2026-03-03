#!/usr/bin/env bash
# Fast format script - builds tools once, runs in parallel
# Used by both pre-commit and CI for identical formatting
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }

# Build all format tools + script generators in one shot
log "Building tools..."
bazel build \
	@aspect_rules_lint//format:ruff \
	@aspect_rules_lint//format:shfmt \
	@aspect_rules_lint//format:gofumpt \
	@buildifier_prebuilt//:buildifier \
	//tools/format:prettier \
	//scripts:generate-push-all \
	//scripts:generate-push-all-pages \
	//scripts:generate-render-all \
	2>&1 | grep -v "^INFO:" || true

# Find binaries in bazel-bin (faster than cquery)
# -L follows symlinks (bazel-bin itself is a symlink)
# Use -perm /111 for GNU find (Linux) or -perm +111 for BSD find (macOS)
find_bin() {
	if find --version 2>/dev/null | grep -q GNU; then
		find -L bazel-bin -name "$1" -type f -perm /111 2>/dev/null | head -1
	else
		find -L bazel-bin -name "$1" -type f -perm +111 2>/dev/null | head -1
	fi
}

RUFF=$(find_bin ruff)
SHFMT=$(find_bin shfmt)
BUILDIFIER=$(find_bin buildifier)
PRETTIER=$(find_bin prettier)
GOFUMPT=$(find_bin gofumpt)

# Run formatters and script generators in parallel
log "Formatting..."
PIDS=()

# Python
"$RUFF" format . 2>/dev/null &
PIDS+=($!)

# Shell
(find . -name '*.sh' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
	xargs -0 "$SHFMT" -w 2>/dev/null || true) &
PIDS+=($!)

# Starlark (exclude worktrees — they have their own formatting)
(find . \( -name BUILD -o -name BUILD.bazel -o -name '*.bzl' -o -name WORKSPACE -o -name WORKSPACE.bazel \) \
	-not -path './bazel-*' -not -path './.claude/worktrees/*' -print0 |
	xargs -0 "$BUILDIFIER" 2>/dev/null || true) &
PIDS+=($!)

# Go
(find . -name '*.go' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
	xargs -0 "$GOFUMPT" -w 2>/dev/null || true) &
PIDS+=($!)

# Prettier (JS/TS/JSON/YAML/MD)
"$PRETTIER" --write . 2>/dev/null &
PIDS+=($!)

# Script generators (run in parallel with formatters)
$(find_bin generate-push-all) 2>/dev/null &
PIDS+=($!)
$(find_bin generate-push-all-pages) 2>/dev/null &
PIDS+=($!)
$(find_bin generate-render-all) &
PIDS+=($!)
# Wait for all parallel tasks
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

# Gazelle (generates BUILD files for Go/Python)
# Run after formatters complete since it needs formatted files
log "Running gazelle..."
bazel run //:gazelle 2>&1 | grep -v "^INFO:" || true

log "Done!"
