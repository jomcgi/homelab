#!/usr/bin/env bash
# CI validation: cross-check grep-based generate scripts against bazel query output.
# This ensures the grep approximations haven't drifted from the actual Bazel build graph.
#
# Only intended to run in CI where Bazel is available.
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

FAILED=0
TMPDIR_VALIDATE=$(mktemp -d)
trap 'rm -rf "$TMPDIR_VALIDATE"' EXIT

# --- Helper functions ---

extract_targets_from_build() {
	# Extract "//..." target labels from a generated BUILD file
	local build_file="$1"
	grep -o '"//[^"]*"' "$build_file" | tr -d '"' | grep -v '//visibility:\|//:__subpackages__\|//:__pkg__' | LC_ALL=C sort
}

compare_targets() {
	local name="$1"
	local grep_file="$2"
	local query_file="$3"

	if diff -u "$query_file" "$grep_file" >"$TMPDIR_VALIDATE/diff_${name}" 2>&1; then
		echo "  ${name}: PASS"
	else
		echo "  ${name}: FAIL"
		echo "    The grep-based generate script output differs from bazel query."
		echo "    Diff (- = bazel query / expected, + = grep script / actual):"
		sed 's/^/    /' "$TMPDIR_VALIDATE/diff_${name}"
		echo ""
		FAILED=1
	fi
}

# --- Validation 1: generate-push-all.sh ---

echo "Validating generate-push-all.sh ..."

# Run the grep-based script (it writes bazel/images/BUILD)
bash bazel/images/generate-push-all.sh

# Extract targets from the generated BUILD file
extract_targets_from_build bazel/images/BUILD >"$TMPDIR_VALIDATE/push_all_grep.txt"

# Run equivalent bazel queries
{
	bazel query 'kind("oci_push", //...)' 2>/dev/null
	bazel query 'kind("helm_push", //...)' 2>/dev/null
} | LC_ALL=C sort >"$TMPDIR_VALIDATE/push_all_query.txt"

compare_targets "push-all" "$TMPDIR_VALIDATE/push_all_grep.txt" "$TMPDIR_VALIDATE/push_all_query.txt"

# --- Validation 2: generate-push-all-pages.sh ---

echo "Validating generate-push-all-pages.sh ..."

# Run the grep-based script (it writes projects/websites/BUILD)
bash bazel/images/generate-push-all-pages.sh

# Extract targets from the generated BUILD file
extract_targets_from_build projects/websites/BUILD >"$TMPDIR_VALIDATE/push_pages_grep.txt"

# Run equivalent bazel query
bazel query 'kind("wrangler_pages_push", //...)' 2>/dev/null |
	LC_ALL=C sort >"$TMPDIR_VALIDATE/push_pages_query.txt"

compare_targets "push-all-pages" "$TMPDIR_VALIDATE/push_pages_grep.txt" "$TMPDIR_VALIDATE/push_pages_query.txt"

# --- Summary ---

echo ""
if [ "$FAILED" -ne 0 ]; then
	echo "VALIDATION FAILED"
	echo ""
	echo "One or more generate scripts produced output that differs from bazel query."
	echo "This means the grep-based heuristics have drifted from the actual build graph."
	echo ""
	echo "To fix:"
	echo "  1. Check which BUILD files changed (new targets added/removed/renamed)"
	echo "  2. Update the corresponding generate script in bazel/images/ to match"
	echo "  3. Re-run 'format' to regenerate the BUILD files"
	echo "  4. Verify locally with: bash bazel/images/validate-generate-scripts.sh"
	exit 1
fi

echo "ALL VALIDATIONS PASSED"
