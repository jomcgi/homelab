#!/usr/bin/env bash
# Unit tests for check-generic-test-filename.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Only inspects files whose path ends in _test.py or _test.go
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when the basename contains a vague keyword:
#       coverage, gaps, remaining, final_, new_, identified
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-generic-test-filename.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-generic-test-filename.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-generic-test-filename.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly one expression:
#   jq -r '.tool_input.file_path // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expression used by check-generic-test-filename.sh."""
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
# Tests — flagged (generic) names: should warn
# ---------------------------------------------------------------------------

# 1. coverage_test.py → warning (generic coverage label)
run_test "coverage_test_py_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/coverage_test.py"}}' \
	0 "Generic test file name"

# 2. gaps_test.py → warning
run_test "gaps_test_py_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/gaps_test.py"}}' \
	0 "Generic test file name"

# 3. remaining_test.py → warning
run_test "remaining_test_py_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/remaining_test.py"}}' \
	0 "Generic test file name"

# 4. final_auth_test.go → warning (has "final_" prefix)
run_test "final_prefix_test_go_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/final_auth_test.go"}}' \
	0 "Generic test file name"

# 5. new_service_test.go → warning (has "new_" prefix)
run_test "new_prefix_test_go_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/new_service_test.go"}}' \
	0 "Generic test file name"

# 6. identified_issues_test.py → warning
run_test "identified_test_py_warns" \
	'{"tool_input":{"file_path":"projects/myapp/tests/identified_issues_test.py"}}' \
	0 "Generic test file name"

# 7. coverage_test.go (Go variant of coverage) → warning
run_test "coverage_test_go_warns" \
	'{"tool_input":{"file_path":"projects/myapp/coverage_test.go"}}' \
	0 "Generic test file name"

# 8. remaining_gaps_test.go → warning (both keywords; either triggers)
run_test "remaining_gaps_test_go_warns" \
	'{"tool_input":{"file_path":"projects/myapp/remaining_gaps_test.go"}}' \
	0 "Generic test file name"

# ---------------------------------------------------------------------------
# Tests — allowed (specific) names: should NOT warn
# ---------------------------------------------------------------------------

# 9. auth_test.go → no warning (meaningful name)
run_test "auth_test_go_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/auth_test.go"}}' \
	0 ""

# 10. payment_processor_test.py → no warning
run_test "payment_processor_test_py_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/tests/payment_processor_test.py"}}' \
	0 ""

# 11. user_service_test.go → no warning
run_test "user_service_test_go_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/user_service_test.go"}}' \
	0 ""

# 12. Non-test .go file → not inspected (no warning)
run_test "regular_go_file_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/main.go"}}' \
	0 ""

# 13. Non-test .py file → not inspected (no warning)
run_test "regular_py_file_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/coverage_handler.py"}}' \
	0 ""

# 14. No file_path field → exit 0, no output
run_test "no_file_path_no_warn" \
	'{"tool_input":{"content":"some content"}}' \
	0 ""

# 15. Completely empty JSON → exit 0, no output
run_test "empty_json_no_warn" \
	'{}' \
	0 ""

# 16. YAML file with "gaps" in name → not a test file, no warning
run_test "yaml_gaps_file_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/gaps.yaml"}}' \
	0 ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
