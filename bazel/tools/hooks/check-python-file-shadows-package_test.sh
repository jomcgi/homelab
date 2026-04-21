#!/usr/bin/env bash
# Unit tests for check-python-file-shadows-package.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 always (warning-only, never blocks)
#   - Emits a WARNING on stderr when the file stem matches a pip package name
#   - Skips non-.py files, __init__.py, and files in test/ or tests/ directories

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-python-file-shadows-package.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-python-file-shadows-package.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-python-file-shadows-package.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by check-python-file-shadows-package.sh."""
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
# Create a minimal pyproject.toml fixture for tests
# ---------------------------------------------------------------------------
FIXTURE_PYPROJECT="${TEST_TMPDIR}/pyproject.toml"
cat >"$FIXTURE_PYPROJECT" <<'TOML'
[project]
name = "homelab"
version = "0"

dependencies = [
    "aiohttp",
    "fastapi>=0.115.0",
    "fastmcp>=3.0.0",
    "mcp>=1.0",
    "httpx~=0.28.1",
    "pyyaml~=6.0",
    "open-gopro[gui]>=0.22.0",
    "pydantic-settings~=2.1",
    "discord.py>=2.4",
]
TOML

export PYPROJECT_TOML_PATH="$FIXTURE_PYPROJECT"

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
# Tests
# ---------------------------------------------------------------------------

# 1. File that shadows a pip package → warns
run_test "shadows_mcp_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/app/mcp.py"}}' \
	0 "WARNING.*mcp"

# 2. File that shadows a hyphenated package (open-gopro → open_gopro) → warns
run_test "shadows_hyphenated_pkg_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/open_gopro.py"}}' \
	0 "WARNING.*open.gopro"

# 3. File that shadows fastapi → warns
run_test "shadows_fastapi_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/fastapi.py"}}' \
	0 "WARNING.*fastapi"

# 4. File with a name that does NOT match any package → no warning
run_test "no_match_allowed" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/myservice.py"}}' \
	0 ""

# 5. Non-.py file → no warning
run_test "non_py_file_skipped" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/httpx.yaml"}}' \
	0 ""

# 6. __init__.py → no warning (even though it doesn't shadow)
run_test "init_py_skipped" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/__init__.py"}}' \
	0 ""

# 7. File in test/ directory → no warning
run_test "test_dir_skipped" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/test/mcp.py"}}' \
	0 ""

# 8. File in tests/ directory → no warning
run_test "tests_dir_skipped" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/tests/mcp.py"}}' \
	0 ""

# 9. _test.py suffix → no warning
run_test "test_suffix_skipped" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/mcp_test.py"}}' \
	0 ""

# 10. Empty JSON object (no tool_input) → allowed silently
run_test "empty_json_allowed" \
	'{}' \
	0 ""

# 11. Package with extras (discord.py) — stem 'discord' doesn't match 'discord.py' package
#     The package name is 'discord.py', normalized would be 'discord.py' not matching stem 'discord'
run_test "discord_py_pkg_no_false_positive" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/discord.py"}}' \
	0 ""

# 12. Stem matching pydantic_settings (hyphen-normalized) → warns
run_test "shadows_pydantic_settings_warns" \
	'{"tool_input":{"file_path":"/workspace/homelab/projects/foo/pydantic_settings.py"}}' \
	0 "WARNING.*pydantic.settings"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
