"apko_image - multi-platform apko OCI images"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@rules_apko//apko:defs.bzl", _apko_image = "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_image_index", "oci_push")

def apko_image(name, config, contents, repository = None, visibility = ["//images:__pkg__"], multi_platform = True):
    """Create a multi-platform apko OCI image.

    Args:
        name: The name of the image.
        config: The apko config file (should define both x86_64 and aarch64 in archs list).
        contents: The apko contents (lock file).
        repository: The container registry repository (e.g., "ghcr.io/jomcgi/homelab/my-app").
                   Defaults to "ghcr.io/jomcgi/homelab/{package_name}".
        visibility: Visibility of the generated .push target. Defaults to ["//images:__pkg__"]
                   to allow access from the auto-generated //images:push_all multirun.
        multi_platform: Build for both amd64 and arm64. Defaults to True.
                       If True, requires separate config files: {config}-amd64.yaml and {config}-arm64.yaml

    Creates:
        :{name} - The oci_image_index target (for multi-platform)
        :{name}_amd64 - AMD64-specific image (if multi_platform=True)
        :{name}_arm64 - ARM64-specific image (if multi_platform=True)
        :{name}.push - Target to push image to registry
    """
    if multi_platform:
        # Extract base config name (remove .yaml if present)
        config_base = config.replace(".yaml", "")

        # Build AMD64 image
        _apko_image(
            name = name + "_amd64",
            config = config_base + "-amd64.yaml",
            contents = contents,
            tag = "latest",
        )

        # Build ARM64 image
        _apko_image(
            name = name + "_arm64",
            config = config_base + "-arm64.yaml",
            contents = contents,
            tag = "latest",
        )

        # Create multi-platform index
        oci_image_index(
            name = name,
            images = [
                name + "_amd64",
                name + "_arm64",
            ],
        )
    else:
        # Single platform build (legacy)
        _apko_image(
            name = name,
            config = config,
            contents = contents,
            tag = "latest",
        )

    # Create stamped tags file for CI builds (branch + timestamp)
    expand_template(
        name = name + "_stamped_tags_ci",
        out = name + "_stamped_ci.tags.txt",
        template = [
            "{STABLE_BRANCH_TAG}",
            "{STABLE_IMAGE_TAG}",
        ],
        stamp_substitutions = {
            "{STABLE_BRANCH_TAG}": "{{STABLE_BRANCH_TAG}}",
            "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
        },
    )

    # Create stamped tags file for local builds (timestamp only)
    expand_template(
        name = name + "_stamped_tags_local",
        out = name + "_stamped_local.tags.txt",
        template = [
            "{STABLE_IMAGE_TAG}",
        ],
        stamp_substitutions = {
            "{STABLE_IMAGE_TAG}": "{{STABLE_IMAGE_TAG}}",
        },
    )

    # Push uses the index for multi-platform, or base image for single platform
    oci_push(
        name = name + ".push",
        image = name,
        repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
        remote_tags = select({
            "//tools/oci:ci_build": name + "_stamped_tags_ci",
            "//conditions:default": name + "_stamped_tags_local",
        }),
        visibility = visibility,
    )
