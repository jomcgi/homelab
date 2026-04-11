#!/usr/bin/env bash
# Unit tests for check-batch-session-add.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when a Python file contains session.add()
#     inside a for/while loop body AND has no begin_nested() call

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-batch-session-add.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-batch-session-add.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-batch-session-add.sh in runfiles" >&2
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
"""Minimal jq stub covering expressions used by check-batch-session-add.sh."""
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

# (a) Python file with for loop + session.add() + no begin_nested → warns
run_test "python_for_loop_session_add_warns" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":"for item in items:\n    session.add(MyModel(data=item))\nsession.commit()"}}' \
	0 "begin_nested"

# (a) Python file with while loop + session.add() + no begin_nested → warns
run_test "python_while_loop_session_add_warns" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/raw_ingest.py","content":"while queue:\n    obj = queue.pop()\n    session.add(obj)\nsession.commit()"}}' \
	0 "begin_nested"

# (b) Python file with for loop + session.add() + begin_nested → no warn
run_test "python_for_loop_session_add_with_begin_nested_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":"for item in items:\n    with session.begin_nested():\n        session.add(MyModel(data=item))\nsession.commit()"}}' \
	0 ""

# (c) Python file with session.add() but no loop → no warn
run_test "python_no_loop_session_add_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":"session.add(MyModel(data=item))\nsession.commit()"}}' \
	0 ""

# (d) Non-Python file with loop + session.add() → no warn
run_test "non_python_file_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.sh","content":"for item in items:\n    session.add(MyModel(data=item))\nsession.commit()"}}' \
	0 ""

# (d) Go file with loop + session.add() → no warn
run_test "go_file_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.go","content":"for _, item := range items {\n    session.add(item)\n}"}}' \
	0 ""

# (e) Python file with no session.add() → no warn
run_test "python_no_session_add_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":"for item in items:\n    db.insert(item)\nsession.commit()"}}' \
	0 ""

# (f) Edit tool (new_string) with violation → warns
run_test "edit_new_string_with_loop_and_add_warns" \
	'{"tool_input":{"file_path":"projects/monolith/knowledge/raw_ingest.py","new_string":"for raw_input in raw_inputs:\n    note = Note(content=raw_input.content)\n    session.add(note)\nsession.commit()"}}' \
	0 "begin_nested"

# (f) Edit tool (new_string) with begin_nested → no warn
run_test "edit_new_string_with_begin_nested_no_warn" \
	'{"tool_input":{"file_path":"projects/monolith/knowledge/raw_ingest.py","new_string":"for raw_input in raw_inputs:\n    with session.begin_nested():\n        note = Note(content=raw_input.content)\n        session.add(note)\nsession.commit()"}}' \
	0 ""

# (g) Empty content → no warn
run_test "empty_content_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":""}}' \
	0 ""

# (g) No content field → no warn
run_test "no_content_field_no_warn" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py"}}' \
	0 ""

# (g) Completely empty JSON → no warn
run_test "empty_json_no_warn" \
	'{}' \
	0 ""

# (h) Warning message mentions savepoints / begin_nested
run_test "warning_mentions_savepoint" \
	'{"tool_input":{"file_path":"projects/knowledge/backend/ingest.py","content":"for item in items:\n    session.add(MyModel(data=item))\nsession.commit()"}}' \
	0 "savepoint|begin_nested"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
