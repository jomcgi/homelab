#!/usr/bin/env bash
# Unit tests for check-bdd-shared-testing-dep.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path (and optionally .tool_input.content)
#   - Exits 0 always (warning-only, never blocks)
#   - Emits a WARNING on stderr when a BUILD file references shared.testing.plugin
#     without :shared_testing in deps
#   - Skips non-BUILD files and files without shared.testing.plugin

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-bdd-shared-testing-dep.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-bdd-shared-testing-dep.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-bdd-shared-testing-dep.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly two expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-bdd-shared-testing-dep.sh."""
import json, sys

args = sys.argv[1:]
raw = False
if args and args[0] == "-r":
    raw = True
    args = args[1:]

expr = args[0] if args else "."
data = json.load(sys.stdin)

def jq_eval(obj, expr):
    """Evaluate '.a.b // .c.d // empty' style expressions."""
    for alt in expr.split("//"):
        alt = alt.strip()
        if alt == "empty":
            return None
        keys = [k for k in alt.lstrip(".").split(".") if k]
        val = obj
        try:
            for k in keys:
                val = val[k] if isinstance(val, dict) else None
                if val is None:
                    break
        except (KeyError, TypeError):
            val = None
        if val is not None:
            return val
    return None

result = jq_eval(data, expr)
if result is None:
    pass  # empty — print nothing
elif raw:
    print(result)
else:
    print(json.dumps(result))
JQ_STUB
chmod +x "${TEST_TMPDIR}/bin/jq"
export PATH="${TEST_TMPDIR}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Temp directory for BUILD file fixtures
# ---------------------------------------------------------------------------
BUILDS_DIR="${TEST_TMPDIR}/builds"
mkdir -p "$BUILDS_DIR"

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

run_test() {
	local name="$1"
	local input_json="$2"
	local want_exit="$3"      # expected exit code (always 0 for this hook)
	local want_stderr_re="$4" # regex that must match stderr (empty = no output expected)

	local stderr_out
	local got_exit=0
	stderr_out=$(printf '%s' "$input_json" | bash "$HOOK" 2>&1 >/dev/null) || got_exit=$?

	local ok=true

	if [[ "$got_exit" -ne "$want_exit" ]]; then
		echo "FAIL [$name]: exit $got_exit, want $want_exit"
		ok=false
	fi

	if [[ -n "$want_stderr_re" ]]; then
		if ! echo "$stderr_out" | grep -qE "$want_stderr_re"; then
			echo "FAIL [$name]: stderr $(printf '%q' "$stderr_out") did not match /$want_stderr_re/"
			ok=false
		fi
	else
		if [[ -n "$stderr_out" ]]; then
			echo "FAIL [$name]: unexpected stderr: $(printf '%q' "$stderr_out")"
			ok=false
		fi
	fi

	if $ok; then
		echo "PASS [$name]"
		PASS=$((PASS + 1))
	else
		FAIL=$((FAIL + 1))
	fi
}

# ---------------------------------------------------------------------------
# Tests using actual temp files (hook reads file when no content field)
# ---------------------------------------------------------------------------

# 1. BUILD file with shared.testing.plugin but no :shared_testing dep → warns
cat >"$BUILDS_DIR/missing_dep_BUILD" <<'EOF'
py_test(
    name = "test_suite",
    srcs = glob(["**/*_test.py"]),
    env = {
        "PYTEST_ADDOPTS": "-p shared.testing.plugin",
    },
)
EOF
run_test "missing_shared_testing_dep_warns" \
	"{\"tool_input\":{\"file_path\":\"$BUILDS_DIR/missing_dep_BUILD\"}}" \
	0 "WARNING.*shared_testing"

# 2. BUILD file with both shared.testing.plugin and :shared_testing dep → no warning
cat >"$BUILDS_DIR/has_dep_BUILD" <<'EOF'
py_test(
    name = "test_suite",
    srcs = glob(["**/*_test.py"]),
    env = {
        "PYTEST_ADDOPTS": "-p shared.testing.plugin",
    },
    deps = [
        ":shared_testing",
        "//other:dep",
    ],
)
EOF
run_test "has_shared_testing_dep_no_warning" \
	"{\"tool_input\":{\"file_path\":\"$BUILDS_DIR/has_dep_BUILD\"}}" \
	0 ""

# 3. Non-BUILD file → skip even if content references shared.testing.plugin
cat >"$BUILDS_DIR/conftest.py" <<'EOF'
pytest_plugins = ["shared.testing.plugin"]
EOF
run_test "non_build_file_skipped" \
	"{\"tool_input\":{\"file_path\":\"$BUILDS_DIR/conftest.py\"}}" \
	0 ""

# 4. BUILD file without shared.testing.plugin → no warning
cat >"$BUILDS_DIR/plain_BUILD" <<'EOF'
py_test(
    name = "test_suite",
    srcs = glob(["**/*_test.py"]),
    deps = [":some_dep"],
)
EOF
run_test "no_plugin_no_warning" \
	"{\"tool_input\":{\"file_path\":\"$BUILDS_DIR/plain_BUILD\"}}" \
	0 ""

# 5. Empty JSON (no tool_input) → skip
run_test "empty_json_allowed" \
	'{}' \
	0 ""

# 6. BUILD.bazel filename variant — also checked
cat >"$BUILDS_DIR/missing_dep_BUILD.bazel" <<'EOF'
py_test(
    name = "test_suite",
    srcs = ["test.py"],
    env = {"PYTEST_ADDOPTS": "-p shared.testing.plugin"},
)
EOF
run_test "build_bazel_filename_warns" \
	"{\"tool_input\":{\"file_path\":\"$BUILDS_DIR/missing_dep_BUILD.bazel\"}}" \
	0 "WARNING.*shared_testing"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
