#!/usr/bin/env bash
# Unit tests for check-hardcoded-svc-url.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when content contains .svc.cluster.local
#     AND the file_path matches */values.yaml or */deploy/*.yaml

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-hardcoded-svc-url.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-hardcoded-svc-url.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-hardcoded-svc-url.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses two expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-hardcoded-svc-url.sh."""
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
# Tests
# ---------------------------------------------------------------------------

# (a) values.yaml with .svc.cluster.local triggers warning
run_test "write_values_yaml_svc_url_warns" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"url: http://svc.svc.cluster.local:8080"}}' \
	0 "svc.cluster.local"

# (a) deploy/*.yaml with .svc.cluster.local triggers warning
run_test "write_deploy_yaml_svc_url_warns" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/application.yaml","content":"targetURL: http://myapp.default.svc.cluster.local"}}' \
	0 "svc.cluster.local"

# (a) Edit tool: new_string in values.yaml triggers warning
run_test "edit_values_yaml_svc_url_warns" \
	'{"tool_input":{"file_path":"projects/auth/deploy/values.yaml","new_string":"upstream: http://auth-svc.prod.svc.cluster.local:9090"}}' \
	0 "svc.cluster.local"

# (b) Non-deploy file with .svc.cluster.local does NOT trigger warning
run_test "write_go_file_svc_url_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.go","content":"// url: http://svc.svc.cluster.local"}}' \
	0 ""

# (b) README with .svc.cluster.local does NOT trigger warning
run_test "write_readme_svc_url_no_warn" \
	'{"tool_input":{"file_path":"docs/services.md","content":"Service is at http://myapp.default.svc.cluster.local"}}' \
	0 ""

# (b) values.yaml WITHOUT .svc.cluster.local does NOT trigger warning
run_test "write_values_yaml_no_svc_url" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"replicaCount: 1\nimage: myapp:latest"}}' \
	0 ""

# (c) Empty content does NOT trigger warning
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":""}}' \
	0 ""

# (c) No content field does NOT trigger warning
run_test "no_content_field" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml"}}' \
	0 ""

# (c) Completely empty JSON does NOT trigger warning
run_test "empty_json" \
	'{}' \
	0 ""

# (d) Warning message mentions values.yaml guidance
run_test "warning_mentions_values_yaml" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"url: http://myapp.default.svc.cluster.local"}}' \
	0 "values.yaml"

# (e) chart/values.yaml (not in deploy/) still matches */values.yaml pattern
run_test "chart_values_yaml_svc_url_warns" \
	'{"tool_input":{"file_path":"projects/myapp/chart/values.yaml","content":"upstream: http://svc.default.svc.cluster.local"}}' \
	0 "svc.cluster.local"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
