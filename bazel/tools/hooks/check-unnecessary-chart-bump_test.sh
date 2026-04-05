#!/usr/bin/env bash
# Unit tests for check-unnecessary-chart-bump.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and .tool_input.new_string
#     (or .tool_input.content for Write tool)
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr when Chart.yaml version is bumped but only test
#     files changed under chart/ or deploy/
#
# This test mocks jq via a minimal Python3 stub and git via a Python3 stub,
# both placed earlier on PATH so the hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-unnecessary-chart-bump.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-unnecessary-chart-bump.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-unnecessary-chart-bump.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses these expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.new_string // empty'
#   jq -r '.tool_input.content // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-unnecessary-chart-bump.sh."""
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
#   GIT_STUB_TOPLEVEL     -- printed by `git rev-parse --show-toplevel`
#                            empty/unset means no git repo (stub exits 128)
#   GIT_STUB_CACHED_FILES -- output of `git diff --cached --name-only`
#                            empty/unset means no staged changes
#   GIT_STUB_DIFF_FILES   -- output of `git diff --name-only HEAD`
#                            empty/unset means no diff vs HEAD
#   GIT_STUB_STATUS_FILES -- output of `git status --porcelain` (one file per line,
#                            format: "M  projects/svc/chart/foo.go")
#                            empty/unset means clean working tree
# ---------------------------------------------------------------------------
cat >"${TEST_TMPDIR}/bin/git" <<'GIT_STUB'
#!/usr/bin/env python3
"""git stub for check-unnecessary-chart-bump.sh tests."""
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
elif cmd == "diff":
    if "--cached" in args:
        out = os.environ.get("GIT_STUB_CACHED_FILES", "")
        if out:
            print(out)
    elif "HEAD" in args:
        out = os.environ.get("GIT_STUB_DIFF_FILES", "")
        if out:
            print(out)
elif cmd == "status":
    out = os.environ.get("GIT_STUB_STATUS_FILES", "")
    if out:
        print(out)
else:
    sys.exit(1)
GIT_STUB
chmod +x "${TEST_TMPDIR}/bin/git"

export PATH="${TEST_TMPDIR}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Filesystem fixtures used by version-comparison tests
#
# Layout:
#   $FIXTURE/projects/myservice/chart/Chart.yaml  (existing file with version 0.1.0)
# ---------------------------------------------------------------------------
FIXTURE="${TEST_TMPDIR}/fixture"
mkdir -p "${FIXTURE}/projects/myservice/chart"
mkdir -p "${FIXTURE}/projects/myservice/deploy"
CHART_PATH="${FIXTURE}/projects/myservice/chart/Chart.yaml"
cat >"$CHART_PATH" <<'CHART'
apiVersion: v2
name: myservice
description: A test service
version: 0.1.0
appVersion: "1.0.0"
CHART

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

# run_git_test NAME FILE_PATH NEW_STRING TOPLEVEL CACHED_FILES DIFF_FILES STATUS_FILES WANT_STDERR_RE
#   Wraps run_test with explicit GIT_STUB_* env vars for git-aware test cases.
run_git_test() {
	local name="$1"
	local file_path="$2"
	local new_string="$3"
	local toplevel="$4"
	local cached_files="$5"
	local diff_files="$6"
	local status_files="$7"
	local want_stderr_re="$8"

	local esc_path="${file_path//\\/\\\\}"
	esc_path="${esc_path//\"/\\\"}"
	local esc_content="${new_string//$'\n'/\\n}"
	esc_content="${esc_content//\"/\\\"}"
	local input_json
	input_json=$(printf '{"tool_input":{"file_path":"%s","new_string":"%s"}}' "$esc_path" "$esc_content")

	local stderr_out
	local got_exit=0
	stderr_out=$(
		export GIT_STUB_TOPLEVEL="$toplevel"
		export GIT_STUB_CACHED_FILES="$cached_files"
		export GIT_STUB_DIFF_FILES="$diff_files"
		export GIT_STUB_STATUS_FILES="$status_files"
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
# Tests: paths that skip the check entirely
# ---------------------------------------------------------------------------

# 1. Empty JSON -- no file_path, skipped immediately
run_test "empty_json" \
	'{}' \
	""

# 2. tool_input present but no file_path field -- skipped
run_test "missing_file_path" \
	'{"tool_input":{}}' \
	""

# 3. values.yaml (not Chart.yaml) -- skipped
run_test "values_yaml_not_flagged" \
	"$(printf '{"tool_input":{"file_path":"%s","new_string":"name: foo"}}' \
		"${FIXTURE}/projects/myservice/chart/values.yaml")" \
	""

# 4. Chart.yaml outside chart/ or deploy/ dir -- pattern not matched
run_test "chart_yaml_wrong_dir" \
	"$(printf '{"tool_input":{"file_path":"%s","new_string":"version: 0.2.0"}}' \
		"${FIXTURE}/projects/myservice/Chart.yaml")" \
	""

# 5. Chart.yaml inside chart/ but new content has no version line -- skipped
run_test "no_version_in_new_content" \
	"$(printf '{"tool_input":{"file_path":"%s","new_string":"name: myservice\ndescription: foo"}}' \
		"$CHART_PATH")" \
	""

# 6. Chart.yaml version not changing (0.1.0 -> 0.1.0) -- skipped
run_test "version_not_changing" \
	"$(printf '{"tool_input":{"file_path":"%s","new_string":"version: 0.1.0"}}' \
		"$CHART_PATH")" \
	""

# ---------------------------------------------------------------------------
# Tests: version is changing; git state varies
# ---------------------------------------------------------------------------

# 7. No git repo -- hook skips gracefully without warning
run_git_test \
	"no_git_repo_no_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"" "" "" "" \
	""

# 8. Version changing, no other files changed (clean working tree) -- no warning
#    (standalone chart bump; may be intentional)
run_git_test \
	"version_bump_no_other_files_no_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" "" "" "" \
	""

# 9. Version changing, non-test file changed (template) -- no warning
run_git_test \
	"version_bump_with_template_change_no_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"projects/myservice/chart/templates/deployment.yaml" \
	"" \
	"" \
	""

# 10. Version changing, non-test file changed via diff HEAD -- no warning
run_git_test \
	"version_bump_with_values_change_no_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"" \
	"projects/myservice/deploy/values.yaml" \
	"" \
	""

# 11. Version changing, only a Go test file changed -- WARNING emitted
run_git_test \
	"version_bump_only_go_test_emits_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"projects/myservice/chart/tests/deploy_test.go" \
	"" \
	"" \
	"WARNING:"

# 12. Version changing, only a Python test file changed -- WARNING emitted
run_git_test \
	"version_bump_only_py_test_emits_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"" \
	"projects/myservice/chart/tests/render_test.py" \
	"" \
	"WARNING:"

# 13. Version changing, only a TypeScript test file changed -- WARNING emitted
run_git_test \
	"version_bump_only_ts_test_emits_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"" \
	"" \
	"M  projects/myservice/chart/tests/validate_test.ts" \
	"WARNING:"

# 14. Version changing, only a file in fixtures/ changed -- WARNING emitted
run_git_test \
	"version_bump_only_fixture_emits_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"" \
	"projects/myservice/chart/fixtures/sample.yaml" \
	"" \
	"WARNING:"

# 15. Version changing, mix of test file + non-test file -- no warning
run_git_test \
	"version_bump_mixed_files_no_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"projects/myservice/chart/tests/deploy_test.go" \
	"projects/myservice/chart/templates/service.yaml" \
	"" \
	""

# 16. Write tool (content field instead of new_string) -- WARNING emitted when only test changed
#     Uses a custom input_json with the content field rather than new_string.
write_tool_input=$(printf '{"tool_input":{"file_path":"%s","content":"version: 0.2.0\\nname: myservice\\n"}}' "$CHART_PATH")
GIT_STUB_TOPLEVEL="$FIXTURE" \
	GIT_STUB_CACHED_FILES="projects/myservice/chart/tests/e2e_test.go" \
	GIT_STUB_DIFF_FILES="" \
	GIT_STUB_STATUS_FILES="" \
	run_test "write_tool_content_field" "$write_tool_input" "WARNING:"

# 17. Version changing, only a shell test file changed -- WARNING emitted
run_git_test \
	"version_bump_only_sh_test_emits_warning" \
	"$CHART_PATH" \
	"version: 0.2.0" \
	"$FIXTURE" \
	"projects/myservice/chart/tests/deploy_test.sh" \
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
