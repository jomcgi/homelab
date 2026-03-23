#!/usr/bin/env bash
# Unit tests for check-pdb-single-replica.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and .tool_input.content
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr when minAvailable >= 1 is set in a PDB config
#     without evidence of multiple replicas (replicaCount absent or 1)
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so the
# hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-pdb-single-replica.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-pdb-single-replica.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-pdb-single-replica.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-pdb-single-replica.sh."""
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

# run_test NAME INPUT_JSON WANT_EXIT WANT_STDERR_RE
#   WANT_EXIT: expected exit code (always 0 for this warning-only hook)
#   WANT_STDERR_RE: regex to match stderr; "" means no output expected
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
		echo "FAIL [$name]: expected exit $want_exit, got $got_exit"
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
# Helper to build a JSON input payload for a Write tool call
# ---------------------------------------------------------------------------
make_input() {
	local file_path="$1"
	local content="$2"
	# Use Python to safely produce JSON with arbitrary content
	python3 -c "
import json, sys
print(json.dumps({'tool_input': {'file_path': sys.argv[1], 'content': sys.argv[2]}}))" \
		"$file_path" "$content"
}

# ---------------------------------------------------------------------------
# Tests: paths that are skipped entirely
# ---------------------------------------------------------------------------

# 1. Empty JSON — no file_path, skipped immediately
run_test "empty_json" \
	'{}' \
	0 ""

# 2. Non-deploy file — not a values.yaml or pdb.yaml
run_test "non_target_file_skipped" \
	"$(make_input "projects/myservice/chart/Chart.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 ""

# 3. templates/deployment.yaml — not a pdb.yaml, skipped
run_test "deployment_yaml_skipped" \
	"$(make_input "projects/myservice/chart/templates/deployment.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 ""

# ---------------------------------------------------------------------------
# Tests: deploy/values.yaml — safe configurations (no warning expected)
# ---------------------------------------------------------------------------

# 4. PDB disabled — no eviction risk
run_test "pdb_disabled_no_warning" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: false
  minAvailable: 1")" \
	0 ""

# 5. maxUnavailable used instead of minAvailable — correct pattern
run_test "maxunavailable_no_warning" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: true
  maxUnavailable: 1")" \
	0 ""

# 6. minAvailable: 0 — does not block eviction
run_test "minavailable_zero_no_warning" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: true
  minAvailable: 0")" \
	0 ""

# 7. replicaCount: 3 with minAvailable: 1 — safe, multiple replicas
run_test "multi_replica_safe_no_warning" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 3
podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 ""

# 8. replicaCount: 2 with minAvailable: 1 — leaves budget of 1, safe
run_test "two_replicas_minavailable_one_no_warning" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 2
podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 ""

# ---------------------------------------------------------------------------
# Tests: deploy/values.yaml — dangerous configurations (warning expected)
# ---------------------------------------------------------------------------

# 9. replicaCount: 1 + minAvailable: 1 → zero disruption budget
run_test "explicit_single_replica_warns" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 1
podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 "WARNING:"

# 10. replicaCount absent (defaults to 1) + minAvailable: 1 → zero disruption budget
run_test "absent_replica_count_warns" \
	"$(make_input "projects/myservice/deploy/values.yaml" "podDisruptionBudget:
  enabled: true
  minAvailable: 1")" \
	0 "WARNING:"

# 11. replicaCount: 3 but minAvailable: 3 → zero disruption budget for 3-replica set
run_test "minavailable_equals_replicas_warns" \
	"$(make_input "projects/myservice/deploy/values.yaml" "replicaCount: 3
podDisruptionBudget:
  enabled: true
  minAvailable: 3")" \
	0 "WARNING:"

# ---------------------------------------------------------------------------
# Tests: templates/pdb.yaml — checked as well
# ---------------------------------------------------------------------------

# 12. pdb.yaml with minAvailable and no replicaCount → warns
run_test "pdb_template_warns" \
	"$(make_input "projects/myservice/chart/templates/pdb.yaml" "apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  minAvailable: 1")" \
	0 "WARNING:"

# 13. pdb.yaml with maxUnavailable — no warning
run_test "pdb_template_maxunavailable_ok" \
	"$(make_input "projects/myservice/chart/templates/pdb.yaml" "apiVersion: policy/v1
kind: PodDisruptionBudget
spec:
  maxUnavailable: 1")" \
	0 ""

# ---------------------------------------------------------------------------
# Tests: Edit tool input (new_string instead of content)
# ---------------------------------------------------------------------------

# 14. Edit tool: new_string with bad PDB config → warns
run_test "edit_tool_new_string_warns" \
	"$(python3 -c "
import json, sys
print(json.dumps({'tool_input': {'file_path': 'projects/svc/deploy/values.yaml', 'new_string': 'replicaCount: 1\npodDisruptionBudget:\n  enabled: true\n  minAvailable: 1\n'}}))")" \
	0 "WARNING:"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
