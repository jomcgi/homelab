#!/usr/bin/env bash
# validate-recipes.sh — Validates Goose recipe YAML files.
#
# Usage: validate-recipes.sh <recipe.yaml> [<recipe.yaml> ...]
#
# Checks each recipe file for:
#   1. Required top-level fields: title, description
#   2. At least one of: instructions, prompt
#   3. No double-quoted template variables in the prompt field.
#      Using prompt: "{{ var }}" breaks YAML parsing when the task description
#      contains " characters. Use a block scalar (prompt: |-) instead.

set -euo pipefail

FAILED=0

check_recipe() {
	local file="$1"
	local ok=1

	echo "Checking: $file"

	# 1. Required fields
	for field in title description; do
		if ! grep -qE "^${field}:" "$file"; then
			echo "  ERROR: missing required field '${field}'"
			ok=0
		fi
	done

	# 2. Must have at least instructions or prompt
	if ! grep -qE "^(instructions|prompt):" "$file"; then
		echo "  ERROR: missing 'instructions' or 'prompt'"
		ok=0
	fi

	# 3. Detect double-quoted template variable in prompt.
	#    Pattern: a line starting with "prompt:" that contains "{{ anywhere in quotes.
	#    e.g.  prompt: "{{ task_description }}"   <- BROKEN
	#    Fix:  prompt: |-                          <- safe block scalar
	#            {{ task_description }}
	if grep -qE '^prompt:[[:space:]]+"[^"]*\{\{' "$file"; then
		echo "  ERROR: prompt field uses a double-quoted template variable."
		echo "         This produces invalid YAML when the substituted value"
		echo "         contains \" characters (common in task descriptions)."
		echo "         Use a YAML block scalar instead:"
		echo "           prompt: |-"
		echo "             {{ task_description }}"
		ok=0
	fi

	if [ "$ok" -eq 1 ]; then
		echo "  OK"
	else
		FAILED=1
	fi
}

if [ "$#" -eq 0 ]; then
	echo "Usage: $0 <recipe.yaml> [<recipe.yaml> ...]"
	exit 1
fi

for recipe in "$@"; do
	check_recipe "$recipe"
done

if [ "$FAILED" -ne 0 ]; then
	echo ""
	echo "FAIL: one or more recipe files failed validation"
	exit 1
fi

echo ""
echo "PASS: all recipe files valid"
