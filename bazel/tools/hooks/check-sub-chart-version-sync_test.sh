#!/usr/bin/env bash
# Unit tests for check-sub-chart-version-sync.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 always (warning only, never blocks)
#   - Prints a WARNING to stderr when file_path matches a sub-chart Chart.yaml
#     (i.e. */chart/<subchartname>/Chart.yaml)
#   - Does NOT warn for top-level chart/Chart.yaml (no sub-chart dir level)
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-sub-chart-version-sync.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-sub-chart-version-sync.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-sub-chart-version-sync.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by check-sub-chart-version-sync.sh."""
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
# Tests
# ---------------------------------------------------------------------------

# 1. Completely empty JSON object → exit 0, no output
run_test "empty_json" \
	'{}' \
	0 ""

# 2. tool_input present but no file_path field → exit 0, no output
run_test "missing_file_path" \
	'{"tool_input":{}}' \
	0 ""

# 3. Top-level chart/Chart.yaml (no sub-chart dir) → NOT flagged by this hook
#    (handled by check-chart-version-sync.sh instead)
run_test "top_level_chart_yaml_not_flagged" \
	'{"tool_input":{"file_path":"/projects/myservice/chart/Chart.yaml"}}' \
	0 ""

# 4. Sub-chart Chart.yaml → WARNING on stderr
run_test "sub_chart_chart_yaml_warns" \
	'{"tool_input":{"file_path":"/projects/myservice/chart/mysubchart/Chart.yaml"}}' \
	0 "WARNING:"

# 5. Another sub-chart path → WARNING on stderr
run_test "nested_sub_chart_warns" \
	'{"tool_input":{"file_path":"/projects/platform/chart/subchart/Chart.yaml"}}' \
	0 "WARNING:"

# 6. Sub-chart values.yaml (not Chart.yaml) → no output
run_test "non_yaml_not_flagged" \
	'{"tool_input":{"file_path":"/projects/myservice/chart/subchart/values.yaml"}}' \
	0 ""

# 7. Deploy values.yaml (not under chart/) → no output
run_test "random_yaml_not_flagged" \
	'{"tool_input":{"file_path":"/projects/myservice/deploy/values.yaml"}}' \
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
