#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep-core directly against source files
#
# Usage: semgrep-test.sh <semgrep-core> <rule-files...> -- <source-files...>
#
# Exit code 0 = no findings, non-zero = semgrep found violations.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated items to skip. Each item is used in two ways:
#      1. Matched against YAML filename (basename without .yaml) to exclude entire config files
#      2. Matched as a suffix against semgrep check_ids to exclude individual rule findings
# Env: SEMGREP_TEST_MODE — if "1", emits warning and exits 0 (test mode requires pysemgrep)
#      UPLOAD_SCRIPT     — path to upload binary; uploads results to Semgrep App

set -euo pipefail

if [[ $# -lt 3 ]]; then
	echo "Usage: $0 <semgrep-core> <rule-files...> -- <source-files...>"
	exit 1
fi

SEMGREP_CORE="$1"
shift

# Graceful degradation: if semgrep-core binary is empty (OCI artifact not fetched),
# skip the scan with a warning. Same pattern as the pro engine.
if [[ ! -x "$SEMGREP_CORE" ]]; then
	echo "SKIPPED: semgrep-core binary not found or not executable (GHCR credentials may be missing)"
	exit 0
fi

# Select engine: use pro engine if available in runfiles, otherwise use OSS semgrep-core.
# The pro_engine filegroup may be empty (no token/digest) — find returns nothing → OSS only.
ENGINE="$SEMGREP_CORE"
SEMGREP_PRO_ENGINE=$(find . -name "semgrep-core-proprietary" -type f 2>/dev/null | head -1)
if [[ -n "$SEMGREP_PRO_ENGINE" ]]; then
	# semgrep-core-proprietary needs semgrep-core alongside it in the same directory
	PRO_DIR="${TEST_TMPDIR}/pro_bin"
	mkdir -p "$PRO_DIR"
	cp "$SEMGREP_CORE" "$PRO_DIR/semgrep-core"
	chmod 755 "$PRO_DIR/semgrep-core"
	cp "$SEMGREP_PRO_ENGINE" "$PRO_DIR/semgrep-core-proprietary"
	chmod 755 "$PRO_DIR/semgrep-core-proprietary"
	ENGINE="$PRO_DIR/semgrep-core-proprietary"
fi

# Parse exclude items: filename-based exclusion (EXCLUDE_LIST) and
# rule-ID-based exclusion (EXCLUDE_IDS).
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

# Collect rule files until we hit the -- separator, skipping excluded rules
RULE_FILES=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	rule_name="$(basename "$1" .yaml)"
	if [[ "$EXCLUDE_LIST" != *",$rule_name,"* ]]; then
		RULE_FILES+=("$(pwd)/$1")
	fi
	shift
done

if [[ $# -eq 0 ]]; then
	echo "ERROR: missing -- separator between rules and source files"
	exit 1
fi
shift # skip --

if [[ ${#RULE_FILES[@]} -eq 0 ]]; then
	echo "PASSED: All rules excluded, nothing to scan"
	exit 0
fi

# Test mode requires pysemgrep's --test command (# ruleid: / # ok: annotations).
# semgrep-core doesn't support this — skip with a warning.
if [[ "${SEMGREP_TEST_MODE:-}" == "1" ]]; then
	echo "WARNING: SEMGREP_TEST_MODE=1 requires pysemgrep which is no longer bundled."
	echo "SKIPPED: Rule annotation testing deferred to pysemgrep-based test target."
	exit 0
fi

# Copy source files to a temp directory — semgrep-core needs real file paths
SCAN_DIR="${TEST_TMPDIR}/scan"
mkdir -p "$SCAN_DIR"
SOURCE_FILES=()
for f in "$@"; do
	mkdir -p "$SCAN_DIR/$(dirname "$f")"
	cp "$f" "$SCAN_DIR/$f"
	SOURCE_FILES+=("$SCAN_DIR/$f")
done

# Map file extension to semgrep language identifier
detect_lang() {
	case "${1##*.}" in
		py) echo "python" ;;
		go) echo "go" ;;
		js|jsx) echo "javascript" ;;
		ts|tsx) echo "typescript" ;;
		yaml|yml) echo "yaml" ;;
		sh|bash) echo "bash" ;;
		tf) echo "terraform" ;;
		json) echo "json" ;;
		c|h) echo "c" ;;
		cpp|cc|cxx) echo "cpp" ;;
		java) echo "java" ;;
		rb) echo "ruby" ;;
		rs) echo "rust" ;;
		*) echo "" ;;
	esac
}

# Generate targets JSON in semgrep-core's ATD format:
# ["Targets", [["CodeTarget", {"path": {...}, "analyzer": "...", "products": ["sast"]}]]]
TARGETS_FILE="${TEST_TMPDIR}/targets.json"
{
	echo -n '["Targets",['
	first=true
	for f in "${SOURCE_FILES[@]}"; do
		lang=$(detect_lang "$f")
		if [[ -z "$lang" ]]; then
			continue
		fi
		abs_path="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
		if [[ "$first" == "true" ]]; then
			first=false
		else
			echo -n ','
		fi
		echo -n "$(printf '["CodeTarget",{"path":{"fpath":"%s","ppath":"%s"},"analyzer":"%s","products":["sast"]}]' \
			"$abs_path" "$abs_path" "$lang")"
	done
	echo ']]'
} >"$TARGETS_FILE"

# Run semgrep-core once per rule file, merge JSON results
RESULTS_DIR="${TEST_TMPDIR}/results"
mkdir -p "$RESULTS_DIR"
HAS_FINDINGS=false
HAS_ERRORS=false
RESULT_INDEX=0

for rule_file in "${RULE_FILES[@]}"; do
	RESULT_FILE="$RESULTS_DIR/result_${RESULT_INDEX}.json"
	STDERR_FILE="${TEST_TMPDIR}/stderr_${RESULT_INDEX}.txt"
	SCAN_EXIT=0
	"$ENGINE" -rules "$rule_file" -targets "$TARGETS_FILE" -json -json_nodots \
		>"$RESULT_FILE" 2>"$STDERR_FILE" || SCAN_EXIT=$?

	if [[ "$SCAN_EXIT" -ne 0 ]]; then
		echo "WARNING: semgrep-core exited $SCAN_EXIT on $(basename "$rule_file")" >&2
		cat "$STDERR_FILE" >&2
		HAS_ERRORS=true
	fi

	RESULT_INDEX=$((RESULT_INDEX + 1))
done

# Merge results into a single JSON and determine findings
MERGED_FILE="${TEST_TMPDIR}/results.json"
SCAN_EXIT=0
python3 - "$RESULTS_DIR" "$MERGED_FILE" <<'PYEOF'
import json, glob, sys, os

results_dir = sys.argv[1]
output_file = sys.argv[2]
merged = {"results": [], "errors": []}

for f in sorted(glob.glob(os.path.join(results_dir, "result_*.json"))):
    try:
        data = json.load(open(f))
        merged["results"].extend(data.get("results", []))
        merged["errors"].extend(data.get("errors", []))
    except (json.JSONDecodeError, KeyError):
        pass

json.dump(merged, open(output_file, "w"))

# Exit 1 if there are findings (so the caller can detect)
if merged["results"]:
    sys.exit(1)
PYEOF
SCAN_EXIT=$?

# Best-effort upload (never affects exit code)
if [[ -n "${SEMGREP_APP_TOKEN:-}" && -n "${UPLOAD_SCRIPT:-}" && -f "$MERGED_FILE" ]]; then
	"$UPLOAD_SCRIPT" "$MERGED_FILE" "$SCAN_EXIT" 2>&1 || true
fi

# When rule-ID exclusions are set, post-filter the JSON results.
# semgrep-core check_ids may or may not be prefixed — suffix matching handles both.
if [[ "$SCAN_EXIT" -ne 0 && ${#EXCLUDE_IDS[@]} -gt 0 ]]; then
	if python3 - "$MERGED_FILE" "${EXCLUDE_IDS[@]}" <<'PYEOF'; then
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
	echo "PASSED: No semgrep findings"
else
	# Print findings summary from JSON so test logs are actionable
	python3 - "$MERGED_FILE" <<'PYEOF' 2>/dev/null || true
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get("results", []):
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
PYEOF
	echo "FAILED: Semgrep found violations"
fi
exit "$SCAN_EXIT"
