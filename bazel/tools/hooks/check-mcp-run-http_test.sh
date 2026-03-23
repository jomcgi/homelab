#!/usr/bin/env bash
# Unit tests for check-mcp-run-http.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 2 (BLOCK) when a .py file contains mcp.run( with transport="http" or transport='http'
#   - Exits 0 (allow) otherwise

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-mcp-run-http.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-mcp-run-http.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-mcp-run-http.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-mcp-run-http.sh."""
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

# (a) .py file with mcp.run(transport="http") is BLOCKED (double quotes)
run_test "write_py_mcp_run_http_double_quotes_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/backend/server.py","content":"mcp.run(transport=\"http\")"}}' \
	2 "BLOCK"

# (a) .py file with mcp.run(transport='"'"'http'"'"') is BLOCKED (single quotes)
run_test "write_py_mcp_run_http_single_quotes_blocked" \
	"$(printf '{"tool_input":{"file_path":"projects/myservice/backend/server.py","content":"mcp.run(transport='"'"'http'"'"')"}}')" \
	2 "BLOCK"

# (a) Edit tool: new_string with mcp.run http transport is BLOCKED
run_test "edit_py_mcp_run_http_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/backend/main.py","new_string":"mcp.run(mcp_server, transport=\"http\", port=8080)"}}' \
	2 "BLOCK"

# (b) .py file with mcp.run(transport="stdio") is NOT blocked
run_test "write_py_mcp_run_stdio_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/backend/server.py","content":"mcp.run(transport=\"stdio\")"}}' \
	0 ""

# (b) .py file using mcp.http_app() + uvicorn is NOT blocked
run_test "write_py_mcp_http_app_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/backend/server.py","content":"app = mcp.http_app()\nuvicorn.run(app, host=\"0.0.0.0\", port=8080)"}}' \
	0 ""

# (b) Non-.py file with mcp.run(transport="http") is NOT blocked
run_test "write_non_py_mcp_run_http_no_block" \
	'{"tool_input":{"file_path":"docs/mcp.md","content":"mcp.run(transport=\"http\") is not recommended"}}' \
	0 ""

# (c) Empty content does NOT block
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"projects/myapp/backend/server.py","content":""}}' \
	0 ""

# (c) No content field does NOT block
run_test "no_content_field" \
	'{"tool_input":{"file_path":"projects/myapp/backend/server.py"}}' \
	0 ""

# (c) Completely empty JSON does NOT block
run_test "empty_json" \
	'{}' \
	0 ""

# (d) Block message mentions http_app + uvicorn pattern
run_test "block_message_mentions_http_app" \
	'{"tool_input":{"file_path":"projects/myservice/backend/server.py","content":"mcp.run(transport=\"http\")"}}' \
	2 "http_app"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
