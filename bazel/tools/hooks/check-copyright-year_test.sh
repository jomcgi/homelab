#!/usr/bin/env bash
# Unit tests for check-copyright-year.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.content (Write) or
#     .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when content contains "Copyright 2025"
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-copyright-year.sh"
HOOK=""
for candidate in \
    "${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
    "${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
    "${BASH_SOURCE[0]%/*}/check-copyright-year.sh"; do
    if [[ -f "$candidate" ]]; then
        HOOK="$candidate"
        break
    fi
done
if [[ -z "$HOOK" ]]; then
    echo "ERROR: cannot locate check-copyright-year.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by check-copyright-year.sh."""
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
    local want_exit="$3"        # expected exit code (always 0 for this hook)
    local want_stderr_re="$4"   # regex that must match stderr (empty = no output expected)

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

# 1. Write tool: content with current-year copyright → no warning
run_test "write_current_year" \
    '{"tool_input":{"file_path":"foo.go","content":"// Copyright 2026 Block, Inc."}}' \
    0 ""

# 2. Write tool: content with stale 2025 copyright → warning on stderr
run_test "write_stale_year" \
    '{"tool_input":{"file_path":"foo.go","content":"// Copyright 2025 Block, Inc."}}' \
    0 "2025"

# 3. Edit tool: new_string with stale 2025 copyright → warning on stderr
run_test "edit_stale_year" \
    '{"tool_input":{"file_path":"bar.go","new_string":"// Copyright 2025 Block, Inc.\nfunc Foo() {}"}}' \
    0 "2025"

# 4. Edit tool: new_string with current-year copyright → no warning
run_test "edit_current_year" \
    '{"tool_input":{"file_path":"bar.go","new_string":"// Copyright 2026 Block, Inc."}}' \
    0 ""

# 5. Write tool: content is empty string → exit 0, no output
run_test "write_empty_content" \
    '{"tool_input":{"file_path":"foo.go","content":""}}' \
    0 ""

# 6. No tool_input content or new_string fields → exit 0, no output
run_test "no_content_fields" \
    '{"tool_input":{"file_path":"foo.go"}}' \
    0 ""

# 7. Completely empty JSON object → exit 0, no output
run_test "empty_json" \
    '{}' \
    0 ""

# 8. Warning message mentions "Copyright 2026" as the correct replacement
run_test "warning_suggests_2026" \
    '{"tool_input":{"file_path":"baz.go","content":"// Copyright 2025 Block, Inc."}}' \
    0 "2026"

# 9. Older copyright years (e.g. 2024) are not flagged by this hook
run_test "old_year_not_flagged" \
    '{"tool_input":{"file_path":"legacy.go","content":"// Copyright 2024 Block, Inc."}}' \
    0 ""

# 10. Content where "Copyright 2025" appears inline (not at start of line)
run_test "inline_stale_copyright" \
    '{"tool_input":{"file_path":"readme.md","content":"This project was started in Copyright 2025."}}' \
    0 "2025"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
