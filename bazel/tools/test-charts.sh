#!/usr/bin/env bash
# test-charts.sh - Validate all Helm charts with helm lint
#
# Usage: ./bazel/tools/test-charts.sh [chart-name]
#   If chart-name is provided, only that chart is tested
#   Otherwise, all charts in charts/ are tested
#
# When run via Bazel, uses HELM env var and BUILD_WORKSPACE_DIRECTORY

set -euo pipefail

# Support both direct invocation and Bazel execution
if [[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
	# Running via Bazel
	REPO_ROOT="$BUILD_WORKSPACE_DIRECTORY"
	CHARTS_DIR="$REPO_ROOT/charts"
	# Use helm from multitool if HELM is set
	if [[ -n "${HELM:-}" ]]; then
		# Export function so it's available in subshells
		HELM_BIN="$HELM"
		export HELM_BIN
	fi
else
	# Direct invocation
	SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
	REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
	CHARTS_DIR="$REPO_ROOT/charts"
fi

# Wrapper for helm command - uses HELM_BIN if set
run_helm() {
	if [[ -n "${HELM_BIN:-}" ]]; then
		"$HELM_BIN" "$@"
	else
		helm "$@"
	fi
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0
SKIPPED=0

log_info() {
	echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
	echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
	echo -e "${RED}[ERROR]${NC} $1"
}

lint_chart() {
	local chart_path="$1"
	local chart_name
	chart_name=$(basename "$chart_path")

	# Check if Chart.yaml exists
	if [[ ! -f "$chart_path/Chart.yaml" ]]; then
		log_warn "Skipping $chart_name: no Chart.yaml found"
		((SKIPPED++))
		return 0
	fi

	echo -n "Linting $chart_name... "

	# Run helm lint with strict mode
	local output
	if output=$(run_helm lint "$chart_path" --strict 2>&1); then
		echo -e "${GREEN}PASSED${NC}"
		((PASSED++))
		return 0
	else
		echo -e "${RED}FAILED${NC}"
		echo "$output" | sed 's/^/  /'
		((FAILED++))
		return 1
	fi
}

run_unittest() {
	local chart_path="$1"
	local chart_name
	chart_name=$(basename "$chart_path")
	local tests_dir="$chart_path/tests"

	# Check if tests directory exists
	if [[ ! -d "$tests_dir" ]]; then
		return 0
	fi

	# Check if helm-unittest plugin is installed
	if ! run_helm plugin list 2>/dev/null | grep -q unittest; then
		log_warn "helm-unittest plugin not installed, skipping unit tests for $chart_name"
		log_warn "Install with: helm plugin install https://github.com/helm-unittest/helm-unittest"
		return 0
	fi

	echo -n "Running unit tests for $chart_name... "

	local output
	if output=$(run_helm unittest "$chart_path" 2>&1); then
		echo -e "${GREEN}PASSED${NC}"
		return 0
	else
		echo -e "${RED}FAILED${NC}"
		echo "$output" | sed 's/^/  /'
		return 1
	fi
}

main() {
	log_info "Helm Chart Validation"
	echo ""

	# Check if helm is available
	if ! command -v run_helm &>/dev/null && [[ -z "${HELM_BIN:-}" ]] && ! command -v helm &>/dev/null; then
		log_error "helm is not installed or not in PATH"
		exit 1
	fi

	log_info "Using helm version: $(run_helm version --short)"
	echo ""

	# Determine which charts to test
	local charts_to_test=()

	if [[ $# -gt 0 ]]; then
		# Test specific chart
		local chart_path="$CHARTS_DIR/$1"
		if [[ -d "$chart_path" ]]; then
			charts_to_test+=("$chart_path")
		else
			log_error "Chart not found: $1"
			exit 1
		fi
	else
		# Test all charts
		for chart_path in "$CHARTS_DIR"/*/; do
			if [[ -d "$chart_path" ]]; then
				charts_to_test+=("$chart_path")
			fi
		done
	fi

	if [[ ${#charts_to_test[@]} -eq 0 ]]; then
		log_warn "No charts found in $CHARTS_DIR"
		exit 0
	fi

	log_info "Found ${#charts_to_test[@]} chart(s) to validate"
	echo ""

	# Phase 1: Lint all charts
	echo "=== Phase 1: Helm Lint ==="
	echo ""

	local lint_failed=0
	for chart_path in "${charts_to_test[@]}"; do
		if ! lint_chart "$chart_path"; then
			lint_failed=1
		fi
	done
	echo ""

	# Phase 2: Run unit tests (if available)
	echo "=== Phase 2: Unit Tests ==="
	echo ""

	local unittest_failed=0
	for chart_path in "${charts_to_test[@]}"; do
		if ! run_unittest "$chart_path"; then
			unittest_failed=1
		fi
	done
	echo ""

	# Summary
	echo "=== Summary ==="
	echo "  Passed:  $PASSED"
	echo "  Failed:  $FAILED"
	echo "  Skipped: $SKIPPED"
	echo ""

	if [[ $FAILED -gt 0 ]] || [[ $lint_failed -eq 1 ]] || [[ $unittest_failed -eq 1 ]]; then
		log_error "Some charts failed validation"
		exit 1
	fi

	log_info "All charts passed validation"
}

main "$@"
