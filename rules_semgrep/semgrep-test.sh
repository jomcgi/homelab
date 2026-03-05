#!/usr/bin/env bash
# semgrep-test.sh - Runs semgrep-core directly against source files
#
# Usage: semgrep-test.sh <rule-files...> -- <source-files...> [-- <lockfile-files...>]
#
# The semgrep-core binary is discovered via find(1) in runfiles rather than
# passed as an argument, because the engine filegroup may be empty when GHCR
# credentials are missing (graceful degradation).
#
# Exit code 0 = no findings, non-zero = semgrep found violations.
#
# Env: SEMGREP_EXCLUDE_RULES — comma-separated items to skip. Each item is used in two ways:
#      1. Matched against YAML filename (basename without .yaml) to exclude entire config files
#      2. Matched as a suffix against semgrep check_ids to exclude individual rule findings
# Env: SEMGREP_TEST_MODE — if "1", emits warning and exits 0 (test mode requires pysemgrep)
#      UPLOAD_SCRIPT     — path to upload binary; uploads results to Semgrep App

set -euo pipefail

if [[ $# -lt 2 ]]; then
	echo "Usage: $0 <rule-files...> -- <source-files...>"
	exit 1
fi

# Discover semgrep-core from runfiles. The engine filegroup may be empty
# (no GHCR token / empty digest) — in that case, skip gracefully.
# Search RUNFILES_DIR (not cwd) because external repo files live in sibling
# directories (e.g. +semgrep+semgrep_engine_arm64/) outside _main/.
# Use -type f -o -type l to match both regular files and symlinks.
SEARCH_ROOT="${RUNFILES_DIR:-.}"
SEMGREP_CORE=$(find "$SEARCH_ROOT" -name "semgrep-core" -not -name "*proprietary*" \( -type f -o -type l \) 2>/dev/null | head -1)
if [[ -z "$SEMGREP_CORE" || ! -x "$SEMGREP_CORE" ]]; then
	echo "SKIPPED: semgrep-core binary not found in runfiles (GHCR credentials may be missing)"
	exit 0
fi

# Verify the binary can actually execute on this platform (the OCI-vendored
# engine is a Linux ELF binary — it won't run on macOS).
if ! "$SEMGREP_CORE" -version >/dev/null 2>&1; then
	echo "SKIPPED: semgrep-core found but cannot execute on this platform ($(uname -s)/$(uname -m))"
	exit 0
fi

# Select engine: use pro engine if available in runfiles, otherwise use OSS semgrep-core.
# The pro_engine filegroup may be empty (no token/digest) — find returns nothing → OSS only.
ENGINE="$SEMGREP_CORE"
SEMGREP_PRO_ENGINE=$(find "$SEARCH_ROOT" -name "semgrep-core-proprietary" \( -type f -o -type l \) 2>/dev/null | head -1)
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

# Collect source files until we hit another -- separator (or end of args)
SOURCE_ARGS=()
while [[ $# -gt 0 && "$1" != "--" ]]; do
	SOURCE_ARGS+=("$1")
	shift
done

# Collect lockfile files after the optional second --
LOCKFILE_ARGS=()
if [[ $# -gt 0 && "$1" == "--" ]]; then
	shift # skip second --
	LOCKFILE_ARGS=("$@")
fi

# Copy source files to a temp directory — semgrep-core needs real file paths
SCAN_DIR="${TEST_TMPDIR}/scan"
mkdir -p "$SCAN_DIR"
SOURCE_FILES=()
for f in "${SOURCE_ARGS[@]}"; do
	mkdir -p "$SCAN_DIR/$(dirname "$f")"
	cp "$f" "$SCAN_DIR/$f"
	SOURCE_FILES+=("$SCAN_DIR/$f")
done

# Copy lockfile files to scan directory
LOCKFILE_FILES=()
for f in "${LOCKFILE_ARGS[@]}"; do
	mkdir -p "$SCAN_DIR/$(dirname "$f")"
	cp "$f" "$SCAN_DIR/$f"
	LOCKFILE_FILES+=("$SCAN_DIR/$f")
done

# Map file extension to semgrep language identifier
detect_lang() {
	case "${1##*.}" in
	py) echo "python" ;;
	go) echo "go" ;;
	js | jsx) echo "javascript" ;;
	ts | tsx) echo "typescript" ;;
	yaml | yml) echo "yaml" ;;
	sh | bash) echo "bash" ;;
	tf) echo "terraform" ;;
	json) echo "json" ;;
	c | h) echo "c" ;;
	cpp | cc | cxx) echo "cpp" ;;
	java) echo "java" ;;
	rb) echo "ruby" ;;
	rs) echo "rust" ;;
	*) echo "" ;;
	esac
}

# Map lockfile filename to semgrep-core lockfile_kind enum
detect_lockfile_kind() {
	local basename
	basename="$(basename "$1")"
	case "$basename" in
	go.sum) echo "GoModLock" ;;
	requirements*.txt | requirements*.pip) echo "PipRequirementsTxt" ;;
	poetry.lock) echo "PoetryLock" ;;
	Pipfile.lock) echo "PipfileLock" ;;
	uv.lock) echo "UvLock" ;;
	package-lock.json) echo "NpmPackageLockJson" ;;
	yarn.lock) echo "YarnLock" ;;
	pnpm-lock.yaml) echo "PnpmLock" ;;
	*) echo "" ;;
	esac
}

# Determine products and dependency_source based on lockfiles
HAS_LOCKFILES=false
LOCKFILE_JSON=""
if [[ ${#LOCKFILE_FILES[@]} -gt 0 ]]; then
	HAS_LOCKFILES=true
	# Use the first lockfile for dependency_source (semgrep deduplicates internally)
	LF="${LOCKFILE_FILES[0]}"
	LF_KIND=$(detect_lockfile_kind "$LF")
	if [[ -n "$LF_KIND" ]]; then
		LF_ABS="$(cd "$(dirname "$LF")" && pwd)/$(basename "$LF")"
		LOCKFILE_JSON=$(printf ',"dependency_source":["LockfileOnly",{"kind":"%s","path":"%s"}]' "$LF_KIND" "$LF_ABS")
	fi
fi

PRODUCTS='["sast"]'
if [[ "$HAS_LOCKFILES" == "true" ]]; then
	PRODUCTS='["sast","sca"]'
fi

# Generate targets JSON in semgrep-core's ATD format
TARGETS_FILE="${TEST_TMPDIR}/targets.json"
{
	echo -n '["Targets",['
	first=true

	# CodeTargets for source files
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
		echo -n "$(printf '["CodeTarget",{"path":{"fpath":"%s","ppath":"%s"},"analyzer":"%s","products":%s%s}]' \
			"$abs_path" "$abs_path" "$lang" "$PRODUCTS" "$LOCKFILE_JSON")"
	done

	# DependencySourceTargets for lockfile-only mode (no source files)
	if [[ ${#SOURCE_FILES[@]} -eq 0 && "$HAS_LOCKFILES" == "true" ]]; then
		for lf in "${LOCKFILE_FILES[@]}"; do
			lf_kind=$(detect_lockfile_kind "$lf")
			if [[ -z "$lf_kind" ]]; then
				continue
			fi
			lf_abs="$(cd "$(dirname "$lf")" && pwd)/$(basename "$lf")"
			if [[ "$first" == "true" ]]; then
				first=false
			else
				echo -n ','
			fi
			echo -n "$(printf '["DependencySourceTarget",["LockfileOnly",{"kind":"%s","path":"%s"}]]' "$lf_kind" "$lf_abs")"
		done
	fi

	echo ']]'
} >"$TARGETS_FILE"

# Run semgrep-core once per rule file, merge JSON results
RESULTS_DIR="${TEST_TMPDIR}/results"
mkdir -p "$RESULTS_DIR"
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
	fi

	RESULT_INDEX=$((RESULT_INDEX + 1))
done

# Merge results into a single JSON and determine findings
MERGED_FILE="${TEST_TMPDIR}/results.json"
SCAN_EXIT=0
python3 - "$RESULTS_DIR" "$MERGED_FILE" <<'PYEOF' || SCAN_EXIT=$?
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
