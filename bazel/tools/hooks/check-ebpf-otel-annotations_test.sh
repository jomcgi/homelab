#!/usr/bin/env bash
# Unit tests for check-ebpf-otel-annotations.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 2 (BLOCK) when content contains instrumentation.opentelemetry.io/inject-
#     AND the file_path matches deploy files
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

# (a) values.yaml with inject-go annotation is BLOCKED
run_test "write_values_yaml_ebpf_go_blocked" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"annotations:\n  instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "BLOCK"

# (a) application.yaml with inject-python annotation is BLOCKED
run_test "write_deploy_yaml_ebpf_python_blocked" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/application.yaml","content":"annotations:\n  instrumentation.opentelemetry.io/inject-python: myns/my-instrumentation"}}' \
	2 "BLOCK"

# (a) Edit tool: new_string with eBPF annotation in values.yaml is BLOCKED
run_test "edit_values_yaml_ebpf_blocked" \
	'{"tool_input":{"file_path":"projects/auth/deploy/values.yaml","new_string":"instrumentation.opentelemetry.io/inject-nodejs: \"true\""}}' \
	2 "BLOCK"

# (b) Non-deploy file with eBPF annotation is NOT blocked
run_test "write_go_file_ebpf_no_block" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.go","content":"// instrumentation.opentelemetry.io/inject-go: true"}}' \
	0 ""

# (b) README with eBPF annotation is NOT blocked
run_test "write_readme_ebpf_no_block" \
	'{"tool_input":{"file_path":"docs/observability.md","content":"The instrumentation.opentelemetry.io/inject-go annotation is not supported"}}' \
	0 ""

# (b) values.yaml WITHOUT eBPF annotation is NOT blocked
run_test "write_values_yaml_no_ebpf" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"replicaCount: 1\nimage: myapp:latest"}}' \
	0 ""

# (c) Empty content does NOT block
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":""}}' \
	0 ""

# (c) No content field does NOT block
run_test "no_content_field" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml"}}' \
	0 ""

# (c) Completely empty JSON does NOT block
run_test "empty_json" \
	'{}' \
	0 ""

# (d) Block message mentions drop: ALL context
run_test "block_message_mentions_drop_all" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"instrumentation.opentelemetry.io/inject-go: \"true\""}}' \
	2 "drop.*ALL|ALL.*drop"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
