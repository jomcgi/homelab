#!/usr/bin/env bash
# Push OCI images only if their digest differs from the registry
#
# Usage: ./push-if-digest-changed.sh
#
# This script:
# 1. Builds ALL images (Bazel cache makes unchanged builds near-instant)
# 2. For each image, compares its digest with what's in GHCR
# 3. Only pushes images whose digest has changed
#
# This approach is superior to git-based detection because:
# - No manual package mapping needed
# - Bazel's content-addressable builds ensure identical inputs = identical digest
# - Automatically handles transitive dependencies
# - Works for new images automatically

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}ℹ${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $*" >&2
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

log_success() {
    echo -e "${BLUE}✓${NC} $*" >&2
}

log_skip() {
    echo -e "${CYAN}⊘${NC} $*" >&2
}

# Check dependencies
check_deps() {
    local missing=()

    if ! command -v crane &> /dev/null; then
        missing+=("crane")
    fi

    if ! command -v bazel &> /dev/null; then
        missing+=("bazel")
    fi

    if ! command -v jq &> /dev/null; then
        missing+=("jq")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        log_error "Install crane: go install github.com/google/go-containerregistry/cmd/crane@latest"
        log_error "Install jq: apt-get install jq"
        exit 1
    fi
}

# Extract repository from oci_push target
# This queries Bazel for the repository attribute
get_repository() {
    local push_target="$1"

    # Query the push target for its repository attribute
    # oci_push has a 'repository' attribute that specifies the registry repo
    local repo=$(bazel cquery \
        --output=jsonproto \
        "$push_target" 2>/dev/null | \
        jq -r '
            .results[0].target.rule.attribute[] |
            select(.name == "repository") |
            .stringValue
        ' 2>/dev/null || echo "")

    echo "$repo"
}

# Get the current tag from workspace status (STABLE_IMAGE_TAG or STABLE_BRANCH_TAG)
get_current_tag() {
    # Run workspace status script to get the tag
    local tag=$("./tools/workspace_status.sh" 2>/dev/null | grep STABLE_IMAGE_TAG | awk '{print $2}')
    echo "$tag"
}

# Get digest of locally built image
# For multi-platform images (oci_image_index), we get the index digest
get_local_digest() {
    local image_target="$1"

    # The image is already built, get its digest from the bazel-bin output
    # For oci_image_index, there's an index.json with the manifest digest
    local image_path=$(bazel cquery --output=files "$image_target" 2>/dev/null | head -1)

    if [ -z "$image_path" ] || [ ! -e "$image_path" ]; then
        log_warn "Could not find image path for $image_target"
        return 1
    fi

    # The image path is a directory containing the OCI layout
    # Look for index.json or manifest digest
    if [ -f "$image_path/index.json" ]; then
        # Multi-platform index - compute digest of the index
        local digest=$(sha256sum "$image_path/index.json" | awk '{print "sha256:" $1}')
        echo "$digest"
    elif [ -f "$image_path" ]; then
        # Single file - compute its digest
        local digest=$(sha256sum "$image_path" | awk '{print "sha256:" $1}')
        echo "$digest"
    else
        log_warn "Unknown image format at $image_path"
        return 1
    fi
}

# Main logic
main() {
    check_deps

    log_info "Building all images (cached builds are fast)..."

    # Build all images first (uses Bazel cache for unchanged images)
    if ! bazel build //images:push_all --config=ci 2>&1 | grep -E "(Build|FAIL|ERROR)" | head -10 >&2; then
        log_error "Failed to build images"
        exit 1
    fi

    log_success "All images built successfully"
    echo >&2

    # Get all push targets
    ALL_TARGETS=$(bazel query 'kind("oci_push", //...)' --output=label 2>/dev/null)

    if [ -z "$ALL_TARGETS" ]; then
        log_error "No oci_push targets found"
        exit 1
    fi

    TOTAL_COUNT=$(echo "$ALL_TARGETS" | wc -l)
    PUSHED_COUNT=0
    SKIPPED_COUNT=0
    FAILED_COUNT=0

    log_info "Processing $TOTAL_COUNT image(s)..."
    echo >&2

    # Get current tag
    CURRENT_TAG=$(get_current_tag)
    log_info "Current tag: $CURRENT_TAG"
    echo >&2

    # Process each push target
    while IFS= read -r push_target; do
        log_info "Processing: $push_target"

        image_target="${push_target%.push}"

        # Get repository
        repository=$(get_repository "$push_target")
        if [ -z "$repository" ]; then
            log_warn "  Could not determine repository, pushing unconditionally"
            if bazel run --config=ci "$push_target"; then
                log_success "  Pushed (unconditional)"
                ((PUSHED_COUNT++))
            else
                log_error "  Push failed"
                ((FAILED_COUNT++))
            fi
            echo >&2
            continue
        fi

        log_info "  Repository: $repository"

        # Get local digest
        local_digest=$(get_local_digest "$image_target")
        if [ -z "$local_digest" ]; then
            log_warn "  Could not determine local digest, pushing unconditionally"
            if bazel run --config=ci "$push_target"; then
                log_success "  Pushed (unconditional)"
                ((PUSHED_COUNT++))
            else
                log_error "  Push failed"
                ((FAILED_COUNT++))
            fi
            echo >&2
            continue
        fi

        log_info "  Local digest: $local_digest"

        # Check if digest exists in registry
        remote_digest=$(crane digest "$repository:$CURRENT_TAG" 2>/dev/null || echo "")

        if [ -z "$remote_digest" ]; then
            log_info "  Tag not found in registry (new image)"
            log_info "  Pushing..."
            if bazel run --config=ci "$push_target"; then
                log_success "  ✓ Pushed new image"
                ((PUSHED_COUNT++))
            else
                log_error "  ✗ Push failed"
                ((FAILED_COUNT++))
            fi
        elif [ "$local_digest" = "$remote_digest" ]; then
            log_skip "  ⊘ Unchanged (digest matches registry)"
            log_info "    Digest: $local_digest"
            ((SKIPPED_COUNT++))
        else
            log_info "  Remote digest: $remote_digest"
            log_info "  Digest changed, pushing..."
            if bazel run --config=ci "$push_target"; then
                log_success "  ✓ Pushed updated image"
                ((PUSHED_COUNT++))
            else
                log_error "  ✗ Push failed"
                ((FAILED_COUNT++))
            fi
        fi

        echo >&2
    done <<<"$ALL_TARGETS"

    # Summary
    log_info "═══════════════════════════════════════"
    log_success "Pushed: $PUSHED_COUNT image(s)"
    log_skip "Skipped: $SKIPPED_COUNT image(s) (unchanged)"
    if [ $FAILED_COUNT -gt 0 ]; then
        log_error "Failed: $FAILED_COUNT image(s)"
        exit 1
    fi

    exit 0
}

main "$@"
