#!/usr/bin/env bash
# Unit tests for check-npm-apko-transitive-deps.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr only when ALL of the following match:
#       1. file_path ends with BUILD or BUILD.bazel
#       2. content contains 'apko_image'
#       3. content contains 'node_modules/'
#       4. content contains a .tar reference (matches \.tar["\)])
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so the
# hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-npm-apko-transitive-deps.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-npm-apko-transitive-deps.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-npm-apko-transitive-deps.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses exactly two expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering the expressions used by check-npm-apko-transitive-deps.sh."""
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
# Reusable BUILD file content fragments
# ---------------------------------------------------------------------------
# Content that triggers all four checks: apko_image + node_modules/ + .tar ref
FULL_MATCH_CONTENT='load("@rules_apko//:defs.bzl", "apko_image")

genrule(
    name = "npm_layer",
    srcs = ["node_modules/my-pkg"],
    outs = ["npm_layer.tar"],
    cmd = "tar cf $@ $(SRCS)",
)

apko_image(
    name = "image",
    config = "apko.yaml",
    layers = [":npm_layer"],
)'

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

# run_test NAME FILE_PATH CONTENT WANT_STDERR_RE
#   FILE_PATH  -- value of tool_input.file_path (use "content" key for Write tool)
#   CONTENT    -- value of tool_input.content (empty string means omit from JSON)
#   WANT_STDERR_RE -- regex that stderr must match; "" means no output expected.
#   Hook always exits 0.
run_test() {
	local name="$1"
	local file_path="$2"
	local content="$3"
	local want_stderr_re="$4"

	# Build JSON input. Escape quotes in the content for embedding in JSON.
	local esc_path="${file_path//\\/\\\\}"
	esc_path="${esc_path//\"/\\\"}"
	local esc_content="${content//\\/\\\\}"
	esc_content="${esc_content//\"/\\\"}"
	esc_content="${esc_content//$'\n'/\\n}"

	local input_json
	if [[ -n "$content" ]]; then
		input_json=$(printf '{"tool_input":{"file_path":"%s","content":"%s"}}' \
			"$esc_path" "$esc_content")
	else
		input_json=$(printf '{"tool_input":{"file_path":"%s"}}' "$esc_path")
	fi

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

# ---------------------------------------------------------------------------
# Tests: non-BUILD files are ignored regardless of content
# ---------------------------------------------------------------------------

# 1. Python source file — skipped even if content matches all conditions
run_test "non_build_python_file" \
	"/workspace/projects/myservice/main.py" \
	"$FULL_MATCH_CONTENT" \
	""

# 2. YAML file — skipped
run_test "non_build_yaml_file" \
	"/workspace/projects/myservice/deploy/values.yaml" \
	"$FULL_MATCH_CONTENT" \
	""

# 3. Go source file — skipped
run_test "non_build_go_file" \
	"/workspace/projects/myservice/main.go" \
	"$FULL_MATCH_CONTENT" \
	""

# 4. File named BUILD.go (not a real BUILD file) — skipped
run_test "non_build_go_suffix" \
	"/workspace/projects/myservice/BUILD.go" \
	"$FULL_MATCH_CONTENT" \
	""

# ---------------------------------------------------------------------------
# Tests: BUILD files without apko_image are ignored
# ---------------------------------------------------------------------------

# 5. BUILD file with node_modules/ and .tar but no apko_image
CONTENT_NO_APKO='genrule(
    name = "npm_layer",
    srcs = ["node_modules/my-pkg"],
    outs = ["npm_layer.tar"],
    cmd = "tar cf $@ $(SRCS)",
)'
run_test "build_no_apko_image" \
	"/workspace/projects/myservice/BUILD" \
	"$CONTENT_NO_APKO" \
	""

# 6. BUILD.bazel with no apko_image — also skipped
run_test "build_bazel_no_apko_image" \
	"/workspace/projects/myservice/BUILD.bazel" \
	"$CONTENT_NO_APKO" \
	""

# ---------------------------------------------------------------------------
# Tests: BUILD files without node_modules/ refs are ignored
# ---------------------------------------------------------------------------

# 7. BUILD file with apko_image and .tar but no node_modules/ reference
CONTENT_NO_NODE_MODULES='load("@rules_apko//:defs.bzl", "apko_image")

genrule(
    name = "static_layer",
    srcs = ["static/assets"],
    outs = ["static_layer.tar"],
    cmd = "tar cf $@ $(SRCS)",
)

apko_image(
    name = "image",
    config = "apko.yaml",
)'
run_test "build_no_node_modules" \
	"/workspace/projects/myservice/BUILD" \
	"$CONTENT_NO_NODE_MODULES" \
	""

# ---------------------------------------------------------------------------
# Tests: BUILD files without .tar output are ignored
# ---------------------------------------------------------------------------

# 8. BUILD file with apko_image and node_modules/ but no .tar output
CONTENT_NO_TAR='load("@rules_apko//:defs.bzl", "apko_image")

genrule(
    name = "npm_layer",
    srcs = ["node_modules/my-pkg"],
    outs = ["npm_layer.zip"],
    cmd = "zip $@ $(SRCS)",
)

apko_image(
    name = "image",
    config = "apko.yaml",
)'
run_test "build_no_tar_output" \
	"/workspace/projects/myservice/BUILD" \
	"$CONTENT_NO_TAR" \
	""

# ---------------------------------------------------------------------------
# Tests: BUILD files matching all conditions emit the warning to stderr
# ---------------------------------------------------------------------------

# 9. BUILD file (not .bazel) with all conditions — warning expected
run_test "build_all_conditions_warns" \
	"/workspace/projects/myservice/BUILD" \
	"$FULL_MATCH_CONTENT" \
	"WARNING:"

# 10. BUILD.bazel file with all conditions — also warns
run_test "build_bazel_all_conditions_warns" \
	"/workspace/projects/myservice/BUILD.bazel" \
	"$FULL_MATCH_CONTENT" \
	"WARNING:"

# 11. Warning mentions transitive deps in the message
run_test "warning_mentions_transitive" \
	"/workspace/projects/myservice/BUILD" \
	"$FULL_MATCH_CONTENT" \
	"transitive"

# 12. Warning mentions pnpm in the message
run_test "warning_mentions_pnpm" \
	"/workspace/projects/myservice/BUILD" \
	"$FULL_MATCH_CONTENT" \
	"pnpm"

# ---------------------------------------------------------------------------
# Tests: new_string (Edit tool) is also checked
# ---------------------------------------------------------------------------

# 13. Edit tool sends new_string instead of content — hook should check it
NEW_STRING_JSON=$(printf '{"tool_input":{"file_path":"%s","new_string":"%s"}}' \
	"/workspace/projects/myservice/BUILD" \
	"$(echo "$FULL_MATCH_CONTENT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])')")

EDIT_STDERR=$(printf '%s' "$NEW_STRING_JSON" | bash "$HOOK" 2>&1 >/dev/null || true)
if echo "$EDIT_STDERR" | grep -qE "WARNING:"; then
	echo "PASS [edit_new_string_warns]"
	PASS=$((PASS + 1))
else
	echo "FAIL [edit_new_string_warns]: expected WARNING in stderr, got: $(printf '%q' "$EDIT_STDERR")"
	FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Tests: empty / missing content is ignored
# ---------------------------------------------------------------------------

# 14. No content key at all — skipped immediately
run_test "missing_content_skipped" \
	"/workspace/projects/myservice/BUILD" \
	"" \
	""

# 15. Empty JSON object — skipped gracefully (no file_path, no content)
EMPTY_STDERR=$(printf '{}' | bash "$HOOK" 2>&1 >/dev/null || true)
if [[ -n "$EMPTY_STDERR" ]]; then
	echo "FAIL [empty_json_object]: unexpected stderr: $(printf '%q' "$EMPTY_STDERR")"
	FAIL=$((FAIL + 1))
else
	echo "PASS [empty_json_object]"
	PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
