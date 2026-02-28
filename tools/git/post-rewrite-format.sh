#!/bin/bash
# Run format after rebase/amend to catch formatting drift.
# Installed via: pre-commit install --hook-type post-rewrite
set -euo pipefail

command="$1" # "rebase" or "amend"

# Only run after rebase (amend already triggers pre-commit)
if [ "$command" != "rebase" ]; then
	exit 0
fi

cd "$(git rev-parse --show-toplevel)"

echo "Running format after rebase..."
if command -v format >/dev/null; then
	format
else
	tools/format/fast-format.sh
fi

if ! git diff --quiet; then
	echo ""
	echo "⚠️  Format found changes after rebase. Stage and amend:"
	echo "   git add -u && git commit --amend --no-edit"
	echo ""
	git diff --stat
fi
