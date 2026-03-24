#!/usr/bin/env bash
# Unit tests for check-values-chart-version-bump.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Warns (exit 0 with stderr) when editing */deploy/values.yaml or
#     */deploy/templates/* in a dir that has a Chart.yaml, but that Chart.yaml
#     has no uncommitted changes
#   - Exits 0 silently when:
#       * file is not under deploy/
#       * no Chart.yaml exists alongside
#       * Chart.yaml already has uncommitted changes
#       * file path is empty / missing

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-values-chart-version-bump.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-values-chart-version-bump.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-values-chart-version-bump.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-values-chart-version-bump.sh."""
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
# Set up a fake git repo in TEST_TMPDIR so git commands work hermetically.
# All tests run against paths under this fake repo.
# ---------------------------------------------------------------------------
FAKE_REPO="${TEST_TMPDIR}/repo"
mkdir -p "${FAKE_REPO}"
git -C "${FAKE_REPO}" init -q
git -C "${FAKE_REPO}" config user.email "test@test.com"
git -C "${FAKE_REPO}" config user.name "Test"

# ---------------------------------------------------------------------------
# Pattern 1: deploy/ directory contains Chart.yaml directly
# ---------------------------------------------------------------------------

# Service A: deploy/Chart.yaml with NO staged/unstaged changes
SVC_A="${FAKE_REPO}/projects/service-a"
mkdir -p "${SVC_A}/deploy/templates"
cat >"${SVC_A}/deploy/Chart.yaml" <<'EOF'
apiVersion: v2
name: service-a
version: 1.0.0
EOF
cat >"${SVC_A}/deploy/values.yaml" <<'EOF'
replicaCount: 1
EOF
cat >"${SVC_A}/deploy/templates/deployment.yaml" <<'EOF'
# template file
EOF
# Commit so it has a clean working tree
git -C "${FAKE_REPO}" add .
git -C "${FAKE_REPO}" commit -q -m "initial"

# Service B: deploy/Chart.yaml WITH staged changes (modified after commit)
SVC_B="${FAKE_REPO}/projects/service-b"
mkdir -p "${SVC_B}/deploy"
cat >"${SVC_B}/deploy/Chart.yaml" <<'EOF'
apiVersion: v2
name: service-b
version: 1.0.0
EOF
cat >"${SVC_B}/deploy/values.yaml" <<'EOF'
replicaCount: 1
EOF
git -C "${FAKE_REPO}" add .
git -C "${FAKE_REPO}" commit -q -m "add service-b"
# Now modify the Chart.yaml so it has uncommitted changes
echo "# bumped" >>"${SVC_B}/deploy/Chart.yaml"

# ---------------------------------------------------------------------------
# Pattern 2: chart/ directory contains Chart.yaml (sibling to deploy/)
# ---------------------------------------------------------------------------

# Service C: chart/Chart.yaml with NO staged/unstaged changes
SVC_C="${FAKE_REPO}/projects/service-c"
mkdir -p "${SVC_C}/chart" "${SVC_C}/deploy/templates"
cat >"${SVC_C}/chart/Chart.yaml" <<'EOF'
apiVersion: v2
name: service-c
version: 2.0.0
EOF
cat >"${SVC_C}/deploy/values.yaml" <<'EOF'
image: myimage
EOF
cat >"${SVC_C}/deploy/templates/svc.yaml" <<'EOF'
# template
EOF
git -C "${FAKE_REPO}" add .
git -C "${FAKE_REPO}" commit -q -m "add service-c"

# Service D: chart/Chart.yaml WITH staged changes
SVC_D="${FAKE_REPO}/projects/service-d"
mkdir -p "${SVC_D}/chart" "${SVC_D}/deploy"
cat >"${SVC_D}/chart/Chart.yaml" <<'EOF'
apiVersion: v2
name: service-d
version: 3.0.0
EOF
cat >"${SVC_D}/deploy/values.yaml" <<'EOF'
replicas: 2
EOF
git -C "${FAKE_REPO}" add .
git -C "${FAKE_REPO}" commit -q -m "add service-d"
# Modify chart/Chart.yaml to simulate a bumped version
echo "# bumped" >>"${SVC_D}/chart/Chart.yaml"

# Service E: deploy/values.yaml with no Chart.yaml anywhere → skip
SVC_E="${FAKE_REPO}/projects/service-e"
mkdir -p "${SVC_E}/deploy"
cat >"${SVC_E}/deploy/values.yaml" <<'EOF'
key: value
EOF
git -C "${FAKE_REPO}" add .
git -C "${FAKE_REPO}" commit -q -m "add service-e"

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

# Pattern 1: deploy/Chart.yaml present, NOT changed → WARNING
run_test "p1_values_no_chart_bump_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/deploy/values.yaml\"}}" \
	0 "WARNING"

# Pattern 1: deploy/Chart.yaml present, already changed → silent
run_test "p1_values_with_chart_bump_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVC_B}/deploy/values.yaml\"}}" \
	0 ""

# Pattern 1: deploy/templates/* present, Chart.yaml NOT changed → WARNING
run_test "p1_template_no_chart_bump_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/deploy/templates/deployment.yaml\"}}" \
	0 "WARNING"

# Pattern 2: chart/Chart.yaml present, NOT changed → WARNING
run_test "p2_values_no_chart_bump_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVC_C}/deploy/values.yaml\"}}" \
	0 "WARNING"

# Pattern 2: chart/Chart.yaml present, already changed → silent
run_test "p2_values_with_chart_bump_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVC_D}/deploy/values.yaml\"}}" \
	0 ""

# Pattern 2: deploy/templates/* present, chart/Chart.yaml NOT changed → WARNING
run_test "p2_template_no_chart_bump_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVC_C}/deploy/templates/svc.yaml\"}}" \
	0 "WARNING"

# No Chart.yaml anywhere → silent
run_test "no_chart_yaml_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVC_E}/deploy/values.yaml\"}}" \
	0 ""

# File not in deploy/ directory → silent
run_test "file_not_in_deploy_silent" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/chart/Chart.yaml\"}}" \
	0 ""

# File path is empty → silent
run_test "empty_file_path_silent" \
	'{"tool_input":{"file_path":""}}' \
	0 ""

# No file_path field → silent
run_test "no_file_path_field_silent" \
	'{"tool_input":{}}' \
	0 ""

# Completely empty JSON → silent
run_test "empty_json_silent" \
	'{}' \
	0 ""

# Non-existent path with no git repo → silent (git fails gracefully)
run_test "nonexistent_path_silent" \
	'{"tool_input":{"file_path":"/nonexistent/deploy/values.yaml"}}' \
	0 ""

# Warning message mentions Chart.yaml path
run_test "warning_mentions_chart_yaml" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/deploy/values.yaml\"}}" \
	0 "Chart.yaml"

# Warning message mentions PR numbers
run_test "warning_mentions_pr_numbers" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/deploy/values.yaml\"}}" \
	0 "#1499"

# values-prod.yaml (matches values[^/]*.yaml) should also warn
cat >"${SVC_A}/deploy/values-prod.yaml" <<'EOF'
env: prod
EOF
run_test "values_prod_yaml_warns" \
	"{\"tool_input\":{\"file_path\":\"${SVC_A}/deploy/values-prod.yaml\"}}" \
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
