#!/usr/bin/env bash
# Unit tests for prefer-k8s-mcp.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.command
#   - Exits 0 when kubectl is absent or the verb is not get/describe/logs/top
#   - Exits 2 and prints BLOCKED to stderr for kubectl get/describe/logs/top
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so
# the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/prefer-k8s-mcp.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/prefer-k8s-mcp.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate prefer-k8s-mcp.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by prefer-k8s-mcp.sh."""
import json, sys

args = sys.argv[1:]
raw = False
if args and args[0] == "-r":
    raw = True
    args = args[1:]

expr = args[0] if args else "."
data = json.load(sys.stdin)

def jq_eval(obj, expr):
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
    pass
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

# 1. Completely unrelated command (no kubectl) -- allowed
run_test "non_kubectl_command_allowed" \
	'{"tool_input":{"command":"ls -la"}}' \
	0 ""

# 2. kubectl get -- blocked (read-only operation, use MCP instead)
run_test "kubectl_get_blocked" \
	'{"tool_input":{"command":"kubectl get pods"}}' \
	2 "BLOCKED"

# 3. kubectl describe -- blocked
run_test "kubectl_describe_blocked" \
	'{"tool_input":{"command":"kubectl describe pod/foo"}}' \
	2 "BLOCKED"

# 4. kubectl logs -- blocked
run_test "kubectl_logs_blocked" \
	'{"tool_input":{"command":"kubectl logs pod/foo"}}' \
	2 "BLOCKED"

# 5. kubectl top -- blocked
run_test "kubectl_top_blocked" \
	'{"tool_input":{"command":"kubectl top pods"}}' \
	2 "BLOCKED"

# 6. kubectl get with -n flag before verb -- still blocked (flag stripping handles this)
run_test "kubectl_get_with_namespace_flag_blocked" \
	'{"tool_input":{"command":"kubectl -n prod get deployments"}}' \
	2 "BLOCKED"

# 7. kubectl get in a chained command (after &&) -- blocked
run_test "kubectl_get_chained_blocked" \
	'{"tool_input":{"command":"helm template chart && kubectl get pods"}}' \
	2 "BLOCKED"

# 8. kubectl apply -- allowed (write operation, not redirected)
run_test "kubectl_apply_allowed" \
	'{"tool_input":{"command":"kubectl apply -f manifest.yaml"}}' \
	0 ""

# 9. kubectl exec -- allowed (interactive, not a read redirected by MCP)
run_test "kubectl_exec_allowed" \
	'{"tool_input":{"command":"kubectl exec -it pod -- bash"}}' \
	0 ""

# 10. kubectl port-forward -- allowed
run_test "kubectl_port_forward_allowed" \
	'{"tool_input":{"command":"kubectl port-forward svc/foo 8080:80"}}' \
	0 ""

# 11. kubectl explain -- allowed (meta-info, not cluster state)
run_test "kubectl_explain_allowed" \
	'{"tool_input":{"command":"kubectl explain pods"}}' \
	0 ""

# 12. Empty JSON object (no tool_input) -- allowed
run_test "empty_json_allowed" \
	'{}' \
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
