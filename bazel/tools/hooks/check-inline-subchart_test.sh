#!/usr/bin/env bash
# Unit tests for check-inline-subchart.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 (warning) when Chart.yaml is nested inside a chart dir whose
#     subdirectory is not declared as a file:// dependency in the parent Chart.yaml
#   - Exits 0 (silent) otherwise — it never blocks

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-inline-subchart.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-inline-subchart.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-inline-subchart.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-inline-subchart.sh."""
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
# Set up a fake chart directory in TEST_TMPDIR
# ---------------------------------------------------------------------------
FAKE_CHART_DIR="${TEST_TMPDIR}/projects/myservice/chart"
mkdir -p "${FAKE_CHART_DIR}/memgraph"

# Parent Chart.yaml WITHOUT memgraph as a file:// dependency
cat >"${FAKE_CHART_DIR}/Chart.yaml" <<'CHART_NO_DEP'
apiVersion: v2
name: myservice
version: 1.0.0
dependencies: []
CHART_NO_DEP

# Parent Chart.yaml WITH memgraph declared as a file:// dependency
FAKE_CHART_DIR_WITH_DEP="${TEST_TMPDIR}/projects/myservice-with-dep/chart"
mkdir -p "${FAKE_CHART_DIR_WITH_DEP}/memgraph"
cat >"${FAKE_CHART_DIR_WITH_DEP}/Chart.yaml" <<'CHART_WITH_DEP'
apiVersion: v2
name: myservice
version: 1.0.0
dependencies:
  - name: memgraph
    version: "*"
    repository: "file://memgraph"
CHART_WITH_DEP

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

run_test() {
	local name="$1"
	local input_json="$2"
	local want_exit="$3"
	local want_stderr_re="$4"

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

# (a) Nested Chart.yaml without file:// dep in parent → WARNING
run_test "nested_chart_no_dep_warns" \
	"{\"tool_input\":{\"file_path\":\"${TEST_TMPDIR}/projects/myservice/chart/memgraph/Chart.yaml\"}}" \
	0 "WARNING"

# (b) Nested Chart.yaml with file:// dep declared in parent → silent
run_test "nested_chart_with_dep_silent" \
	"{\"tool_input\":{\"file_path\":\"${TEST_TMPDIR}/projects/myservice-with-dep/chart/memgraph/Chart.yaml\"}}" \
	0 ""

# (c) Top-level chart/Chart.yaml (not nested) → silent
run_test "top_level_chart_yaml_silent" \
	'{"tool_input":{"file_path":"projects/myservice/chart/Chart.yaml"}}' \
	0 ""

# (d) Non-Chart.yaml file → silent
run_test "non_chart_yaml_silent" \
	'{"tool_input":{"file_path":"projects/myservice/chart/memgraph/values.yaml"}}' \
	0 ""

# (e) Empty file path → silent
run_test "empty_file_path_silent" \
	'{"tool_input":{"file_path":""}}' \
	0 ""

# (f) No file_path field → silent
run_test "no_file_path_silent" \
	'{"tool_input":{}}' \
	0 ""

# (g) Completely empty JSON → silent
run_test "empty_json_silent" \
	'{}' \
	0 ""

# (h) Nested Chart.yaml with no parent Chart.yaml → silent (not a standard layout)
run_test "nested_chart_no_parent_silent" \
	'{"tool_input":{"file_path":"/nonexistent/chart/subdir/Chart.yaml"}}' \
	0 ""

# (i) Warning message mentions the subdirectory name
run_test "warning_mentions_subdir_name" \
	"{\"tool_input\":{\"file_path\":\"${TEST_TMPDIR}/projects/myservice/chart/memgraph/Chart.yaml\"}}" \
	0 "memgraph"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
