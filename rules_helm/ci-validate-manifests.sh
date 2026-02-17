#!/usr/bin/env bash
# rules_helm/ci-validate-manifests.sh
# CI validation script to ensure pre-rendered manifests are up to date

set -euo pipefail

echo "🔍 Validating that all pre-rendered manifests are up to date..."
echo ""

# Get the repo root
# When run via Bazel, use BUILD_WORKSPACE_DIRECTORY
REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"
cd "$REPO_ROOT"

# Find all BUILD files with render_manifests target
APPS_WITH_MANIFESTS=()

while IFS= read -r build_file; do
	if grep -q "name = \"render_manifests\"" "$build_file"; then
		overlay_dir=$(dirname "$build_file")
		overlay_package=$(echo "$overlay_dir" | sed "s|^$REPO_ROOT/||" | sed 's|^./||')
		APPS_WITH_MANIFESTS+=("$overlay_package")
	fi
done < <(find overlays -name BUILD -type f)

# If no apps have manifest generation enabled, exit
if [ ${#APPS_WITH_MANIFESTS[@]} -eq 0 ]; then
	echo "✅ No applications using pre-rendered manifests"
	exit 0
fi

echo "📦 Found ${#APPS_WITH_MANIFESTS[@]} application(s) with pre-rendered manifests:"
for app in "${APPS_WITH_MANIFESTS[@]}"; do
	echo "   - $app"
done
echo ""

# Track validation results
VALIDATION_FAILED=false
FAILED_APPS=()

# Validate each app
for app in "${APPS_WITH_MANIFESTS[@]}"; do
	manifest_file="$app/manifests/all.yaml"

	# Check if manifest file exists
	if [ ! -f "$manifest_file" ]; then
		echo "❌ $app: manifest file missing ($manifest_file)"
		echo "   Run: bazel run //$app:render_manifests"
		VALIDATION_FAILED=true
		FAILED_APPS+=("$app")
		continue
	fi

	# Save current manifests
	temp_file=$(mktemp)
	cp "$manifest_file" "$temp_file"

	# Re-render manifests
	echo "🔨 Rendering: $app"
	if ! bazel run "//$app:render_manifests" >/dev/null 2>&1; then
		echo "   ❌ Failed to render manifests"
		rm "$temp_file"
		VALIDATION_FAILED=true
		FAILED_APPS+=("$app")
		continue
	fi

	# Compare with saved version
	if ! diff -q "$temp_file" "$manifest_file" >/dev/null 2>&1; then
		echo "   ❌ Manifests are out of date!"
		echo ""
		echo "   Diff:"
		diff -u "$temp_file" "$manifest_file" | head -50 || true
		echo ""
		echo "   To fix, run: bazel run //$app:render_manifests"
		rm "$temp_file"
		VALIDATION_FAILED=true
		FAILED_APPS+=("$app")
	else
		echo "   ✅ Manifests are up to date"
		rm "$temp_file"
	fi
	echo ""
done

# Report results
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$VALIDATION_FAILED" = true ]; then
	echo "❌ Validation failed for ${#FAILED_APPS[@]} application(s):"
	for app in "${FAILED_APPS[@]}"; do
		echo "   - $app"
	done
	echo ""
	echo "Fix by running:"
	for app in "${FAILED_APPS[@]}"; do
		echo "   bazel run //$app:render_manifests"
	done
	echo ""
	echo "Or enable pre-commit hooks to auto-render:"
	echo "   pre-commit install"
	exit 1
else
	echo "✅ All pre-rendered manifests are up to date!"
	exit 0
fi
