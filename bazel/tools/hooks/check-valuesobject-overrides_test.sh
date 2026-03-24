#!/usr/bin/env bash
# Unit tests for check-valuesobject-overrides.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 (warning) when a */deploy/application.yaml contains a
#     valuesObject block with overrideable Helm values
#   - Exits 0 (silent) otherwise — it never blocks

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-valuesobject-overrides.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-valuesobject-overrides.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-valuesobject-overrides.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-valuesobject-overrides.sh."""
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

# (a) application.yaml with valuesObject + podAnnotations → WARNING
run_test "write_application_yaml_valuesObject_podAnnotations_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        podAnnotations:\n          prometheus.io/scrape: \"true\"\n"}}' \
	0 "WARNING"

# (b) application.yaml with valuesObject + resources → WARNING
run_test "write_application_yaml_valuesObject_resources_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        resources:\n          limits:\n            memory: 512Mi\n"}}' \
	0 "WARNING"

# (c) application.yaml with valuesObject + nodeSelector → WARNING
run_test "write_application_yaml_valuesObject_nodeSelector_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        nodeSelector:\n          kubernetes.io/arch: amd64\n"}}' \
	0 "WARNING"

# (d) Edit tool: new_string with valuesObject + podLabels → WARNING
run_test "edit_application_yaml_valuesObject_podLabels_warns" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","new_string":"spec:\n  source:\n    helm:\n      valuesObject:\n        podLabels:\n          team: platform\n"}}' \
	0 "WARNING"

# (e) application.yaml without valuesObject → silent
run_test "write_application_yaml_no_valuesObject_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valueFiles:\n        - values.yaml\n"}}' \
	0 ""

# (f) application.yaml with valuesObject but no overrideable keys → silent
run_test "write_application_yaml_valuesObject_safe_keys_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        replicaCount: 2\n        image:\n          tag: latest\n"}}' \
	0 ""

# (g) Non-application.yaml file → silent
run_test "write_values_yaml_not_checked" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/values.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        podAnnotations:\n          foo: bar\n"}}' \
	0 ""

# (h) Non-deploy path application.yaml → silent
run_test "write_non_deploy_application_yaml_silent" \
	'{"tool_input":{"file_path":"projects/myservice/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        podAnnotations:\n          foo: bar\n"}}' \
	0 ""

# (i) Empty content → silent
run_test "write_empty_content_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":""}}' \
	0 ""

# (j) No content field → silent
run_test "no_content_field_silent" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml"}}' \
	0 ""

# (k) Completely empty JSON → silent
run_test "empty_json_silent" \
	'{}' \
	0 ""

# (l) Warning message mentions values.yaml
run_test "warning_message_mentions_values_yaml" \
	'{"tool_input":{"file_path":"projects/myservice/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        tolerations:\n          - key: foo\n"}}' \
	0 "values.yaml"

# (m) Nested deploy path still matched
run_test "write_nested_deploy_application_yaml_warns" \
	'{"tool_input":{"file_path":"projects/agent_platform/cluster_agents/deploy/application.yaml","content":"spec:\n  source:\n    helm:\n      valuesObject:\n        env:\n          - name: MY_VAR\n            value: hello\n"}}' \
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
