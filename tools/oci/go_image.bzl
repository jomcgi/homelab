"go_image macro for OCI containers"

load("@aspect_bazel_lib//lib:tar.bzl", "tar")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load", "oci_push")

def go_image(name, binary, base = "@distroless_base", repository = None):
    """Create a Go OCI image from a Go binary.

    Args:
        name: The name of the image.
        binary: The Go binary target to package.
        base: The base image to use. Defaults to distroless base.
        repository: The container registry repository (e.g., "ghcr.io/jomcgi/homelab/my-app").
                   Defaults to "ghcr.io/jomcgi/homelab/{package_name}".

    Creates:
        :{name} - The oci_image target
        :{name}_platform - Platform-specific image filegroup
        :{name}.load - Target to load image into local Docker
        :{name}.push - Target to push image to registry
    """
    tar(
        name = name + "_app_layer",
        srcs = [binary],
        mtree = [
            "./opt/app type=file content=$(execpath {})".format(binary),
        ],
    )
    oci_image(
        name = name,
        base = base,
        tars = [
            name + "_app_layer",
        ],
        entrypoint = [
            "/opt/app",
        ],
    )
    platform_transition_filegroup(
        name = name + "_platform",
        srcs = [name],
        target_platform = select({
            "@platforms//cpu:arm64": "@rules_go//go/toolchain:linux_arm64",
            "@platforms//cpu:x86_64": "@rules_go//go/toolchain:linux_amd64",
        }),
    )
    oci_load(
        name = name + ".load",
        image = name + "_platform",
        repo_tags = [
            native.package_name() + ":latest",
        ],
    )
    oci_push(
        name = name + ".push",
        image = name + "_platform",
        repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
        remote_tags = [
            "{STABLE_BRANCH_TAG}",  # Branch name (e.g., "main", "feature-xyz")
            "{STABLE_IMAGE_TAG}",  # Timestamp: YYYY.MM.DD.HH.MM.SS-shortsha
        ],
    )
