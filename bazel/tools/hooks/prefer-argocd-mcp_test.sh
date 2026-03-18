#!/usr/bin/env bash
# Unit tests for prefer-argocd-mcp.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.command
#   - Exits 0 when the command does not invoke the argocd CLI
#   - Exits 2 and prints BLOCKED to stderr when the argocd binary is invoked
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/prefer-argocd-mcp.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/prefer-argocd-mcp.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate prefer-argocd-mcp.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly one expression:
#   jq -r '.tool_input.command // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expression used by prefer-argocd-mcp.sh."""
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
	local want_exit="$3"      # expected exit code (0=allow, 2=block)
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

# 1. Completely unrelated command → allowed
run_test "non_argocd_command_allowed" \
	'{"tool_input":{"command":"kubectl get pods"}}' \
	0 ""

# 2. argocd app list → blocked
run_test "argocd_app_list_blocked" \
	'{"tool_input":{"command":"argocd app list"}}' \
	2 "BLOCKED"

# 3. argocd sync subcommand → blocked
run_test "argocd_sync_blocked" \
	'{"tool_input":{"command":"argocd app sync myapp"}}' \
	2 "BLOCKED"

# 4. argocd after && in a chained command → blocked
run_test "argocd_after_ampersand_blocked" \
	'{"tool_input":{"command":"kubectl get pods && argocd app list"}}' \
	2 "BLOCKED"

# 5. argocd after ; in a chained command → blocked
run_test "argocd_after_semicolon_blocked" \
	'{"tool_input":{"command":"foo; argocd sync myapp"}}' \
	2 "BLOCKED"

# 6. "argocd" appearing only in a Bazel label path → allowed
#    The argocd token is followed by ":" not whitespace, so the regex does not match.
run_test "argocd_in_bazel_path_label_allowed" \
	'{"tool_input":{"command":"bazel test //overlays/argocd:semgrep_test"}}' \
	0 ""

# 7. "argocd" as part of a filename (hyphen after) → allowed
run_test "argocd_filename_hyphen_allowed" \
	'{"tool_input":{"command":"cat argocd-config.yaml"}}' \
	0 ""

# 8. Empty JSON object (no tool_input) → allowed
run_test "empty_json_allowed" \
	'{}' \
	0 ""

# 9. tool_input present but command field absent → allowed
run_test "missing_command_field_allowed" \
	'{"tool_input":{}}' \
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
