#!/usr/bin/env bash
# Validate all apko config files in the repository

set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

echo "Validating apko config files..."

failed=0

# Find all apko config files (including architecture-specific ones, excluding lock files)
find . \( -name "apko.yaml" -o -name "apko-*.yaml" \) \
	-not -path "*/node_modules/*" \
	-not -path "*/.git/*" \
	-not -name "*.lock.json" | while read -r config; do

	echo "  Validating: $config"

	# Validate config using rules_apko
	# show-config will fail if the YAML is invalid
	if ! bazel run @rules_apko//apko -- show-config "$config" >/dev/null 2>&1; then
		echo "  ❌ Validation failed for: $config"
		echo "     Run: bazel run @rules_apko//apko -- show-config $config"
		failed=1
	else
		echo "  ✅ Valid: $config"
	fi
done

if [ $failed -eq 1 ]; then
	echo ""
	echo "❌ apko validation failed - see errors above"
	exit 1
fi

echo "✅ All apko configs are valid"
