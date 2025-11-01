"""oci_run - Create runnable targets for OCI images

This provides a .run target that loads and runs an OCI image using podman/docker,
making it easy to test images locally without pushing to a registry.
"""

def _oci_run_impl(ctx):
    """Implementation of the oci_run rule."""

    # Get the image index or manifest
    image = ctx.attr.image
    image_files = image.files.to_list()

    if not image_files:
        fail("Image target has no files")

    # Create a script that loads and runs the image
    script_content = """#!/usr/bin/env bash
set -euo pipefail

# Detect container runtime
if command -v podman &> /dev/null; then
    RUNTIME="podman"
elif command -v docker &> /dev/null; then
    RUNTIME="docker"
else
    echo "Error: Neither podman nor docker found in PATH" >&2
    exit 1
fi

# Get the image path from Bazel
IMAGE_PATH="$PWD/{image_path}"

# Handle both OCI directory layout and tar archives
if [ -d "$IMAGE_PATH" ]; then
    # OCI directory layout - create a temp tar and load it
    echo "Loading OCI image from $IMAGE_PATH..." >&2
    TEMP_TAR=$(mktemp).tar
    trap "rm -f $TEMP_TAR" EXIT

    # Create tar archive from OCI layout
    tar -cf "$TEMP_TAR" -C "$IMAGE_PATH" .

    # Load the tar
    IMAGE_ID=$($RUNTIME load -i "$TEMP_TAR" | grep -oE 'sha256:[a-f0-9]{{64}}' | head -1)

    if [ -z "$IMAGE_ID" ]; then
        echo "Error: Failed to load image" >&2
        exit 1
    fi

    echo "Loaded image: $IMAGE_ID" >&2
    echo "Running: $RUNTIME run --rm $IMAGE_ID $@" >&2
    exec $RUNTIME run --rm "$IMAGE_ID" "$@"
elif [ -f "$IMAGE_PATH" ]; then
    # Tar archive
    echo "Loading image from $IMAGE_PATH..." >&2
    IMAGE_ID=$($RUNTIME load -i "$IMAGE_PATH" | grep -oE 'sha256:[a-f0-9]{{64}}' | head -1)

    if [ -z "$IMAGE_ID" ]; then
        echo "Error: Failed to load image" >&2
        exit 1
    fi

    echo "Loaded image: $IMAGE_ID" >&2
    echo "Running: $RUNTIME run --rm $IMAGE_ID $@" >&2
    exec $RUNTIME run --rm "$IMAGE_ID" "$@"
else
    echo "Error: Image path does not exist: $IMAGE_PATH" >&2
    exit 1
fi
"""

    # Create the executable script
    script = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.write(
        output = script,
        content = script_content.format(
            image_path = image_files[0].short_path,
        ),
        is_executable = True,
    )

    return [DefaultInfo(
        executable = script,
        runfiles = ctx.runfiles(files = image_files),
    )]

oci_run = rule(
    implementation = _oci_run_impl,
    attrs = {
        "image": attr.label(
            doc = "The OCI image target to run",
            mandatory = True,
            allow_files = True,
        ),
    },
    executable = True,
    doc = """Creates a runnable target for an OCI image.

    Example:
        oci_run(
            name = "my_image_run",
            image = ":my_image",
        )

        # Then run with:
        # bazel run //:my_image_run
        # bazel run //:my_image_run -- bash -c "ls /usr/local/bin"
        # bazel run //:my_image_run -- --entrypoint="" /bin/sh
    """,
)
