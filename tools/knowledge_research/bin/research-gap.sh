#!/usr/bin/env bash
# Batch-research external gaps via Opus 4.7.
#
# Usage:
#   research-gap.sh [--max N] [--vault PATH] [--filter PATTERN]
#
# Iterates _researching/*.md, skips already-researched and non-external
# gaps, invokes claude per stub. Resumable.
#
# Two-step write flow:
#   1. Opus writes to <vault>/.opus-research/<slug>.md (Phase A skips
#      dot-prefixed dirs, so no race with the ingest job).
#   2. After claude exits cleanly, this script atomically promotes the
#      staged file to <vault>/<slug>.md, where Phase A picks it up.

set -euo pipefail

# Resolve our prompt regardless of cwd.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SELF_DIR/../prompts/research-external.system.md"
[ -f "$PROMPT_FILE" ] || {
	echo "missing prompt: $PROMPT_FILE" >&2
	exit 1
}

VAULT="${VAULT:-}"
MAX=50
FILTER=""

while [ $# -gt 0 ]; do
	case "$1" in
	--max)
		MAX="$2"
		shift 2
		;;
	--vault)
		VAULT="$2"
		shift 2
		;;
	--filter)
		FILTER="$2"
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

count=0
skipped_exists=0
skipped_class=0
failed=0
promoted=0

shopt -s nullglob
for stub in _researching/*.md; do
	[ "$count" -ge "$MAX" ] && break

	slug="$(basename "$stub" .md)"

	if [ -n "$FILTER" ] && [[ ! "$slug" =~ $FILTER ]]; then
		continue
	fi

	# Skip if already promoted at vault root, or already staged.
	if [ -f "$slug.md" ] || [ -f "$STAGING/$slug.md" ]; then
		skipped_exists=$((skipped_exists + 1))
		continue
	fi

	# Skip non-external fast (don't burn a Claude call).
	gap_class="$(awk '/^gap_class:/ {print $2; exit}' "$stub" | tr -d '"')"
	if [ "$gap_class" != "external" ]; then
		skipped_class=$((skipped_class + 1))
		continue
	fi

	echo "==> researching: $slug"
	if claude --print \
		--model claude-opus-4-7 \
		--permission-mode acceptEdits \
		--append-system-prompt "$(cat "$PROMPT_FILE")" \
		--add-dir "$VAULT" \
		-- \
		"Research the gap at \`_researching/${slug}.md\`. Vault root is the current working directory. Stage your output at \`.opus-research/${slug}.md\` per the system prompt — do not write at vault root, the wrapper handles promotion."; then
		count=$((count + 1))
	else
		echo "    FAILED: $slug — continuing" >&2
		failed=$((failed + 1))
		continue
	fi

	# Promote staged file to vault root.
	if [ -f "$STAGING/$slug.md" ]; then
		mv "$STAGING/$slug.md" "$slug.md"
		echo "    promoted: $slug.md"
		promoted=$((promoted + 1))
	else
		# Opus may have used a different filename (allowed). Promote any
		# files created during this run and not already at vault root.
		found_any=0
		while IFS= read -r staged; do
			base="$(basename "$staged")"
			if [ -f "$base" ]; then
				echo "    skip-promote (vault root collision): $base" >&2
				continue
			fi
			mv "$staged" "$base"
			echo "    promoted: $base"
			promoted=$((promoted + 1))
			found_any=1
		done < <(find "$STAGING" -maxdepth 1 -type f -name "*.md" -newer "$stub" 2>/dev/null)
		[ "$found_any" = "0" ] && echo "    NOTE: no staged file found for $slug — claude may have skipped it" >&2
	fi

	sleep 2 # rate-limit politeness
done

cat <<EOF

Done.
  researched (claude calls): $count
  promoted to vault root:    $promoted
  skipped (already exists):  $skipped_exists
  skipped (non-external):    $skipped_class
  failed:                    $failed
EOF
