#!/usr/bin/env bash
# Auto-generate the ADR sidebar entries for the VitePress docs site.
# Scans docs/decisions/*/*.md and produces adr-sidebar.json imported by config.js.
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

OUTPUT_FILE="projects/websites/docs.jomcgi.dev/.vitepress/adr-sidebar.json"
DECISIONS_DIR="docs/decisions"

# Extract a display title from an ADR markdown file.
# Strips common prefixes (ADR NNN:, RFC:, #) and trims whitespace.
extract_title() {
	local file="$1"
	local heading
	heading=$(head -1 "$file" | sed -E 's/^#+ *//')

	# Strip "ADR NNN: ", "RFC: ", "ADR: " prefixes
	heading=$(echo "$heading" | sed -E 's/^(ADR|RFC)[[:space:]]*[0-9]*:?[[:space:]]*//')

	echo "$heading"
}

# Collect categories (subdirectories with numbered .md files)
CATEGORIES=()
for dir in "$DECISIONS_DIR"/*/; do
	[ -d "$dir" ] || continue
	category=$(basename "$dir")
	if compgen -G "$dir[0-9]*.md" >/dev/null 2>&1; then
		CATEGORIES+=("$category")
	fi
done

IFS=$'\n' CATEGORIES=($(printf '%s\n' "${CATEGORIES[@]}" | LC_ALL=C sort))
unset IFS

if [ ${#CATEGORIES[@]} -eq 0 ]; then
	echo "No ADR categories found"
	echo "[]" >"$OUTPUT_FILE"
	exit 0
fi

# Build JSON array of category objects, each with nested items.
# Collect items into arrays first, then emit valid JSON.
json="["
cat_sep=""
for category in "${CATEGORIES[@]}"; do
	# Capitalize first letter (portable — no GNU \U needed)
	display_name="$(echo "${category:0:1}" | tr '[:lower:]' '[:upper:]')${category:1}"

	items=""
	item_sep=""
	for file in "$DECISIONS_DIR/$category"/[0-9]*.md; do
		[ -f "$file" ] || continue
		basename_noext=$(basename "$file" .md)
		number=$(echo "$basename_noext" | grep -oE '^[0-9]+')
		title=$(extract_title "$file")
		link="/docs/decisions/$category/$basename_noext"

		items="${items}${item_sep}{\"text\":\"${number} - ${title}\",\"link\":\"${link}\"}"
		item_sep=","
	done

	json="${json}${cat_sep}{\"text\":\"${display_name}\",\"collapsed\":true,\"items\":[${items}]}"
	cat_sep=","
done
json="${json}]"

# Write compact JSON — prettier will format it on the next format run
echo "$json" >"$OUTPUT_FILE"
