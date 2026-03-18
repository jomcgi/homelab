#!/usr/bin/env bash
# Unit tests for check-chart-version-sync.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr when Chart.yaml is edited without a
#     corresponding update to deploy/application.yaml in the git working tree
#
# This test mocks jq via a minimal Python3 stub and git via a Python3 stub,
# both placed earlier on PATH so the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-chart-version-sync.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-chart-version-sync.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-chart-version-sync.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly one expression:
#   jq -r '.tool_input.file_path // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expression used by check-chart-version-sync.sh."""
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

# ---------------------------------------------------------------------------
# Install a git stub controlled by environment variables:
#
#   GIT_STUB_TOPLEVEL  -- printed by `git rev-parse --show-toplevel`
#                         empty/unset means no git repo (stub exits 128)
#   GIT_STUB_STATUS    -- output of `git status --porcelain`
#                         empty/unset means clean working tree
#   GIT_STUB_DIFF      -- output of `git diff --name-only HEAD`
#                         empty/unset means no diff vs HEAD
# ---------------------------------------------------------------------------
cat >"${TEST_TMPDIR}/bin/git" <<'GIT_STUB'
#!/usr/bin/env python3
"""git stub for check-chart-version-sync.sh tests."""
import os, sys

args = sys.argv[1:]

# Strip all -C <dir> pairs (hook always passes -C to set CWD context)
while "-C" in args:
    idx = args.index("-C")
    args = args[:idx] + args[idx + 2:]

if not args:
    sys.exit(1)

cmd = args[0]

if cmd == "rev-parse" and "--show-toplevel" in args:
    toplevel = os.environ.get("GIT_STUB_TOPLEVEL", "")
    if toplevel:
        print(toplevel)
    else:
        sys.exit(128)  # simulates "not a git repository"
elif cmd == "status":
    out = os.environ.get("GIT_STUB_STATUS", "")
    if out:
        print(out)
elif cmd == "diff":
    out = os.environ.get("GIT_STUB_DIFF", "")
    if out:
        print(out)
else:
    sys.exit(1)
GIT_STUB
chmod +x "${TEST_TMPDIR}/bin/git"

export PATH="${TEST_TMPDIR}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Filesystem fixtures used by git-aware tests
#
# Layout:
#   $FIXTURE/projects/myservice/chart/Chart.yaml   (the file_path under test)
#   $FIXTURE/projects/myservice/deploy/application.yaml  (must exist for -f check)
# ---------------------------------------------------------------------------
FIXTURE="${TEST_TMPDIR}/fixture"
mkdir -p "${FIXTURE}/projects/myservice/chart"
mkdir -p "${FIXTURE}/projects/myservice/deploy"
touch "${FIXTURE}/projects/myservice/deploy/application.yaml"
CHART_PATH="${FIXTURE}/projects/myservice/chart/Chart.yaml"

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

# run_test NAME INPUT_JSON WANT_STDERR_RE
#   Hook always exits 0; WANT_STDERR_RE="" means no output expected.
run_test() {
	local name="$1"
	local input_json="$2"
	local want_stderr_re="$3"

	local stderr_out
	local got_exit=0
	stderr_out=$(printf '%s' "$input_json" | bash "$HOOK" 2>&1 >/dev/null) || got_exit=$?

	local ok=true

	if [[ "$got_exit" -ne 0 ]]; then
		echo "FAIL [$name]: unexpected exit $got_exit (hook should always exit 0)"
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

# run_git_test NAME FILE_PATH TOPLEVEL STATUS DIFF WANT_STDERR_RE
#   Wraps run_test with explicit GIT_STUB_* env vars for each test case.
run_git_test() {
	local name="$1"
	local file_path="$2"
	local toplevel="$3"
	local stub_status="$4"
	local stub_diff="$5"
	local want_stderr_re="$6"

	local esc_path="${file_path//\\/\\\\}"
	esc_path="${esc_path//\"/\\\"}"
	local input_json
	input_json=$(printf '{"tool_input":{"file_path":"%s"}}' "$esc_path")

	local stderr_out
	local got_exit=0
	stderr_out=$(
		export GIT_STUB_TOPLEVEL="$toplevel"
		export GIT_STUB_STATUS="$stub_status"
		export GIT_STUB_DIFF="$stub_diff"
		printf '%s' "$input_json" | bash "$HOOK" 2>&1 >/dev/null
	) || got_exit=$?

	local ok=true

	if [[ "$got_exit" -ne 0 ]]; then
		echo "FAIL [$name]: unexpected exit $got_exit"
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
# Tests: paths that skip the Chart.yaml check entirely
# ---------------------------------------------------------------------------

# 1. Empty JSON -- no file_path, skipped immediately
run_test "empty_json" \
	'{}' \
	""

# 2. tool_input present but no file_path field -- skipped
run_test "missing_file_path" \
	'{"tool_input":{}}' \
	""

# 3. values.yaml in chart/ dir -- not Chart.yaml, skipped
run_test "values_yaml_not_flagged" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${FIXTURE}/projects/myservice/chart/values.yaml")" \
	""

# 4. Chart.yaml outside chart/ subdir -- pattern */chart/Chart.yaml not matched
run_test "chart_yaml_wrong_dir" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${FIXTURE}/projects/myservice/deploy/Chart.yaml")" \
	""

# 5. Valid */chart/Chart.yaml path but no deploy/application.yaml sibling -- skipped
run_test "no_application_yaml_skipped" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${FIXTURE}/projects/noapp/chart/Chart.yaml")" \
	""

# ---------------------------------------------------------------------------
# Tests: Chart.yaml path + application.yaml present; git state varies
# (GIT_STUB_TOPLEVEL="" means git exits 128 --> REPO_ROOT="" --> hook exits 0 silently)
# ---------------------------------------------------------------------------

# 6. No git repo at all -- hook skips gracefully without warning
run_git_test \
	"no_git_repo_no_warning" \
	"$CHART_PATH" \
	"" "" "" \
	""

# 7. application.yaml shows in git status (staged/modified) -- no warning
run_git_test \
	"app_yaml_in_status_no_warning" \
	"$CHART_PATH" \
	"$FIXTURE" \
	"M projects/myservice/deploy/application.yaml" \
	"" \
	""

# 8. application.yaml shows in git diff HEAD -- no warning
run_git_test \
	"app_yaml_in_diff_no_warning" \
	"$CHART_PATH" \
	"$FIXTURE" \
	"" \
	"projects/myservice/deploy/application.yaml" \
	""

# 9. application.yaml shows in both status and diff -- no warning
run_git_test \
	"app_yaml_in_status_and_diff_no_warning" \
	"$CHART_PATH" \
	"$FIXTURE" \
	"M projects/myservice/deploy/application.yaml" \
	"projects/myservice/deploy/application.yaml" \
	""

# 10. application.yaml NOT in status or diff -- WARNING emitted
run_git_test \
	"app_yaml_unchanged_emits_warning" \
	"$CHART_PATH" \
	"$FIXTURE" \
	"" \
	"" \
	"WARNING:"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
