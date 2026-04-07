#!/usr/bin/env bash
# Regenerate atlas.sum when migration SQL files change.
# Requires `atlas` CLI (brew install ariga/tap/atlas).
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

if ! command -v atlas &>/dev/null; then
	echo "SKIP: atlas not installed (brew install ariga/tap/atlas)"
	exit 0
fi

# Find all migration directories containing atlas.sum
while IFS= read -r -d '' sum_file; do
	dir="$(dirname "$sum_file")"
	atlas migrate hash --dir "file://$dir"
done < <(find projects -name atlas.sum -print0)

# Re-stage any changed atlas.sum files
git diff --name-only -- '*/atlas.sum' | xargs -r git add
