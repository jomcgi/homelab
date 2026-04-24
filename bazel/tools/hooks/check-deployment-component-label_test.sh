#!/usr/bin/env bash
# Unit tests for check-deployment-component-label.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and .tool_input.content
#     (Write) or .tool_input.new_string (Edit)
#   - Exits 0 always (warning-only, never blocks)
#   - Emits a WARNING on stderr when a deployment template's matchLabels uses
#     a selectorLabels include without app.kubernetes.io/component
#   - Skips non-deployment files, non-template directories, and files without
#     selectorLabels includes

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-deployment-component-label.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-deployment-component-label.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-deployment-component-label.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.new_string // .tool_input.content // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-deployment-component-label.sh."""
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
	local want_exit="$3"      # expected exit code (always 0 for this hook)
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
# Test cases
# ---------------------------------------------------------------------------

BAD_CONTENT='    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
  template:'

GOOD_CONTENT='    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:'

# 1. Deployment template missing component label → warns
run_test "missing_component_warns" \
	"$(jq -cn --arg fp "/project/chart/templates/deployment.yaml" --arg content "$BAD_CONTENT" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
	0 "WARNING.*component"

# 2. Deployment template with component label → no warning
run_test "has_component_no_warning" \
	"$(jq -cn --arg fp "/project/chart/templates/deployment.yaml" --arg content "$GOOD_CONTENT" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
	0 ""

# 3. Non-deployment file → skip
run_test "non_deployment_skipped" \
	"$(jq -cn --arg fp "/project/chart/templates/service.yaml" --arg content "$BAD_CONTENT" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
	0 ""

# 4. Non-template directory → skip
run_test "non_template_dir_skipped" \
	"$(jq -cn --arg fp "/project/deploy/values.yaml" --arg content "$BAD_CONTENT" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
	0 ""

# 5. Edit tool (new_string) — missing component warns
run_test "edit_tool_missing_component_warns" \
	"$(jq -cn --arg fp "/project/chart/templates/api-deployment.yaml" --arg ns "$BAD_CONTENT" \
		'{tool_input: {file_path: $fp, new_string: $ns}}')" \
	0 "WARNING"

# 6. No matchLabels in content → skip
run_test "no_matchlabels_skipped" \
	"$(jq -cn --arg fp "/project/chart/templates/deployment.yaml" --arg content "kind: Deployment" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
	0 ""

# 7. Empty JSON → skip
run_test "empty_json_allowed" \
	'{}' \
	0 ""

# 8. deploy/templates path also triggers check
run_test "deploy_templates_path_warns" \
	"$(jq -cn --arg fp "/project/deploy/templates/deployment.yaml" --arg content "$BAD_CONTENT" \
		'{tool_input: {file_path: $fp, content: $content}}')" \
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
