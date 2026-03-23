#!/usr/bin/env bash
# Unit tests for check-ebpf-otel-annotations.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 2 (BLOCK) when a deploy/values*.yaml or deploy/application.yaml
#     file contains instrumentation.opentelemetry.io/inject-* annotations
#   - Exits 0 (allow) otherwise

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-ebpf-otel-annotations.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-ebpf-otel-annotations.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-ebpf-otel-annotations.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly two expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-ebpf-otel-annotations.sh."""
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

# 1. values.yaml with inject-go annotation is BLOCKED
run_test "values_yaml_inject_go_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "BLOCK"

# 2. values.yaml with inject-java annotation is BLOCKED
run_test "values_yaml_inject_java_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"instrumentation.opentelemetry.io/inject-java: myservice-instrumentation"}}' \
	2 "BLOCK"

# 3. values-prod.yaml variant matches
run_test "values_prod_yaml_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values-prod.yaml","content":"instrumentation.opentelemetry.io/inject-python: \"true\""}}' \
	2 "BLOCK"

# 4. application.yaml with eBPF annotation is BLOCKED
run_test "application_yaml_inject_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "BLOCK"

# 5. Edit tool (new_string) in values.yaml is BLOCKED
run_test "edit_values_yaml_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","new_string":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "BLOCK"

# 6. values.yaml WITHOUT annotation is allowed
run_test "values_yaml_no_annotation_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"replicaCount: 2\nimage:\n  tag: latest"}}' \
	0 ""

# 7. Non-deploy file with annotation is NOT blocked (wrong path)
run_test "non_deploy_file_not_blocked" \
	'{"tool_input":{"file_path":"docs/ebpf-notes.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	0 ""

# 8. chart/templates file is NOT blocked (only deploy/ is checked)
run_test "chart_templates_not_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/chart/templates/deployment.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	0 ""

# 9. Empty content is NOT blocked
run_test "empty_content_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":""}}' \
	0 ""

# 10. No content field is NOT blocked
run_test "no_content_field_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml"}}' \
	0 ""

# 11. Empty JSON is NOT blocked
run_test "empty_json_allowed" \
	'{}' \
	0 ""

# 12. Block message mentions drop: ALL / SDK instrumentation
run_test "block_message_mentions_drop_all" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "drop.*ALL|SDK"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
