#!/usr/bin/env bash
# rules_helm/pre-commit-render-manifests.sh
# Pre-commit hook to auto-render Helm manifests for ArgoCD applications

set -euo pipefail

echo "🔍 Checking for applications that need manifest rendering..."

# Get the repo root
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Find all BUILD files with argocd_generate_manifests directive
APPS_TO_RENDER=()

# Get all changed files from git
CHANGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR)

# Check if any application.yaml, values.yaml, or Chart.yaml files changed
if echo "$CHANGED_FILES" | grep -qE '(application\.yaml|values\.yaml|Chart\.yaml)'; then
	echo "📝 Detected changes to Helm charts or values files"

	# Find all overlays with render_manifests target
	while IFS= read -r build_file; do
		if grep -q "name = \"render_manifests\"" "$build_file"; then
			# Extract the package path from the BUILD file location
			overlay_dir=$(dirname "$build_file")
			overlay_package=$(echo "$overlay_dir" | sed "s|^$REPO_ROOT/||" | sed 's|^./||')

			# Check if this overlay or its chart was affected by changes
			affected=false

			# Get the application.yaml to find the chart path
			app_file="$overlay_dir/application.yaml"
			if [ -f "$app_file" ]; then
				# Extract chart path from application.yaml
				chart_path=$(grep "path:" "$app_file" | head -1 | awk '{print $2}' | tr -d '"')

				# Check if any changed file affects this overlay
				for changed in $CHANGED_FILES; do
					if [[ "$changed" == "$overlay_package"* ]] || [[ "$changed" == "$chart_path"* ]]; then
						affected=true
						break
					fi
				done
			fi

			if [ "$affected" = true ]; then
				APPS_TO_RENDER+=("$overlay_package")
				echo "   ✓ $overlay_package needs re-rendering"
			fi
		fi
	done < <(find overlays -name BUILD -type f)
fi

# If no apps need rendering, exit
if [ ${#APPS_TO_RENDER[@]} -eq 0 ]; then
	echo "✅ No manifest rendering needed"
	exit 0
fi

echo ""
echo "📦 Rendering manifests for ${#APPS_TO_RENDER[@]} application(s)..."
echo ""

# Render manifests for each affected app
for app in "${APPS_TO_RENDER[@]}"; do
	echo "🔨 Rendering: $app"

	# Run bazel to render manifests
	if bazel run "//$app:render_manifests" 2>&1 | grep -E '(Rendering Helm|Manifests written|Total resources)'; then
		# Stage the generated manifests
		manifest_file="$app/manifests/all.yaml"
		if [ -f "$manifest_file" ]; then
			git add "$manifest_file"
			echo "   ✅ Staged $manifest_file"
		fi
	else
		echo "   ❌ Failed to render $app"
		exit 1
	fi
	echo ""
done

echo "✅ All manifests rendered and staged successfully!"
