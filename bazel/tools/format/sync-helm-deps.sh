#!/usr/bin/env bash
# Sync homelab-library dependency versions across all consuming charts.
#
# Reads the version from projects/shared/helm/homelab-library/chart/Chart.yaml
# and updates any consuming chart whose dependency version doesn't match.
# Rebuilds Chart.lock and charts/*.tgz when a mismatch is found.
#
# Usage:
#   sync-helm-deps.sh          # Check and fix all charts
#   sync-helm-deps.sh --check  # Check only, exit 1 if mismatched
set -euo pipefail

cd "${BUILD_WORKSPACE_DIRECTORY:-$(git rev-parse --show-toplevel)}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}▶${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1" >&2; }

CHECK_ONLY=false
if [[ "${1:-}" == "--check" ]]; then
	CHECK_ONLY=true
fi

LIBRARY_CHART="projects/shared/helm/homelab-library/chart/Chart.yaml"
if [[ ! -f "$LIBRARY_CHART" ]]; then
	exit 0
fi

# Extract library version
LIBRARY_VERSION=$(grep '^version:' "$LIBRARY_CHART" | awk '{print $2}')
if [[ -z "$LIBRARY_VERSION" ]]; then
	err "Could not read version from $LIBRARY_CHART"
	exit 1
fi

# Find all Chart.yaml files that depend on homelab-library (excluding the library itself)
MISMATCHED=()
while IFS= read -r chart_file; do
	[[ "$chart_file" == "$LIBRARY_CHART" ]] && continue

	# Extract the version after "name: homelab-library"
	dep_version=$(awk '/name: homelab-library/{getline; if ($1 == "version:") print $2}' "$chart_file" | tr -d '"')
	if [[ -n "$dep_version" && "$dep_version" != "$LIBRARY_VERSION" ]]; then
		MISMATCHED+=("$chart_file")
	fi
done < <(grep -rl 'name: homelab-library' --include='Chart.yaml' projects/ 2>/dev/null || true)

if [[ ${#MISMATCHED[@]} -eq 0 ]]; then
	exit 0
fi

if $CHECK_ONLY; then
	err "homelab-library is $LIBRARY_VERSION but these charts reference an older version:"
	for f in "${MISMATCHED[@]}"; do
		err "  $f"
	done
	exit 1
fi

log "Syncing homelab-library $LIBRARY_VERSION to ${#MISMATCHED[@]} chart(s)..."

for chart_file in "${MISMATCHED[@]}"; do
	chart_dir=$(dirname "$chart_file")

	# Update the version in Chart.yaml (line after "name: homelab-library")
	sed -i '' "/name: homelab-library/{n;s/version: \"[^\"]*\"/version: \"$LIBRARY_VERSION\"/;}" "$chart_file"

	# Rebuild dependency archive
	if command -v helm &>/dev/null; then
		helm dependency update "$chart_dir" >/dev/null 2>&1 || true
	fi

	log "  Updated $chart_file"
done
