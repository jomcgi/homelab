#!/usr/bin/env bash
# Unit tests for check-missing-imageupdater.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 (warning) when a */deploy/kustomization.yaml contains
#     application.yaml but NOT imageupdater.yaml
#   - Exits 0 (silent) otherwise — it never blocks

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-missing-imageupdater.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-missing-imageupdater.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-missing-imageupdater.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-missing-imageupdater.sh."""
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

# (a) kustomization.yaml with application.yaml but no imageupdater.yaml → WARNING
run_test "write_kustomization_missing_imageupdater_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 "WARNING"

# (a) Edit tool: new_string with application.yaml but no imageupdater.yaml → WARNING
run_test "edit_kustomization_missing_imageupdater_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","new_string":"resources:\n- application.yaml\n"}}' \
	0 "WARNING"

# (b) kustomization.yaml with both application.yaml AND imageupdater.yaml → silent
run_test "write_kustomization_has_imageupdater_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":"resources:\n- application.yaml\n- imageupdater.yaml\n"}}' \
	0 ""

# (c) kustomization.yaml without application.yaml → silent (not an ArgoCD app)
run_test "write_kustomization_no_application_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":"resources:\n- configmap.yaml\n"}}' \
	0 ""

# (d) Non-kustomization file → silent (hook only fires on kustomization.yaml)
run_test "write_values_yaml_not_checked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 ""

# (e) Non-deploy path kustomization.yaml → silent
run_test "write_non_deploy_kustomization_silent" \
	'{"tool_input":{"file_path":"projects/myservice/kustomization.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 ""

# (f) Empty content → silent
run_test "write_empty_content_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":""}}' \
	0 ""

# (g) No content field → silent
run_test "no_content_field_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml"}}' \
	0 ""

# (h) Completely empty JSON → silent
run_test "empty_json_silent" \
	'{}' \
	0 ""

# (i) Warning message mentions imageupdater.yaml
run_test "warning_message_mentions_imageupdater" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 "imageupdater.yaml"

# (j) Warning message mentions ImagePullBackOff
run_test "warning_message_mentions_imagepullbackoff" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/kustomization.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 "ImagePullBackOff"

# (k) Nested deploy path still matched
run_test "write_nested_deploy_kustomization_warns" \
	'{"tool_input":{"file_path":"projects/agent_platform/cluster_agents/deploy/kustomization.yaml","content":"resources:\n- application.yaml\n"}}' \
	0 "WARNING"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
