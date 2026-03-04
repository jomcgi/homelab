#!/usr/bin/env bash
# semgrep-manifest-test.sh - Renders Helm manifests and scans with semgrep
#
# Usage: semgrep-manifest-test.sh <semgrep> <pysemgrep> <helm> <release> <chart> <namespace> <rules...> -- <values-files...>
#
# Combines helm template rendering with semgrep scanning in a single test.
# Exit code 0 = no findings, non-zero = violations found or render failure.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated items to skip. Each item is used in two ways:
#      1. Matched against YAML filename (basename without .yaml) to exclude entire config files
#      2. Matched as a suffix against semgrep check_ids to exclude individual rule findings
#         (osemgrep prefixes rule IDs with the config file path, so suffix matching is required)
#      UPLOAD_SCRIPT          — path to upload binary; uploads results to Semgrep App

set -euo pipefail

if [[ $# -lt 7 ]]; then
	echo "Usage: $0 <semgrep> <pysemgrep> <helm> <release> <chart> <namespace> <rules...> -- <values...>"
	exit 1
fi

SEMGREP="$1"
PYSEMGREP="$2"
HELM="$3"
RELEASE="$4"
CHART="$5"
NAMESPACE="$6"
shift 6

# osemgrep (native engine) execs pysemgrep at runtime — add it to PATH
export PATH="$(dirname "$PYSEMGREP"):$PATH"

# Set up pro engine if available — semgrep looks for semgrep-core-proprietary
# next to semgrep-core. We use SEMGREP_CORE_BIN to redirect both to a temp dir.
# The engine binary is discovered via find rather than env var, because the
# pro_engine filegroup may be empty (no token/digest) and Bazel's $(rootpaths)
# errors on empty filegroups. When empty, find returns nothing → community only.
PRO_FLAG=""
SEMGREP_PRO_ENGINE=$(find . -name "semgrep-core-proprietary" -type f 2>/dev/null | head -1)
if [[ -n "$SEMGREP_PRO_ENGINE" ]]; then
	SEMGREP_CORE=$(find . -name "semgrep-core" -not -name "*proprietary*" -type f 2>/dev/null | head -1)
	if [[ -z "$SEMGREP_CORE" ]]; then
		echo "INFO: semgrep-core not found — running community analysis only"
	else
		PRO_DIR="${TEST_TMPDIR}/pro_bin"
		mkdir -p "$PRO_DIR"
		cp "$SEMGREP_CORE" "$PRO_DIR/semgrep-core"
		chmod 755 "$PRO_DIR/semgrep-core"
		cp "$SEMGREP_PRO_ENGINE" "$PRO_DIR/semgrep-core-proprietary"
		chmod 755 "$PRO_DIR/semgrep-core-proprietary"
		export SEMGREP_CORE_BIN="$PRO_DIR/semgrep-core"
		PRO_FLAG="--pro"
	fi
fi

# Parse exclude items: filename-based exclusion (EXCLUDE_LIST) and
# rule-ID-based exclusion (EXCLUDE_IDS). osemgrep prefixes rule IDs with
# the full config file path, so --exclude-rule can't match. Instead we
# run with --json and post-filter results by suffix matching.
EXCLUDE_LIST=",${SEMGREP_EXCLUDE_RULES:-},"
EXCLUDE_IDS=()
if [[ -n "${SEMGREP_EXCLUDE_RULES:-}" ]]; then
	IFS=',' read -ra _EXCLUDE_ITEMS <<<"$SEMGREP_EXCLUDE_RULES"
	for _item in "${_EXCLUDE_ITEMS[@]}"; do
		_item="${_item## }"
		_item="${_item%% }"
		if [[ -n "$_item" ]]; then
			EXCLUDE_IDS+=("$_item")
		fi
	done
fi

# Collect rule files until -- separator, skipping excluded rules
RULES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	rule_name="$(basename "$1" .yaml)"
	if [[ "$EXCLUDE_LIST" != *",$rule_name,"* ]]; then
		RULES+=("--config" "$1")
	fi
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and values files"
	exit 1
fi
shift # skip --

# Build values arguments
VALUES_ARGS=()
for vf in "$@"; do
	VALUES_ARGS+=("--values" "$vf")
done

# Render manifests to a temp file with .yaml extension (semgrep needs it)
MANIFESTS="${TEST_TMPDIR}/rendered-manifests.yaml"

echo "Rendering manifests:"
echo "  Release:   $RELEASE"
echo "  Chart:     $CHART"
echo "  Namespace: $NAMESPACE"
echo "  Values:    $*"

if ! "$HELM" template "$RELEASE" "$CHART" \
	--namespace "$NAMESPACE" \
	"${VALUES_ARGS[@]}" >"$MANIFESTS"; then
	echo "FAILED: Helm template rendering failed"
	exit 1
fi

echo ""
echo "Scanning rendered manifests with semgrep:"
echo "  Rules: ${RULES[*]:-none}"
echo ""

if [[ ${#RULES[@]} -eq 0 ]]; then
	echo "PASSED: All rules excluded, nothing to scan"
	exit 0
fi

# Run semgrep with JSON output for both upload and post-filtering
SCAN_EXIT=0
"$SEMGREP" "${RULES[@]}" $PRO_FLAG --error --metrics=off --no-git-ignore \
	--json --output "$TEST_TMPDIR/results.json" \
	"$MANIFESTS" || SCAN_EXIT=$?

# Best-effort upload (never affects exit code)
if [[ -n "${SEMGREP_APP_TOKEN:-}" && -n "${UPLOAD_SCRIPT:-}" ]]; then
	"$UPLOAD_SCRIPT" "$TEST_TMPDIR/results.json" "$SCAN_EXIT" 2>&1 || true
fi

# When rule-ID exclusions are set, post-filter the JSON results.
# osemgrep prefixes check_ids with the config file path (e.g.,
# Users.jomcgi...kubernetes.yaml.<rule-id>), so we use suffix matching.
if [[ "$SCAN_EXIT" -ne 0 && ${#EXCLUDE_IDS[@]} -gt 0 ]]; then
	if python3 - "$TEST_TMPDIR/results.json" "${EXCLUDE_IDS[@]}" <<'PYEOF'; then
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)
exclude_ids = sys.argv[2:]
results = data.get("results", [])
filtered, excluded = [], 0
for r in results:
    cid = r.get("check_id", "")
    if any(cid.endswith("." + e) or cid == e for e in exclude_ids):
        excluded += 1
    else:
        filtered.append(r)
if filtered:
    for r in filtered:
        cid = r.get("check_id", "")
        parts = cid.rsplit(".", 2)
        short = ".".join(parts[-2:]) if len(parts) >= 2 else cid
        path = r.get("path", "?")
        line = r.get("start", {}).get("line", "?")
        msg = r.get("extra", {}).get("message", "")
        print(f"  {short} at {path}:{line}")
        if msg:
            print(f"    {msg[:200]}")
        print()
    print(f"Found {len(filtered)} finding(s) ({excluded} excluded)")
    sys.exit(1)
if excluded:
    print(f"  ({excluded} finding(s) excluded by rule ID filter)")
sys.exit(0)
PYEOF
		SCAN_EXIT=0
	fi
fi

if [[ "$SCAN_EXIT" -eq 0 ]]; then
	echo "PASSED: No semgrep findings in rendered manifests"
else
	echo ""
	echo "FAILED: Semgrep found violations in rendered manifests"
fi
exit "$SCAN_EXIT"
