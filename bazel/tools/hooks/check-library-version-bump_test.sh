#!/usr/bin/env bash
# Unit tests for check-library-version-bump.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Fires only when file_path matches */homelab-library/chart/Chart.yaml
#   - Checks new_string (Edit tool) or content (Write tool) for a version: line
#   - Prints WARNING to stderr when a version bump is detected
#   - Exits 0 always (warning only, never blocks)
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so the
# hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-library-version-bump.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-library-version-bump.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-library-version-bump.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses three expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.new_string // empty'
#   jq -r '.tool_input.content // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expressions used by check-library-version-bump.sh."""
import json, sys

args = sys.argv[1:]
raw = False
if args and args[0] == "-r":
    raw = True
    args = args[1:]

expr = args[0] if args else "."
data = json.load(sys.stdin)

def jq_eval(obj, expr):
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
    pass
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

# run_test NAME INPUT_JSON WANT_STDERR_RE
#   Hook always exits 0; WANT_STDERR_RE="" means no output expected.
run_test() {
	local name="$1"
	local input_json="$2"
	local want_stderr_re="$3"

	local stderr_out
	local got_exit=0
	stderr_out=$(printf '%s' "$input_json" | bash "$HOOK" 2>&1 >/dev/null) || got_exit=$?

	local ok=true

	if [[ "$got_exit" -ne 0 ]]; then
		echo "FAIL [$name]: unexpected exit $got_exit (hook should always exit 0)"
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
# Tests: paths that skip the hook entirely
# ---------------------------------------------------------------------------

# 1. Empty JSON -- no file_path, skipped
run_test "empty_json" \
	'{}' \
	""

# 2. tool_input present but no file_path -- skipped
run_test "missing_file_path" \
	'{"tool_input":{}}' \
	""

# 3. Different Chart.yaml (not homelab-library) -- skipped
run_test "other_chart_yaml_not_flagged" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/myservice/chart/Chart.yaml","new_string":"version: 1.2.3"}}' \
	""

# 4. homelab-library Chart.yaml but no version change in new_string -- no warning
run_test "library_chart_yaml_no_version_in_new_string" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/shared/helm/homelab-library/chart/Chart.yaml","new_string":"description: updated description"}}' \
	""

# 5. homelab-library Chart.yaml but no tool_input content at all -- no warning
run_test "library_chart_yaml_no_content" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/shared/helm/homelab-library/chart/Chart.yaml"}}' \
	""

# ---------------------------------------------------------------------------
# Tests: homelab-library Chart.yaml with version changes
# ---------------------------------------------------------------------------

# 6. Edit tool: new_string contains 'version:' -- WARNING emitted
run_test "edit_tool_version_bump_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/shared/helm/homelab-library/chart/Chart.yaml","new_string":"version: 0.5.0"}}' \
	"WARNING:"

# 7. Write tool: content contains 'version:' -- WARNING emitted
run_test "write_tool_version_bump_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/shared/helm/homelab-library/chart/Chart.yaml","content":"apiVersion: v2\nname: homelab-library\nversion: 0.5.0\n"}}' \
	"WARNING:"

# 8. Edit tool: new_string has version line mid-string (not line-start) -- no warning
#    (grep -E '^version:' matches only at start of line within the string)
run_test "edit_tool_version_not_at_line_start_no_warn" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/shared/helm/homelab-library/chart/Chart.yaml","new_string":"# not a version: bump"}}' \
	""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
