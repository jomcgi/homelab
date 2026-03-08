#!/usr/bin/env bash
# rules_helm/render-all-manifests.sh
# Render manifests for all applications with render_manifests target

set -euo pipefail

# Get the repository root
REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"
cd "$REPO_ROOT"

echo "🔨 Rendering manifests for all applications..."
echo ""

# Find all packages with render_manifests target
PACKAGES=()
while IFS= read -r build_file; do
	if grep -q 'name = "render_manifests"' "$build_file"; then
		pkg_dir=$(dirname "$build_file")
		pkg=$(echo "$pkg_dir" | sed 's|^./||')
		PACKAGES+=("$pkg")
	fi
done < <(find overlays -name BUILD -type f)

if [ ${#PACKAGES[@]} -eq 0 ]; then
	echo "✅ No applications with pre-rendered manifests"
	exit 0
fi

echo "📦 Found ${#PACKAGES[@]} application(s) to render"
echo ""

# Render all in parallel using xargs
printf '%s\n' "${PACKAGES[@]}" | xargs -P 10 -I {} bash -c '
    pkg="{}"
    echo "  🔨 $pkg"
    bazel run "//$pkg:render_manifests" 2>&1 | grep -E "(Error|warning)" || true
'

echo ""
echo "✅ All manifests rendered!"
