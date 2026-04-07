#!/usr/bin/env bash
# Unit tests for check-hardcoded-llm-model.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path and
#     .tool_input.content (Write) or .tool_input.new_string (Edit)
#   - Exits 0 always (warning only, never blocks)
#   - Prints a warning to stderr when content contains a hardcoded LLM model
#     name string (gemma-, llama-, mistral-, claude- + version) AND the file
#     path ends in .py

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-hardcoded-llm-model.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-hardcoded-llm-model.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-hardcoded-llm-model.sh in runfiles" >&2
	exit 1
fi

# ---------------------------------------------------------------------------
# Install a minimal jq stub so the hook runs in the hermetic sandbox.
# The hook uses two expressions:
#   jq -r '.tool_input.file_path // empty'
#   jq -r '.tool_input.content // .tool_input.new_string // empty'
# ---------------------------------------------------------------------------
mkdir -p "${TEST_TMPDIR}/bin"
cat >"${TEST_TMPDIR}/bin/jq" <<'JQ_STUB'
#!/usr/bin/env python3
"""Minimal jq stub covering expressions used by check-hardcoded-llm-model.sh."""
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

# (a) Python file with gemma model string triggers warning
run_test "write_py_gemma_warns" \
	'{"tool_input":{"file_path":"projects/monolith/chat/bot.py","content":"\"model\": \"gemma-4-26b-a4b\","}}' \
	0 "WARNING"

# (a) Python file with llama model string triggers warning
run_test "write_py_llama_warns" \
	'{"tool_input":{"file_path":"projects/myapp/backend/client.py","content":"model = \"llama-3.1-8b\""}}' \
	0 "WARNING"

# (a) Python file with mistral model string triggers warning
run_test "write_py_mistral_warns" \
	'{"tool_input":{"file_path":"projects/myapp/infer.py","content":"\"model\": \"mistral-7b\","}}' \
	0 "WARNING"

# (a) Python file with claude model string triggers warning
run_test "write_py_claude_warns" \
	'{"tool_input":{"file_path":"projects/myapp/agent.py","content":"model_id = \"claude-3-sonnet\""}}' \
	0 "WARNING"

# (a) Edit tool: new_string in .py file triggers warning
run_test "edit_py_gemma_warns" \
	'{"tool_input":{"file_path":"projects/monolith/chat/vision.py","new_string":"\"model\": \"gemma-4-26b-a4b\","}}' \
	0 "WARNING"

# (b) Non-Python file with LLM model string does NOT trigger warning
run_test "write_yaml_gemma_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/deploy/values.yaml","content":"model: gemma-4-26b-a4b"}}' \
	0 ""

# (b) Markdown file with model name does NOT trigger warning
run_test "write_md_llama_no_warn" \
	'{"tool_input":{"file_path":"docs/models.md","content":"We use \"llama-3.1-8b\" for inference."}}' \
	0 ""

# (b) Python file WITHOUT any hardcoded model string does NOT trigger warning
run_test "write_py_no_model_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.py","content":"model = os.environ.get(\"LLM_MODEL\", \"\")"}}' \
	0 ""

# (c) Empty content does NOT trigger warning
run_test "write_empty_content" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.py","content":""}}' \
	0 ""

# (c) No content field does NOT trigger warning
run_test "no_content_field" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.py"}}' \
	0 ""

# (c) Completely empty JSON does NOT trigger warning
run_test "empty_json" \
	'{}' \
	0 ""

# (d) Warning message mentions environment variable
run_test "warning_mentions_env_var" \
	'{"tool_input":{"file_path":"projects/monolith/chat/summarizer.py","content":"\"model\": \"gemma-4-26b-a4b\","}}' \
	0 "environ"

# (e) Go file with model string does NOT trigger warning
run_test "write_go_gemma_no_warn" \
	'{"tool_input":{"file_path":"projects/myapp/backend/main.go","content":"model := \"gemma-4-26b-a4b\""}}' \
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
