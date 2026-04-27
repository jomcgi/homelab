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
skipped_keep=0
skipped_discardable=0
for stub in _researching/*.md; do
	all=$((all + 1))
	slug="$(basename "$stub" .md)"
	[ -f "$slug.md" ] && continue
	[ -f "$STAGING/$slug.md" ] && continue
	# Skip stubs a prior triage round already classified.
	triaged="$(awk '/^triaged:/ {print $2; exit}' "$stub" | tr -d '"')"
	case "$triaged" in
	keep)
		skipped_keep=$((skipped_keep + 1))
		continue
		;;
	discardable)
		skipped_discardable=$((skipped_discardable + 1))
		continue
		;;
	esac
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

echo "Triaging $to_process stubs (of $eligible eligible / $all total; $skipped_keep keep, $skipped_discardable discardable already triaged)"
echo "Batch size: $BATCH_SIZE"
echo "Report path: $report_path"
echo

# nosemgrep: bazel.semgrep.rules.shell.claude-print-missing-permission-mode -- --permission-mode is on the next line; the rule doesn't follow `\`-continuations.
claude --print \
	--model claude-opus-4-7 \
	--permission-mode acceptEdits \
	--append-system-prompt "$(cat "$PROMPT_FILE")" \
	--add-dir "$VAULT" \
	-- \
	"Triage gap stubs in this vault. Working directory is the vault root. Process up to $to_process stubs in batches of $BATCH_SIZE.${FILTER:+ Filter slugs by regex: $FILTER.} Write the consolidated report to \`.opus-research/triage-$ts.md\` per the system prompt."

if [ ! -f "$report_path" ]; then
	echo "WARN: expected report not written at $report_path" >&2
	exit 3
fi

echo
echo "Report written: $report_path"

mark_section() {
	# $1 = decision (keep | discardable)
	# remaining args = section header regex (e.g. "Valid (external|internal)")
	local decision="$1"
	shift
	local section_regex="$1"
	local slugs
	slugs=$(awk -v re="$section_regex" '
		$0 ~ "^## " re { in_section=1; next }
		in_section && /^## /          { in_section=0 }
		in_section && /^\| [a-z0-9]/ {
			gsub(/^\| /, "")
			gsub(/ \|.*$/, "")
			print
		}
	' "$report_path")

	local count=0
	while IFS= read -r slug; do
		[ -z "$slug" ] && continue
		# Defensive: ignore obvious table sentinels like "_none_".
		[[ "$slug" == _* ]] && continue
		local stub="_researching/$slug.md"
		[ ! -f "$stub" ] && continue
		# Skip if already marked the same way (idempotent).
		local existing
		existing="$(awk '/^triaged:/ {print $2; exit}' "$stub" | tr -d '"')"
		[ "$existing" = "$decision" ] && continue
		local tmp
		tmp=$(mktemp)
		awk -v decision="$decision" '
			BEGIN { inserted = 0 }
			NR == 1 && /^---$/ { print; next }
			# If a different triaged: line already exists, replace it.
			!inserted && /^triaged:/ {
				print "triaged: " decision
				inserted = 1
				next
			}
			!inserted && /^[a-zA-Z]/ {
				print "triaged: " decision
				inserted = 1
			}
			{ print }
		' "$stub" >"$tmp" && mv "$tmp" "$stub"
		count=$((count + 1))
	done <<<"$slugs"
	echo "$count"
}

# `triaged: keep` for real research targets — wrapper skips them so they
# don't get re-triaged, and research-gap.sh can pick them up.
marked_keep=$(mark_section keep "Valid (external|internal)")

# `triaged: discardable` instructs the gardener to close out the gap.
# When KNOWLEDGE_GAPS_REWRITE_DISCARDABLE is on, discover_gaps detects
# this marker, rewrites every [[X]] -> bare text in source notes that
# linked to it, then tombstones the gap row + stub once no references
# remain. Convergence takes two discover_gaps cycles after the marker
# lands: cycle one rewrites, the reconciler picks up the hash change
# and rebuilds note_links, cycle two tombstones.
marked_discardable=0
for section in "Already covered" "Garbage" "Misclassified"; do
	count=$(mark_section discardable "$section")
	marked_discardable=$((marked_discardable + count))
done

[ "$marked_keep" -gt 0 ] && echo "Marked $marked_keep stub(s) as triaged: keep."
[ "$marked_discardable" -gt 0 ] && echo "Marked $marked_discardable stub(s) as triaged: discardable."

echo
echo "Top-of-file summary:"
head -30 "$report_path"
