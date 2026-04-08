#!/bin/bash
# PreToolUse hook: warns when a phase constant defined in *_phases.go is missing
# from the +kubebuilder:validation:Enum annotation for the Phase field in *_types.go.
#
# Context: PR #1883 fixed a bug where PhaseUnknown = "Unknown" existed in
# model_cache_phases.go but "Unknown" was missing from the Enum annotation in
# modelcache_types.go, causing SSA status patches to be rejected by the API server.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: always (warning only, never blocks)
# Exit 2: never (this hook only warns)

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check *_types.go and *_phases.go files
if [[ -z "$FILE_PATH" ]]; then
	exit 0
fi
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" != *_types.go ]] && [[ "$BASENAME" != *_phases.go ]]; then
	exit 0
fi

# Must be under projects/operators/
if ! echo "$FILE_PATH" | grep -q '/projects/operators/'; then
	exit 0
fi

# Derive operator root: everything up to projects/operators/<operator-name>
OPERATOR_ROOT=$(echo "$FILE_PATH" | sed 's|\(.*projects/operators/[^/]*\)/.*|\1|')
if [[ -z "$OPERATOR_ROOT" ]] || [[ ! -d "$OPERATOR_ROOT" ]]; then
	exit 0
fi

# Find all *_phases.go files under the operator root
mapfile -t PHASES_FILES < <(find "$OPERATOR_ROOT" -name "*_phases.go" 2>/dev/null | sort)
if [[ ${#PHASES_FILES[@]} -eq 0 ]]; then
	exit 0
fi

# Find all *_types.go files under the operator root
mapfile -t TYPES_FILES < <(find "$OPERATOR_ROOT" -name "*_types.go" 2>/dev/null | sort)
if [[ ${#TYPES_FILES[@]} -eq 0 ]]; then
	exit 0
fi

# Extract phase constant string values from *_phases.go files.
# Matches lines like:   PhaseFoo = "Bar"
mapfile -t PHASE_VALUES < <(grep -hE '^\s+Phase[A-Za-z]+ = "[^"]+"' "${PHASES_FILES[@]}" 2>/dev/null |
	sed 's/.*"\([^"]*\)".*/\1/' | sort -u)

if [[ ${#PHASE_VALUES[@]} -eq 0 ]]; then
	exit 0
fi

# Extract the Enum annotation value for the Phase field from *_types.go files.
# Use awk: remember the last +kubebuilder:validation:Enum= annotation seen;
# when we encounter a "Phase string" field, emit the remembered annotation.
ENUM_ANNOTATION=$(awk '
	/\+kubebuilder:validation:Enum=/ { last_enum = $0 }
	/Phase[[:space:]]+string/ { if (last_enum != "") { print last_enum; last_enum = "" } }
' "${TYPES_FILES[@]}" 2>/dev/null | grep -o 'Enum=[^[:space:]]*' | sed 's/Enum=//' | head -1 || true)

if [[ -z "$ENUM_ANNOTATION" ]]; then
	exit 0
fi

# Split enum values by semicolon
IFS=';' read -ra ENUM_VALUES <<<"$ENUM_ANNOTATION"

# Check each phase constant value against the enum
MISSING=()
for phase_val in "${PHASE_VALUES[@]}"; do
	[[ -z "$phase_val" ]] && continue
	found=false
	for ev in "${ENUM_VALUES[@]}"; do
		if [[ "$ev" == "$phase_val" ]]; then
			found=true
			break
		fi
	done
	if ! $found; then
		MISSING+=("$phase_val")
	fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
	MISSING_STR=$(printf '%s;' "${MISSING[@]}")
	MISSING_STR="${MISSING_STR%;}" # trim trailing semicolon
	cat >&2 <<-EOF
		WARNING: Phase constant(s) in *_phases.go are missing from the
		+kubebuilder:validation:Enum annotation in *_types.go:

		$(printf '  %s\n' "${MISSING[@]}")

		Missing values cause the API server to reject status patches when the
		controller transitions to those phases (SSA conflict). See PR #1883.

		Fix: add the missing value(s) to the Enum annotation in *_types.go:
		  // +kubebuilder:validation:Enum=${ENUM_ANNOTATION};${MISSING_STR}
		  Phase string \`json:"phase,omitempty"\`

		Then regenerate CRD manifests: operator-sdk generate manifests
	EOF
fi

# Always allow — this is a warning, not a blocker
exit 0
