#!/usr/bin/env bash
# Unit tests for check-stale-repo-paths.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.content (Write) or
#     .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when content contains stale paths:
#       overlays/prod/
#       //services/[a-z]
#       //charts/[a-z]
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-stale-repo-paths.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-stale-repo-paths.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-stale-repo-paths.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly one expression:
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expression used by check-stale-repo-paths.sh."""
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

# (a) Content with 'overlays/prod/' triggers warning
run_test "write_overlays_prod_warns" \
	'{"tool_input":{"file_path":"foo.yaml","content":"path: overlays/prod/values.yaml"}}' \
	0 "overlays/prod"

# (a) Edit tool: new_string with 'overlays/prod/' triggers warning
run_test "edit_overlays_prod_warns" \
	'{"tool_input":{"file_path":"bar.yaml","new_string":"kustomize overlays/prod/ apply"}}' \
	0 "overlays/prod"

# (a) Content with '//services/<name>' triggers warning
run_test "write_services_path_warns" \
	'{"tool_input":{"file_path":"BUILD","content":"deps = [\"//services/auth:lib\"]"}}' \
	0 "//services"

# (a) Content with '//charts/<name>' triggers warning
run_test "write_charts_path_warns" \
	'{"tool_input":{"file_path":"BUILD","content":"deps = [\"//charts/ingress:chart\"]"}}' \
	0 "//charts"

# (b) Content with 'projects/trips/deploy/' does NOT trigger warning
run_test "write_projects_deploy_no_warn" \
	'{"tool_input":{"file_path":"foo.yaml","content":"path: projects/trips/deploy/values.yaml"}}' \
	0 ""

# (b) Content with valid Bazel path //projects/ does NOT trigger warning
run_test "write_projects_bazel_no_warn" \
	'{"tool_input":{"file_path":"BUILD","content":"deps = [\"//projects/auth:lib\"]"}}' \
	0 ""

# (c) Empty content does NOT trigger warning
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"foo.yaml","content":""}}' \
	0 ""

# (c) No content fields at all does NOT trigger warning
run_test "no_content_fields" \
	'{"tool_input":{"file_path":"foo.yaml"}}' \
	0 ""

# (c) Completely empty JSON does NOT trigger warning
run_test "empty_json" \
	'{}' \
	0 ""

# Warning message suggests correct projects/<service>/ path
run_test "overlays_prod_suggests_projects" \
	'{"tool_input":{"file_path":"baz.yaml","content":"overlays/prod/kustomization.yaml"}}' \
	0 "projects/"

# //charts/ uppercase C does not match (pattern is lowercase [a-z])
run_test "charts_uppercase_no_warn" \
	'{"tool_input":{"file_path":"BUILD","content":"//Charts/foo"}}' \
	0 ""

# //services/ uppercase S does not match (pattern is lowercase [a-z])
run_test "services_uppercase_no_warn" \
	'{"tool_input":{"file_path":"BUILD","content":"//Services/foo"}}' \
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
