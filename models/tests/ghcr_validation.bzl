"""Rules for validating OCI images on GHCR without downloading blobs."""

def _ghcr_validation_test_impl(ctx):
    """Validate GHCR image using crane manifest."""

    # Get crane from attr
    crane = ctx.attr._crane[platform_common.ToolchainInfo]

    # Create test script
    script = ctx.actions.declare_file(ctx.label.name + ".sh")

    # Build the crane path for runfiles
    crane_binary = crane.crane_info.binary

    script_content = """#!/usr/bin/env bash
set -euo pipefail

# Set up runfiles (works in both bazel test and bazel run)
# In Bazel test sandbox, need to detect runfiles directory from script location
if [ -z "${{RUNFILES_DIR:-}}" ]; then
    # Try to find runfiles relative to this script
    if [ -d "${{BASH_SOURCE[0]}}.runfiles" ]; then
        export RUNFILES_DIR="${{BASH_SOURCE[0]}}.runfiles"
    elif [ -d "${{TEST_SRCDIR:-}}" ]; then
        export RUNFILES_DIR="${{TEST_SRCDIR}}"
    fi
fi

# Set manifest file if available
if [ -z "${{RUNFILES_MANIFEST_FILE:-}}" ]; then
    if [ -f "${{BASH_SOURCE[0]}}.runfiles_manifest" ]; then
        export RUNFILES_MANIFEST_FILE="${{BASH_SOURCE[0]}}.runfiles_manifest"
    elif [ -f "${{BASH_SOURCE[0]}}.runfiles/MANIFEST" ]; then
        export RUNFILES_MANIFEST_FILE="${{BASH_SOURCE[0]}}.runfiles/MANIFEST"
    elif [ -f "${{RUNFILES_DIR:-}}/MANIFEST" ]; then
        export RUNFILES_MANIFEST_FILE="${{RUNFILES_DIR}}/MANIFEST"
    fi
fi

# Source runfiles helper
if [ -f "${{RUNFILES_DIR:-/dev/null}}/bazel_tools/tools/bash/runfiles/runfiles.bash" ]; then
    source "${{RUNFILES_DIR}}/bazel_tools/tools/bash/runfiles/runfiles.bash"
elif [ -f "${{RUNFILES_MANIFEST_FILE:-/dev/null}}" ]; then
    # Minimal rlocation implementation for manifest-based runfiles
    rlocation() {{
        grep "^$1 " "${{RUNFILES_MANIFEST_FILE}}" | cut -d' ' -f2-
    }}
else
    echo "ERROR: Cannot find runfiles"
    exit 1
fi

REPOSITORY="{repository}"

# Use crane from Bazel toolchain (set up once, used for discovery and validation)
CRANE="$(rlocation {crane_path})"

# Authenticate if GITHUB_TOKEN is set (do this BEFORE discovery)
if [ -n "${{GITHUB_TOKEN:-}}" ]; then
    echo "${{GITHUB_TOKEN}}" | $CRANE auth login ghcr.io -u token --password-stdin 2>/dev/null || true
fi

# Check for explicit tag via environment variable (CI passes this)
if [ -n "${{GHCR_VALIDATION_TAG:-}}" ]; then
    TAG="${{GHCR_VALIDATION_TAG}}"
    echo "Using tag from GHCR_VALIDATION_TAG environment variable: ${{TAG}}"
else
    # Fallback to tag parameter or discover latest timestamp tag
    TAG="{tag}"

    # If tag is "main" and we're in CI, try to discover the latest timestamp tag
    if [ "${{TAG}}" = "main" ] && [ -n "${{CI:-}}" ]; then
        echo "Discovering latest timestamp tag..."
        DISCOVERED_TAG=$($CRANE ls "ghcr.io/${{REPOSITORY}}" 2>/dev/null | grep -E '^[0-9]{{4}}\\.[0-9]{{2}}\\.[0-9]{{2}}\\.' | sort -r | head -1 || true)

        if [ -n "${{DISCOVERED_TAG}}" ]; then
            TAG="${{DISCOVERED_TAG}}"
            echo "Discovered timestamp tag: ${{TAG}}"
        fi
    fi
fi

IMAGE="ghcr.io/${{REPOSITORY}}:${{TAG}}"

echo "Validating ${{IMAGE}}..."

# Fetch manifest (no blob download)
MANIFEST=$($CRANE manifest "${{IMAGE}}" 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "ERROR: Failed to fetch manifest"
    echo "${{MANIFEST}}"
    exit 1
fi

# Check if it's a multi-platform index (handle JSON with spaces)
MEDIA_TYPE=$(echo "${{MANIFEST}}" | grep -o '"mediaType"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\\([^"]*\\)"$/\\1/')

if [ "${{MEDIA_TYPE}}" = "application/vnd.oci.image.index.v1+json" ]; then
    # Multi-platform image
    PLATFORM_COUNT=$(echo "${{MANIFEST}}" | grep -o '"platform"' | wc -l | tr -d ' ')
    echo "✓ Multi-platform image with ${{PLATFORM_COUNT}} platforms"

    # Check for expected platforms (handle JSON with spaces)
    if echo "${{MANIFEST}}" | grep -q '"os"[[:space:]]*:[[:space:]]*"linux"' && \
       echo "${{MANIFEST}}" | grep -q '"architecture"[[:space:]]*:[[:space:]]*"amd64"'; then
        echo "✓ Found linux/amd64"
    else
        echo "ERROR: linux/amd64 not found"
        exit 1
    fi

    if echo "${{MANIFEST}}" | grep -q '"os"[[:space:]]*:[[:space:]]*"linux"' && \
       echo "${{MANIFEST}}" | grep -q '"architecture"[[:space:]]*:[[:space:]]*"arm64"'; then
        echo "✓ Found linux/arm64"
    else
        echo "ERROR: linux/arm64 not found"
        exit 1
    fi
else
    # Single platform - just validate it has content
    if [ -z "${{MANIFEST}}" ]; then
        echo "ERROR: Empty manifest"
        exit 1
    fi
    echo "✓ Single platform image"
fi

echo "✓ Image validated: ${{REPOSITORY}}:${{TAG}}"
""".format(
        repository = ctx.attr.repository,
        tag = ctx.attr.tag,
        crane_path = crane_binary.short_path.replace("../", ""),
    )

    ctx.actions.write(
        output = script,
        content = script_content,
        is_executable = True,
    )

    # Create runfiles with crane binary and runfiles helper
    runfiles = ctx.runfiles(files = [crane_binary])
    runfiles = runfiles.merge(crane.default.default_runfiles)
    runfiles = runfiles.merge(ctx.attr._runfiles[DefaultInfo].default_runfiles)

    return [DefaultInfo(
        executable = script,
        runfiles = runfiles,
    )]

ghcr_validation_test = rule(
    implementation = _ghcr_validation_test_impl,
    test = True,
    attrs = {
        "repository": attr.string(
            mandatory = True,
            doc = "GHCR repository path (e.g., jomcgi/homelab/models/qwen3_30b_a3b_awq)",
        ),
        "tag": attr.string(
            default = "main",
            doc = "Image tag to validate",
        ),
        "_crane": attr.label(
            default = "@custom_crane_crane_toolchains//:current_toolchain",
            doc = "Crane tool for OCI registry operations",
        ),
        "_runfiles": attr.label(
            default = "@bazel_tools//tools/bash/runfiles",
        ),
    },
)
