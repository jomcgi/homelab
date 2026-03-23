#!/usr/bin/env bash
# Unit tests for check-empty-1password-itempath.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 2 (BLOCK) when a deploy/values*.yaml file contains an empty itemPath
#   - Exits 0 (allow) otherwise

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-empty-1password-itempath.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-empty-1password-itempath.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-empty-1password-itempath.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-empty-1password-itempath.sh."""
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

# (a) values.yaml with empty itemPath (bare empty) is BLOCKED
run_test "write_values_empty_itempath_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"secret:\n  itemPath: \"\""}}' \
	2 "BLOCK"

# (a) values.yaml with itemPath followed by nothing is BLOCKED
run_test "write_values_bare_itempath_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"secret:\n  itemPath:"}}' \
	2 "BLOCK"

# (a) values-prod.yaml with empty itemPath is BLOCKED
run_test "write_values_prod_empty_itempath_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values-prod.yaml","content":"secret:\n  itemPath: \"\""}}' \
	2 "BLOCK"

# (a) Edit tool: new_string with empty itemPath is BLOCKED
run_test "edit_values_empty_itempath_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","new_string":"  itemPath: \"\""}}' \
	2 "BLOCK"

# (b) values.yaml with a real itemPath is NOT blocked
run_test "write_values_real_itempath_allowed" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"secret:\n  itemPath: \"vaults/My Vault/items/my-secret\""}}' \
	0 ""

# (b) Non-values file with empty itemPath is NOT blocked
run_test "write_non_values_file_not_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"itemPath: \"\""}}' \
	0 ""

# (b) Python file with itemPath: "" is NOT blocked (not a values.yaml)
run_test "write_py_file_not_blocked" \
	'{"tool_input":{"file_path":"projects/myservice/backend/main.py","content":"itemPath: \"\""}}' \
	0 ""

# (c) Empty content does NOT block
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":""}}' \
	0 ""

# (c) No content field does NOT block
run_test "no_content_field" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml"}}' \
	0 ""

# (c) Completely empty JSON does NOT block
run_test "empty_json" \
	'{}' \
	0 ""

# (d) Block message mentions itemPath and 1Password
run_test "block_message_mentions_itempath" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"itemPath: \"\""}}' \
	2 "itemPath"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
