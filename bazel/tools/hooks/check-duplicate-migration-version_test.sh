#!/usr/bin/env bash
# Unit tests for check-duplicate-migration-version.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr when a migration file's 14-digit prefix collides
#     with an existing file in the same migrations/ directory
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so the
# hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-duplicate-migration-version.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-duplicate-migration-version.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-duplicate-migration-version.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by check-duplicate-migration-version.sh."""
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
# Filesystem fixtures: a migrations/ directory with some existing .sql files
# ---------------------------------------------------------------------------
MIGRATIONS="${TEST_TMPDIR}/db/migrations"
mkdir -p "$MIGRATIONS"
touch "${MIGRATIONS}/20240301120000_create_users.sql"
touch "${MIGRATIONS}/20240302130000_add_email_index.sql"

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

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

# 3. Non-SQL file -- not *.sql, skipped
run_test "non_sql_file" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/20240301120000_create_users.py")" \
	""

# 4. SQL file but not in a migrations/ directory -- skipped
run_test "not_in_migrations_dir" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${TEST_TMPDIR}/db/schema/20240301120000_foo.sql")" \
	""

# 5. Filename shorter than 14 chars -- skipped
run_test "filename_too_short" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/2024.sql")" \
	""

# 6. Non-numeric prefix (14 chars but not all digits) -- skipped
run_test "non_numeric_prefix" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/abcdefghijklmn_foo.sql")" \
	""

# 7. Unique prefix -- no existing file with this prefix, no warning
run_test "unique_prefix_no_warning" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/20250101090000_new_table.sql")" \
	""

# 8. Duplicate prefix -- another file exists with the same 14-digit prefix, WARNING emitted
run_test "duplicate_prefix_warns" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/20240301120000_another_migration.sql")" \
	"WARNING:"

# 9. Self -- rewriting an existing file (exact same filename) should NOT warn
run_test "self_no_false_positive" \
	"$(printf '{"tool_input":{"file_path":"%s"}}' \
		"${MIGRATIONS}/20240301120000_create_users.sql")" \
	""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
	exit 1
fi
exit 0
