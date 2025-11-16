#!/usr/bin/env bash
# Detect which OCI image push targets need to be rebuilt based on changed files
# Usage: ./detect-changed-images.sh [base-commit]
#
# Outputs: Space-separated list of Bazel targets that need to be pushed
# Exit code: 0 if targets found, 1 if no changes detected

set -euo pipefail

# Default to comparing against origin/main
BASE_COMMIT="${1:-origin/main}"

# When run via `bazel run`, cd to workspace root
if [[ -n "${BUILD_WORKSPACE_DIRECTORY:-}" ]]; then
    cd "$BUILD_WORKSPACE_DIRECTORY"
fi

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}ℹ${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $*" >&2
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

# Check if we're in a git repository
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    log_error "Not in a git repository"
    exit 1
fi

# Fetch latest to ensure we have up-to-date refs (suppress errors in CI)
log_info "Fetching latest from origin..."
git fetch origin --quiet 2>/dev/null || {
    log_warn "Failed to fetch from origin, using local refs"
}

# Verify base commit exists
if ! git rev-parse --verify "$BASE_COMMIT" >/dev/null 2>&1; then
    log_error "Base commit '$BASE_COMMIT' not found"
    exit 1
fi

# Get list of changed files
log_info "Detecting changed files since $BASE_COMMIT..."
CHANGED_FILES=$(git diff --name-only "$BASE_COMMIT" HEAD || echo "")

if [ -z "$CHANGED_FILES" ]; then
    log_warn "No files changed since $BASE_COMMIT"
    exit 1
fi

log_info "Changed files:"
echo "$CHANGED_FILES" | sed 's/^/  /' >&2

# Extract changed directories (packages)
# For each changed file, get the directory path
CHANGED_PACKAGES=$(echo "$CHANGED_FILES" | sed 's|/[^/]*$||' | sort -u)

log_info "Changed packages:"
echo "$CHANGED_PACKAGES" | sed 's/^/  /' >&2

# Map of image targets to their source packages
# Format: target_label -> package_path
# This is a simple mapping based on known image locations
declare -A IMAGE_PACKAGES
IMAGE_PACKAGES=(
    ["//operators/cloudflare:image.push"]="operators/cloudflare"
    ["//charts/ttyd-session-manager/backend:image.push"]="charts/ttyd-session-manager/backend"
    ["//charts/ttyd-session-manager/backend:ttyd_worker_image.push"]="charts/ttyd-session-manager/backend"
    ["//charts/ttyd-session-manager/frontend:image.push"]="charts/ttyd-session-manager/frontend"
    ["//services/hikes/update_forecast:update_image.push"]="services/hikes/update_forecast"
)

# Detect affected images based on changed packages
AFFECTED_TARGETS=()

for target in "${!IMAGE_PACKAGES[@]}"; do
    package="${IMAGE_PACKAGES[$target]}"

    # Check if any changed file is in this package or its subdirectories
    while IFS= read -r changed_pkg; do
        # Check if changed package is the image package or a parent
        if [[ "$package" == "$changed_pkg"* ]] || [[ "$changed_pkg" == "$package"* ]]; then
            log_info "  ✓ $target affected by changes in $changed_pkg"
            AFFECTED_TARGETS+=("$target")
            break
        fi
    done <<<"$CHANGED_PACKAGES"
done

# Also check for changes in common dependencies
# If MODULE.bazel, REPO.bazel, or tools/oci/* changed, rebuild all images
COMMON_DEPS_CHANGED=false
while IFS= read -r changed_file; do
    case "$changed_file" in
    MODULE.bazel | REPO.bazel | tools/oci/* | .bazelrc | tools/workspace_status.sh)
        log_warn "Common dependency changed: $changed_file"
        COMMON_DEPS_CHANGED=true
        break
        ;;
    esac
done <<<"$CHANGED_FILES"

if [ "$COMMON_DEPS_CHANGED" = true ]; then
    log_warn "Common build dependencies changed, marking all images for rebuild"
    AFFECTED_TARGETS=("${!IMAGE_PACKAGES[@]}")
fi

# Output results
if [ ${#AFFECTED_TARGETS[@]} -eq 0 ]; then
    log_warn "No image targets affected by changes"
    exit 1
fi

# Remove duplicates and sort
UNIQUE_TARGETS=($(printf '%s\n' "${AFFECTED_TARGETS[@]}" | sort -u))

log_info "Affected image targets (${#UNIQUE_TARGETS[@]}):"
printf '%s\n' "${UNIQUE_TARGETS[@]}" | sed 's/^/  /' >&2

# Output space-separated list for CI consumption
printf '%s\n' "${UNIQUE_TARGETS[@]}"
