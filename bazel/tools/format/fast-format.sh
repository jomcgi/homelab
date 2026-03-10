#!/usr/bin/env bash
# Fast format script - runs all formatters in parallel using standalone binaries
# Used by both pre-commit and CI for identical formatting
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

# Ensure .tools/bin is on PATH (pre-commit doesn't run through direnv)
if [[ -d "$PWD/.tools/bin" ]]; then
	export PATH="$PWD/.tools/bin:$PATH"
fi

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1" >&2; }

# Verify required tools exist
# buildifier and gazelle are CI-only (run via Bazel)
MISSING=()
for tool in ruff shfmt prettier gofumpt; do
	if ! command -v "$tool" &>/dev/null; then
		MISSING+=("$tool")
	fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
	err "Missing tools: ${MISSING[*]}"
	err "Run './bootstrap.sh' to install dev tools"
	err "In a worktree? Run 'direnv allow' to symlink tools from the main repo"
	exit 1
fi

# Run formatters and script generators in parallel
log "Formatting..."
PIDS=()

# Python
ruff format . 2>/dev/null &
PIDS+=($!)

# Shell
(find . -name '*.sh' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
	xargs -0 shfmt -w 2>/dev/null || true) &
PIDS+=($!)

# Starlark — buildifier is optional (CI provides it via Bazel)
if command -v buildifier &>/dev/null; then
	(find . \( -name BUILD -o -name BUILD.bazel -o -name '*.bzl' -o -name WORKSPACE -o -name WORKSPACE.bazel \) \
		-not -path './bazel-*' -not -path './.claude/worktrees/*' -print0 |
		xargs -0 buildifier 2>/dev/null || true) &
	PIDS+=($!)
fi

# Go
(find . -name '*.go' -not -path './bazel-*' -not -path './.git/*' -not -path './.claude/worktrees/*' -print0 |
	xargs -0 gofumpt -w 2>/dev/null || true) &
PIDS+=($!)

# Prettier (JS/TS/JSON/YAML/MD)
prettier --write . 2>/dev/null &
PIDS+=($!)

# Script generators (run in parallel with formatters)
./scripts/generate-push-all.sh 2>/dev/null &
PIDS+=($!)
./scripts/generate-push-all-pages.sh 2>/dev/null &
PIDS+=($!)

# Wait for all parallel tasks
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

# Gazelle (generates BUILD files for Go/Python)
# Run after formatters complete since it needs formatted files
# SKIP_GAZELLE=1 allows CI to use bazel run //:gazelle instead
if [ "${SKIP_GAZELLE:-0}" != "1" ]; then
	log "Running gazelle..."
	gazelle 2>/dev/null || true
fi

log "Done!"
