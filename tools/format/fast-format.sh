#!/usr/bin/env bash
# Fast format script - builds tools once, runs in parallel
# Much faster than multirun which has bazel overhead per tool
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }

# Check if any staged files match a pattern
staged_matches() {
	git diff --cached --name-only 2>/dev/null | grep -qE "$1" || return 1
}

# Determine mode: "staged" for pre-commit, "all" for full format
MODE="${1:-all}"
if [[ "$MODE" == "staged" ]]; then
	log "Pre-commit mode (staged files only)"
else
	log "Full format"
fi

# Build all format tools + script generators in one shot
log "Building tools..."
TARGETS=(
	@aspect_rules_lint//format:ruff
	@aspect_rules_lint//format:shfmt
	@buildifier_prebuilt//:buildifier
	//tools/format:prettier
)

if [[ "$MODE" == "all" ]] || staged_matches '\.go$'; then
	TARGETS+=(@aspect_rules_lint//format:gofumpt)
fi

if [[ "$MODE" == "all" ]]; then
	TARGETS+=(//scripts:generate-push-all //scripts:generate-push-all-pages //scripts:generate-render-all)
fi

bazel build "${TARGETS[@]}" 2>&1 | grep -v "^INFO:" || true

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

# Run formatters AND script generators in parallel
log "Formatting..."
PIDS=()

# Python
if [[ "$MODE" == "all" ]] || staged_matches '\.py$'; then
	"$RUFF" format . 2>/dev/null &
	PIDS+=($!)
fi

# Shell
if [[ "$MODE" == "all" ]] || staged_matches '\.(sh|bash)$'; then
	(find . -name '*.sh' -not -path './bazel-*' -not -path './.git/*' -print0 |
		xargs -0 "$SHFMT" -w 2>/dev/null || true) &
	PIDS+=($!)
fi

# Starlark
if [[ "$MODE" == "all" ]] || staged_matches '\.(bzl|BUILD|bazel)$'; then
	"$BUILDIFIER" -r . 2>/dev/null &
	PIDS+=($!)
fi

# Go
if [[ "$MODE" == "all" ]] || staged_matches '\.go$'; then
	GOFUMPT=$(find_bin gofumpt)
	(find . -name '*.go' -not -path './bazel-*' -not -path './.git/*' -print0 |
		xargs -0 "$GOFUMPT" -w 2>/dev/null || true) &
	PIDS+=($!)
fi

# Prettier (JS/TS/JSON/YAML/MD)
if [[ "$MODE" == "all" ]] || staged_matches '\.(js|jsx|ts|tsx|json|md|yaml|yml)$'; then
	"$PRETTIER" --write . 2>/dev/null &
	PIDS+=($!)
fi

# Script generators (run in parallel with formatters)
if [[ "$MODE" == "all" ]]; then
	$(find_bin generate-push-all) 2>/dev/null &
	PIDS+=($!)
	$(find_bin generate-push-all-pages) 2>/dev/null &
	PIDS+=($!)
	$(find_bin generate-render-all) &
	PIDS+=($!)
fi

# Wait for all parallel tasks
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

# Gazelle (generates BUILD files for Go/Python)
# Run after formatters complete since it needs formatted files
if [[ "$MODE" == "all" ]] || staged_matches '\.(go|py)$'; then
	log "Running gazelle..."
	bazel run //:gazelle 2>&1 | grep -v "^INFO:" || true
fi

log "Done!"
