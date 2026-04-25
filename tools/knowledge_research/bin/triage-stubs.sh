#!/usr/bin/env bash
# Triage gap stubs in _researching/ — flag already-covered, misclassified,
# or garbage stubs before spending tokens on real research.
#
# Usage:
#   triage-stubs.sh [--vault PATH] [--limit N] [--filter REGEX] [--batch-size N]
#
# Output: a markdown report at <vault>/.opus-research/triage-<UTC>.md.
# The wrapper does NOT promote this file — it is a working document for
# review, not a vault note. You decide what bulk actions to take based
# on the report.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SELF_DIR/../prompts/triage-stubs.system.md"
[ -f "$PROMPT_FILE" ] || {
	echo "missing prompt: $PROMPT_FILE" >&2
	exit 1
}

VAULT="${VAULT:-}"
LIMIT=100
FILTER=""
BATCH_SIZE=25

while [ $# -gt 0 ]; do
	case "$1" in
	--vault)
		VAULT="$2"
		shift 2
		;;
	--limit)
		LIMIT="$2"
		shift 2
		;;
	--filter)
		FILTER="$2"
		shift 2
		;;
	--batch-size)
		BATCH_SIZE="$2"
		shift 2
		;;
	-h | --help)
		sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
		exit 0
		;;
	*)
		echo "unknown arg: $1" >&2
		exit 2
		;;
	esac
done

[ -n "$VAULT" ] || {
	echo "set VAULT env var or pass --vault PATH" >&2
	exit 2
}
[ -d "$VAULT/_researching" ] || {
	echo "no _researching/ dir at $VAULT" >&2
	exit 2
}

STAGING="$VAULT/.opus-research"
mkdir -p "$STAGING"

cd "$VAULT"

# Quick eligibility count for the user.
shopt -s nullglob
all=0
eligible=0
for stub in _researching/*.md; do
	all=$((all + 1))
	slug="$(basename "$stub" .md)"
	[ -f "$slug.md" ] && continue
	[ -f "$STAGING/$slug.md" ] && continue
	if [ -n "$FILTER" ] && [[ ! "$slug" =~ $FILTER ]]; then
		continue
	fi
	eligible=$((eligible + 1))
done
shopt -u nullglob

[ "$eligible" = "0" ] && {
	echo "no eligible stubs (total: $all)"
	exit 0
}

# Cap eligible at limit.
to_process=$eligible
[ "$to_process" -gt "$LIMIT" ] && to_process="$LIMIT"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
report_path="$STAGING/triage-$ts.md"

echo "Triaging $to_process stubs (of $eligible eligible / $all total)"
echo "Batch size: $BATCH_SIZE"
echo "Report path: $report_path"
echo

claude --print \
	--model claude-opus-4-7 \
	--append-system-prompt "$(cat "$PROMPT_FILE")" \
	--add-dir "$VAULT" \
	"Triage gap stubs in this vault. Working directory is the vault root. Process up to $to_process stubs in batches of $BATCH_SIZE.${FILTER:+ Filter slugs by regex: $FILTER.} Write the consolidated report to \`.opus-research/triage-$ts.md\` per the system prompt."

if [ -f "$report_path" ]; then
	echo
	echo "Report written: $report_path"
	echo
	echo "Top-of-file summary:"
	head -30 "$report_path"
else
	echo "WARN: expected report not written at $report_path" >&2
	exit 3
fi
