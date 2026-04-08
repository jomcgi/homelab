#!/usr/bin/env bash
# Unit tests for check-crd-phase-enum.sh PreToolUse hook.
#
# The hook:
#   - Reads JSON from stdin with .tool_input.file_path
#   - Exits 0 always (warning only, never blocks)
#   - Prints WARNING to stderr when a phase constant in *_phases.go is missing
#     from the +kubebuilder:validation:Enum annotation for the Phase field in
#     *_types.go, when editing files under projects/operators/
#
# This test mocks jq via a minimal Python3 stub placed earlier on PATH so the
# hook can run in the hermetic Bazel sandbox.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate hook from Bazel runfiles
# ---------------------------------------------------------------------------
HOOK_REL="bazel/tools/hooks/check-crd-phase-enum.sh"
HOOK=""
for candidate in \
	"${RUNFILES_DIR:-}/_main/${HOOK_REL}" \
	"${TEST_SRCDIR:-}/_main/${HOOK_REL}" \
	"${BASH_SOURCE[0]%/*}/check-crd-phase-enum.sh"; do
	if [[ -f "$candidate" ]]; then
		HOOK="$candidate"
		break
	fi
done
if [[ -z "$HOOK" ]]; then
	echo "ERROR: cannot locate check-crd-phase-enum.sh in runfiles" >&2
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
"""Minimal jq stub covering the expression used by check-crd-phase-enum.sh."""
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
# Filesystem fixtures
#
# Layout under $FIXTURE mimics a real operator:
#   projects/operators/my-op/
#     statemachine/
#       my_op_phases.go   -- phase constants (Pending, Ready, Unknown)
#       my_op_types.go    -- state machine types (no kubebuilder annotations)
#     api/
#       my_op_types.go    -- CRD types (Enum annotation for Phase field)
# ---------------------------------------------------------------------------
FIXTURE="${TEST_TMPDIR}/fixture"
PHASES_DIR="${FIXTURE}/projects/operators/my-op/statemachine"
API_DIR="${FIXTURE}/projects/operators/my-op/api"
mkdir -p "$PHASES_DIR" "$API_DIR"

# *_phases.go with Pending, Ready, Unknown
cat >"${PHASES_DIR}/my_op_phases.go" <<'GO'
package statemachine

const (
	PhasePending = "Pending"
	PhaseReady   = "Ready"
	PhaseUnknown = "Unknown"
)
GO

# *_types.go with all three phases in the enum (complete, no mismatch)
cat >"${API_DIR}/my_op_types.go" <<'GO'
package v1

type MyOpStatus struct {
	// +kubebuilder:validation:Enum=Pending;Ready;Unknown
	Phase string `json:"phase,omitempty"`
}
GO

# A second operator with an incomplete enum (missing Unknown)
MISSING_DIR="${FIXTURE}/projects/operators/broken-op"
mkdir -p "${MISSING_DIR}/statemachine" "${MISSING_DIR}/api"

cat >"${MISSING_DIR}/statemachine/broken_phases.go" <<'GO'
package statemachine

const (
	PhasePending = "Pending"
	PhaseReady   = "Ready"
	PhaseUnknown = "Unknown"
)
GO

cat >"${MISSING_DIR}/api/broken_types.go" <<'GO'
package v1

type BrokenStatus struct {
	// +kubebuilder:validation:Enum=Pending;Ready
	Phase string `json:"phase,omitempty"`
}
GO

# Operator with no phases file (to test early exit)
mkdir -p "${FIXTURE}/projects/operators/no-phases-op/api"
cat >"${FIXTURE}/projects/operators/no-phases-op/api/nophases_types.go" <<'GO'
package v1

type NoPhasesStatus struct {
	// +kubebuilder:validation:Enum=Pending;Ready
	Phase string `json:"phase,omitempty"`
}
GO

# Operator with no enum annotation in the types file
mkdir -p "${FIXTURE}/projects/operators/no-enum-op/statemachine"
cat >"${FIXTURE}/projects/operators/no-enum-op/statemachine/noenum_phases.go" <<'GO'
package statemachine

const (
	PhasePending = "Pending"
)
GO
mkdir -p "${FIXTURE}/projects/operators/no-enum-op/api"
cat >"${FIXTURE}/projects/operators/no-enum-op/api/noenum_types.go" <<'GO'
package v1

// No Enum annotation here
type NoEnumStatus struct {
	Phase string `json:"phase,omitempty"`
}
GO

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

# run_test NAME FILE_PATH WANT_STDERR_RE
#   Hook always exits 0; WANT_STDERR_RE="" means no output expected.
run_test() {
	local name="$1"
	local file_path="$2"
	local want_stderr_re="$3"

	local esc_path="${file_path//\\/\\\\}"
	esc_path="${esc_path//\"/\\\"}"
	local input_json
	input_json=$(printf '{"tool_input":{"file_path":"%s"}}' "$esc_path")

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
	"" \
	""

# Manually test with empty JSON object
EMPTY_STDERR=$(printf '{}' | bash "$HOOK" 2>&1 >/dev/null || true)
if [[ -n "$EMPTY_STDERR" ]]; then
	echo "FAIL [empty_json_object]: unexpected stderr: $(printf '%q' "$EMPTY_STDERR")"
	FAIL=$((FAIL + 1))
else
	echo "PASS [empty_json_object]"
	PASS=$((PASS + 1))
fi

# 2. Non-matching file extension (values.yaml)
run_test "non_matching_extension" \
	"${FIXTURE}/projects/operators/my-op/api/values.yaml" \
	""

# 3. File not under projects/operators/
run_test "not_under_operators" \
	"${FIXTURE}/projects/myservice/api/my_types.go" \
	""

# 4. *_phases.go not under projects/operators/
run_test "phases_file_not_under_operators" \
	"${FIXTURE}/projects/myservice/statemachine/my_phases.go" \
	""

# 5. *_types.go directly under projects/operators/ (no subdirectory = no operator root)
#    sed extraction would give the path without a trailing slash, which is the
#    operator root itself (a directory) — but the file is directly in it. Let's
#    test with a path that is directly at the operators level (edge case).
run_test "file_directly_under_operators" \
	"${FIXTURE}/projects/operators/some_types.go" \
	""

# ---------------------------------------------------------------------------
# Tests: complete operator — all phases in enum, no warning
# ---------------------------------------------------------------------------

# 6. Editing *_types.go in complete operator — no warning
run_test "complete_op_types_no_warning" \
	"${API_DIR}/my_op_types.go" \
	""

# 7. Editing *_phases.go in complete operator — no warning
run_test "complete_op_phases_no_warning" \
	"${PHASES_DIR}/my_op_phases.go" \
	""

# ---------------------------------------------------------------------------
# Tests: broken operator — phase missing from enum, warning expected
# ---------------------------------------------------------------------------

# 8. Editing *_types.go in broken operator — warns about missing Unknown
run_test "broken_op_types_warns" \
	"${MISSING_DIR}/api/broken_types.go" \
	"WARNING:"

# 9. Editing *_phases.go in broken operator — warns about missing Unknown
run_test "broken_op_phases_warns" \
	"${MISSING_DIR}/statemachine/broken_phases.go" \
	"WARNING:"

# 10. Warning message mentions the specific missing value
run_test "warning_mentions_unknown" \
	"${MISSING_DIR}/statemachine/broken_phases.go" \
	"Unknown"

# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

# 11. Operator with no *_phases.go files — skipped gracefully
run_test "no_phases_file_no_warning" \
	"${FIXTURE}/projects/operators/no-phases-op/api/nophases_types.go" \
	""

# 12. Operator with no Enum annotation in types — skipped gracefully
run_test "no_enum_annotation_no_warning" \
	"${FIXTURE}/projects/operators/no-enum-op/statemachine/noenum_phases.go" \
	""

# 13. Non-existent operator root directory — skipped gracefully
run_test "nonexistent_operator_root" \
	"${FIXTURE}/projects/operators/does-not-exist/api/foo_types.go" \
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
