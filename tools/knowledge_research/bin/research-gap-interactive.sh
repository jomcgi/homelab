#!/usr/bin/env bash
# Interactively research an internal/personal gap with Opus 4.7.
#
# Usage:
#   research-gap-interactive.sh [--vault PATH] <slug>
#   research-gap-interactive.sh [--vault PATH] --pick      # fzf picker
#
# Drops you into a conversational claude session. Opus reads the stub
# and Joe's referenced notes, opens with a focused question, and after
# 3-5 turns drafts a note for review. Joe approves, exits the session,
# and this wrapper atomically promotes the staged file to vault root.
#
# Two-step write flow:
#   1. Opus writes/edits at <vault>/.opus-research/<slug>.md while you
#      converse. Phase A skips dot-prefixed dirs so no race.
#   2. On clean session exit, this wrapper moves the staged file to
#      <vault>/<slug>.md for Phase A to pick up.
#   3. If you Ctrl-C / abort, the staged file is left in place for you
#      to inspect or rerun.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SELF_DIR/../prompts/research-internal.system.md"
[ -f "$PROMPT_FILE" ] || {
	echo "missing prompt: $PROMPT_FILE" >&2
	exit 1
}

VAULT="${VAULT:-}"
PICK=0
SLUG=""
NO_PROMOTE=0

while [ $# -gt 0 ]; do
	case "$1" in
	--vault)
		VAULT="$2"
		shift 2
		;;
	--pick)
		PICK=1
		shift
		;;
	--no-promote)
		NO_PROMOTE=1
		shift
		;;
	-h | --help)
		sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
		exit 0
		;;
	*)
		if [ -z "$SLUG" ]; then
			SLUG="$1"
			shift
		else
			echo "unexpected arg: $1" >&2
			exit 2
		fi
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

if [ "$PICK" = "1" ]; then
	if ! command -v fzf >/dev/null 2>&1; then
		echo "--pick requires fzf; install via 'brew install fzf'" >&2
		exit 2
	fi
	candidates=$(
		for stub in _researching/*.md; do
			slug="$(basename "$stub" .md)"
			[ -f "$slug.md" ] && continue
			[ -f "$STAGING/$slug.md" ] && continue
			cls="$(awk '/^gap_class:/ {print $2; exit}' "$stub" | tr -d '"')"
			[ "$cls" = "external" ] && continue
			printf '%s\t%s\n' "$slug" "$cls"
		done
	)
	[ -n "$candidates" ] || {
		echo "no eligible stubs"
		exit 0
	}
	picked=$(printf '%s\n' "$candidates" | fzf --with-nth=1,2 --delimiter=$'\t' --prompt="gap> ")
	SLUG="${picked%%	*}"
fi

[ -n "$SLUG" ] || {
	echo "supply a slug or use --pick" >&2
	exit 2
}

stub="_researching/${SLUG}.md"
[ -f "$stub" ] || {
	echo "no stub at $stub" >&2
	exit 2
}

if [ -f "${SLUG}.md" ]; then
	echo "WARN: ${SLUG}.md already exists at vault root." >&2
	echo "       Continuing — claude will refuse to overwrite unless you confirm." >&2
fi

# Run claude interactively. The system prompt instructs Opus to write
# to .opus-research/<slug>.md and let the wrapper promote.
set +e
claude \
	--model claude-opus-4-7 \
	--permission-mode acceptEdits \
	--append-system-prompt "$(cat "$PROMPT_FILE")" \
	--add-dir "$VAULT" \
	-- \
	"Research the gap at \`_researching/${SLUG}.md\`. Vault root is the current working directory. Stage your output at \`.opus-research/${SLUG}.md\` per the system prompt — do not write at vault root, the wrapper handles promotion. Begin with your synthesis + first question."
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
	echo "claude exited with status $rc — leaving staged file (if any) in place at $STAGING/" >&2
	exit "$rc"
fi

# Promote staged file to vault root.
if [ "$NO_PROMOTE" = "1" ]; then
	echo "[--no-promote] staged file left at $STAGING/${SLUG}.md"
	exit 0
fi

if [ -f "$STAGING/${SLUG}.md" ]; then
	if [ -f "${SLUG}.md" ]; then
		echo "REFUSE: ${SLUG}.md exists at vault root and staged version also exists." >&2
		echo "        Manually resolve: keep one or the other." >&2
		echo "        Staged: $STAGING/${SLUG}.md" >&2
		exit 3
	fi
	mv "$STAGING/${SLUG}.md" "${SLUG}.md"
	echo "promoted to vault root: ${SLUG}.md"
else
	echo "no staged file at $STAGING/${SLUG}.md — claude may have skipped or aborted before writing" >&2
	exit 4
fi
