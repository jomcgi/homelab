#!/usr/bin/env bash
# Fast format script - builds tools once, runs in parallel
# Much faster than multirun which has bazel overhead per tool
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }
warn() { echo -e "${YELLOW}▶${NC} $1"; }

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

# Build all format tools in one shot (cached after first run)
log "Building tools..."
TARGETS=(
	@aspect_rules_lint//format:ruff
	@aspect_rules_lint//format:shfmt
	@buildifier_prebuilt//:buildifier
)

# Only build go/prettier if we need them
if [[ "$MODE" == "all" ]] || staged_matches '\.go$'; then
	TARGETS+=(@aspect_rules_lint//format:gofumpt)
fi
if [[ "$MODE" == "all" ]] || staged_matches '\.(js|jsx|ts|tsx|json|md|yaml|yml)$'; then
	TARGETS+=(//tools/format:prettier)
fi

bazel build "${TARGETS[@]}" 2>&1 | grep -v "^INFO:" || true

# Get binary paths via cquery (handles bzlmod naming)
get_bin() { bazel cquery --output=files "$1" 2>/dev/null | head -1; }

RUFF=$(get_bin @aspect_rules_lint//format:ruff)
SHFMT=$(get_bin @aspect_rules_lint//format:shfmt)
BUILDIFIER=$(get_bin @buildifier_prebuilt//:buildifier)

# Run formatters in parallel
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
	GOFUMPT=$(get_bin @aspect_rules_lint//format:gofumpt)
	(find . -name '*.go' -not -path './bazel-*' -not -path './.git/*' -print0 |
		xargs -0 "$GOFUMPT" -w 2>/dev/null || true) &
	PIDS+=($!)
fi

# Prettier (JS/TS/JSON/YAML/MD) - still needs bazel run for config
if [[ "$MODE" == "all" ]] || staged_matches '\.(js|jsx|ts|tsx|json|md|yaml|yml)$'; then
	bazel run //tools/format:prettier -- --write . 2>/dev/null &
	PIDS+=($!)
fi

# Wait for formatters
for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

# Generate scripts (fast, idempotent)
if [[ "$MODE" == "all" ]]; then
	log "Generating scripts..."
	bazel run //scripts:generate-push-all 2>&1 | grep -v "^INFO:" || true
	bazel run //scripts:generate-render-all 2>&1 | grep -v "^INFO:" || true
fi

log "Done!"
