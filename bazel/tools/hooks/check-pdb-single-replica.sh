#!/bin/bash
# PreToolUse hook: warns when writing/editing deploy values or PDB template files
# that configure podDisruptionBudget.minAvailable >= 1 without evidence of multiple
# replicas. On a single-replica deployment, minAvailable: 1 leaves a zero disruption
# budget, blocking all voluntary evictions (node drains, cluster upgrades).
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the operation (with optional warning on stderr)
# Exit 2: block the operation (not used here — warning only)
#
# References: PR #1474 (added PDB with minAvailable:1) and PR #1482 (reverted it)

set -euo pipefail

INPUT=$(cat)

# Extract file path and content from Write (content) or Edit (new_string) tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [[ -z "$CONTENT" ]]; then
	exit 0
fi

# Only check deploy/values.yaml and templates/pdb.yaml files
IS_TARGET_FILE=false
if echo "$FILE_PATH" | grep -qE '.*/deploy/values\.yaml$'; then
	IS_TARGET_FILE=true
elif echo "$FILE_PATH" | grep -qE '.*/templates/pdb\.yaml$'; then
	IS_TARGET_FILE=true
fi

if ! $IS_TARGET_FILE; then
	exit 0
fi

# Check if minAvailable is configured with a value >= 1
if ! echo "$CONTENT" | grep -qE '^\s*minAvailable\s*:\s*[1-9][0-9]*\s*$'; then
	exit 0
fi

# Extract the minAvailable value
MIN_AVAIL=$(echo "$CONTENT" | grep -E '^\s*minAvailable\s*:\s*[1-9][0-9]*\s*$' | \
	grep -oE '[1-9][0-9]*' | head -1)

# Check if there is evidence of multiple replicas (replicaCount > 1)
# Look for replicaCount: N where N >= 2
HAS_MULTI_REPLICA=false
if echo "$CONTENT" | grep -qE '^\s*replicaCount\s*:\s*[2-9][0-9]*\s*$'; then
	HAS_MULTI_REPLICA=true
fi

if $HAS_MULTI_REPLICA; then
	# Multiple replicas configured — might still be problematic if minAvailable >= replicaCount,
	# but that's harder to check here. Warn only if minAvailable equals replicaCount.
	REPLICA_COUNT=$(echo "$CONTENT" | grep -E '^\s*replicaCount\s*:\s*[0-9]+\s*$' | \
		grep -oE '[0-9]+' | head -1)
	if [[ -n "$REPLICA_COUNT" ]] && [[ "$MIN_AVAIL" -ge "$REPLICA_COUNT" ]]; then
		cat >&2 <<-EOF
			WARNING: podDisruptionBudget.minAvailable ($MIN_AVAIL) >= replicaCount ($REPLICA_COUNT).
			This leaves a zero disruption budget — no pods can be evicted voluntarily,
			blocking node drains and cluster upgrades.

			Recommendation: use maxUnavailable: 1 instead of minAvailable, or set
			minAvailable < replicaCount.

			Reference: PR #1474 (added) → PR #1482 (reverted) — same anti-pattern.
			See also: bazel/semgrep/rules/kubernetes/pdb-minAvailable-blocks-eviction.yaml
		EOF
	fi
	exit 0
fi

# No replicaCount found (defaults to 1) or replicaCount: 1 — minAvailable: N >= 1
# means zero disruption budget.
cat >&2 <<-EOF
	WARNING: podDisruptionBudget.minAvailable: $MIN_AVAIL with replicaCount: 1 (or absent,
	defaulting to 1) creates a zero disruption budget. No pods can be evicted voluntarily,
	blocking node drains and cluster upgrades.

	Recommendation: use maxUnavailable: 1 instead of minAvailable: 1, or increase
	replicaCount above minAvailable.

	Reference: PR #1474 (added PDB with minAvailable:1) → PR #1482 (reverted it immediately).
	See also: bazel/semgrep/rules/kubernetes/pdb-minAvailable-blocks-eviction.yaml
EOF

# Always allow — this is a warning, not a blocker
exit 0
