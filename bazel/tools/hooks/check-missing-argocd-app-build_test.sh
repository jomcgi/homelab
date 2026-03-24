#!/usr/bin/env bash
# Unit tests for check-missing-argocd-app-build.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 (warning) when:
#     - the file is under a */deploy/ directory
#     - application.yaml exists in that deploy dir
#     - Chart.yaml exists in the sibling chart/ directory
#     - AND the BUILD file is missing or lacks an argocd_app rule
#   - Exits 0 (silent) otherwise — it never blocks
#
# Because the hook checks the real filesystem, tests create temp dirs.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-missing-argocd-app-build.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-missing-argocd-app-build.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-missing-argocd-app-build.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-missing-argocd-app-build.sh."""
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
# Setup: create a temp service directory structure
# Layout:
#   $SVCDIR/
#     chart/Chart.yaml
#     deploy/application.yaml
#     deploy/values.yaml    ← the file being written
#     deploy/BUILD          ← present or absent depending on test
# ---------------------------------------------------------------------------
SVCDIR="${TEST_TMPDIR}/myservice"
mkdir -p "${SVCDIR}/chart"
mkdir -p "${SVCDIR}/deploy"
echo "apiVersion: v2" >"${SVCDIR}/chart/Chart.yaml"
echo "kind: Application" >"${SVCDIR}/deploy/application.yaml"

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# (a) deploy dir has Chart.yaml + application.yaml but no BUILD → WARNING
run_test "missing_build_file_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR}/deploy/values.yaml\"}}" \
	0 "WARNING"

# (b) BUILD file exists but lacks argocd_app → WARNING
echo "# empty BUILD" >"${SVCDIR}/deploy/BUILD"
run_test "build_without_argocd_app_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR}/deploy/values.yaml\"}}" \
	0 "WARNING"

# (c) BUILD file with argocd_app rule → silent
echo 'argocd_app(name = "myservice")' >"${SVCDIR}/deploy/BUILD"
run_test "build_with_argocd_app_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR}/deploy/values.yaml\"}}" \
	0 ""

# (d) File not under deploy/ → silent
run_test "non_deploy_path_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR}/values.yaml\"}}" \
	0 ""

# (e) deploy dir without application.yaml → silent
SVCDIR2="${TEST_TMPDIR}/noapp"
mkdir -p "${SVCDIR2}/chart"
mkdir -p "${SVCDIR2}/deploy"
echo "apiVersion: v2" >"${SVCDIR2}/chart/Chart.yaml"
# No application.yaml created
run_test "no_application_yaml_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR2}/deploy/values.yaml\"}}" \
	0 ""

# (f) deploy dir without chart/Chart.yaml → silent
SVCDIR3="${TEST_TMPDIR}/nochart"
mkdir -p "${SVCDIR3}/deploy"
echo "kind: Application" >"${SVCDIR3}/deploy/application.yaml"
# No chart/Chart.yaml created
run_test "no_chart_yaml_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR3}/deploy/values.yaml\"}}" \
	0 ""

# (g) Empty JSON → silent
run_test "empty_json_silent" \
	'{}' \
	0 ""

# (h) No file_path field → silent
run_test "no_file_path_silent" \
	'{"tool_input":{}}' \
	0 ""

# (i) Warning message mentions BUILD and argocd_app
rm -f "${SVCDIR}/deploy/BUILD"
run_test "warning_mentions_build_and_argocd_app" \
	"{\"tool_input\":{\"file_path\":\"${SVCDIR}/deploy/values.yaml\"}}" \
	0 "BUILD"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
