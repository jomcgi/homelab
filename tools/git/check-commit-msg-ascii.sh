#!/bin/bash
# commit-msg hook: reject non-ASCII characters in commit titles (first line).
#
# Wrangler Pages deployments fail with error 8000111 when the commit *title*
# (first line / subject) contains non-ASCII characters such as smart quotes,
# em-dashes, arrows, or box-drawing characters.  Only the title is checked
# because wrangler reads the subject line from git history; the body is not
# ingested and may contain arbitrary Unicode freely.
#
# Requires only POSIX tools (awk, od, grep) — no Python/Perl/PCRE needed.
# If python3 is available it is used for richer per-character diagnostics.
#
# Usage (commit-msg hook):  check-commit-msg-ascii.sh <commit-msg-file>
# Usage (CI, all commits):  check-commit-msg-ascii.sh --all [base-ref]
#
# Exit 0: all clear
# Exit 1: non-ASCII characters detected in a commit title

set -euo pipefail

# --------------------------------------------------------------------------- #
# has_non_ascii <text>
#   Returns 0 (true) if the string contains any byte > 0x7F, else 1.
# --------------------------------------------------------------------------- #
has_non_ascii() {
	printf '%s' "$1" | od -An -tu1 | tr ' ' '\n' |
		awk '$1+0 >= 128 {found=1} END{exit (found ? 0 : 1)}'
}

# --------------------------------------------------------------------------- #
# bad_lines <text>
#   Prints each line (with its 1-based line number) that contains a byte > 0x7F.
# --------------------------------------------------------------------------- #
bad_lines() {
	printf '%s' "$1" | LC_ALL=C awk '
		BEGIN { found = 0 }
		{
			for (i = 1; i <= length($0); i++) {
				c = substr($0, i, 1)
				if (c > "\177") { print NR ": " $0; found = 1; break }
			}
		}
		END { exit found ? 0 : 1 }
	'
}

# --------------------------------------------------------------------------- #
# explain_chars <text>
#   If python3 is available, prints a character-by-character breakdown of
#   every non-ASCII codepoint found in the text.
# --------------------------------------------------------------------------- #
explain_chars() {
	local text="$1"
	command -v python3 >/dev/null 2>&1 || return 0

	printf '%s' "$text" | python3 - <<-'PYEOF'
		import sys, unicodedata

		HINTS = {
		    '\u2018': "smart left single quote  — use ' instead",
		    '\u2019': "smart right single quote — use ' instead",
		    '\u201c': 'smart left double quote  — use " instead',
		    '\u201d': 'smart right double quote — use " instead',
		    '\u2013': "en-dash  — use - instead",
		    '\u2014': "em-dash  — use -- or - instead",
		    '\u2192': "right arrow — use -> instead",
		    '\u2190': "left arrow  — use <- instead",
		    '\u21d2': "double right arrow — use => instead",
		    '\u2026': "ellipsis — use ... instead",
		    '\u2022': "bullet — use * or - instead",
		    '\u00b7': "middle dot — use . or * instead",
		    '\u00a0': "non-breaking space — use a regular space instead",
		    '\u200b': "zero-width space — remove it",
		}

		text = sys.stdin.read()
		seen = set()
		for c in text:
		    if ord(c) <= 127 or c in seen:
		        continue
		    seen.add(c)
		    cp   = f"U+{ord(c):04X}"
		    name = unicodedata.name(c, "UNKNOWN CHARACTER")
		    hint = HINTS.get(c, "")
		    if hint:
		        print(f"    {cp} ({name}) — {hint}")
		    else:
		        print(f"    {cp} ({name})")
	PYEOF
}

# --------------------------------------------------------------------------- #
# check_message <title> <label>
#   Prints diagnostics and returns 1 if the commit title contains non-ASCII.
# --------------------------------------------------------------------------- #
check_message() {
	local msg="$1"
	local label="${2:-commit title}"

	if ! has_non_ascii "$msg"; then
		return 0
	fi

	echo ""
	echo "ERROR: Non-ASCII characters found in ${label}"
	echo "-------------------------------------------------------"
	echo "Wrangler Pages rejects commits whose title (first line)"
	echo "contains non-ASCII characters (Cloudflare error 8000111)."
	echo ""
	echo "Problematic title:"
	bad_lines "$msg" | sed 's/^/  /'

	local chars_detail
	chars_detail=$(explain_chars "$msg" 2>/dev/null || true)
	if [ -n "$chars_detail" ]; then
		echo ""
		echo "Detected characters:"
		echo "$chars_detail"
	fi

	echo ""
	echo "How to fix — replace non-ASCII characters with ASCII equivalents:"
	echo "  Smart quotes (\u2018\u2019\u201c\u201d) -> ' or \""
	echo "  Em-dash (\u2014)                        -> -- or -"
	echo "  En-dash (\u2013)                        -> -"
	echo "  Arrows (\u2192\u2190\u21d2)             -> -> or <- or =>"
	echo "  Ellipsis (\u2026)                       -> ..."
	echo "  Non-breaking space (\u00a0)             -> (regular space)"
	echo "  Other non-ASCII                         -> remove or rephrase"
	echo ""
	echo "  Tip: many editors silently replace ASCII punctuation with"
	echo "  typographic equivalents. Check your editor's smart-quotes/"
	echo "  autocorrect settings, or use 'git commit -m' directly."
	echo "-------------------------------------------------------"
	return 1
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

if [[ "${1-}" == "--all" ]]; then
	# CI mode: walk every commit between HEAD and base, check each message.
	BASE_REF="${2:-origin/main}"
	FAILED=0

	# Fetch the base ref so it reflects the current upstream state.
	# CI workspaces are often recycled; a stale origin/main makes
	# "BASE_REF..HEAD" walk back into commits that are already on main
	# (e.g. a docs commit merged just before this branch was pushed).
	if [[ "$BASE_REF" == */* ]]; then
		_remote="${BASE_REF%%/*}"
		_branch="${BASE_REF#*/}"
		git fetch "$_remote" "$_branch" 2>/dev/null || true
		unset _remote _branch
	fi

	# Use merge-base so the checked range contains only commits that are
	# unique to this PR.  "BASE_REF..HEAD" alone can stray into commits
	# that have since landed on main when origin/main was stale at fetch
	# time; merge-base pins the lower bound to the actual fork point.
	_merge_base=$(git merge-base HEAD "${BASE_REF}" 2>/dev/null || true)
	_range="${_merge_base:-${BASE_REF}}..HEAD"
	unset _merge_base

	echo "Checking commit titles for non-ASCII characters (commits since ${BASE_REF})..."

	COMMITS=$(git log --format="%H" "$_range")
	unset _range
	if [ -z "$COMMITS" ]; then
		echo "No new commits to check."
		exit 0
	fi

	while IFS= read -r hash; do
		subject=$(git log -1 --format="%s" "$hash")
		short="${hash:0:8}"
		if ! check_message "$subject" "commit ${short} title"; then
			FAILED=1
		fi
	done <<<"$COMMITS"

	if [ "$FAILED" -eq 0 ]; then
		echo "All commit titles contain only ASCII characters."
	fi
	exit "$FAILED"

else
	# commit-msg hook mode: $1 is the path to the commit message file.
	MSG_FILE="${1:-}"
	if [ -z "$MSG_FILE" ] || [ ! -f "$MSG_FILE" ]; then
		echo "Usage: $0 <commit-msg-file>" >&2
		echo "       $0 --all [base-ref]" >&2
		exit 1
	fi

	# Only check the commit title (first non-empty line).
	# The body may contain typographic characters freely — wrangler only
	# reads the subject when recording the deployment in Cloudflare Pages.
	MSG=$(head -1 "$MSG_FILE")
	check_message "$MSG" "commit title"
fi
