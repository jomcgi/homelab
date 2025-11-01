"apko_image - multi-platform apko OCI images"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@rules_apko//apko:defs.bzl", _apko_image = "apko_image")
load("//tools/oci:apko_push.bzl", "apko_push")

def apko_image(name, config, contents, repository = None, visibility = ["//images:__pkg__"]):
    """Create a multi-platform apko OCI image.

    Args:
        name: The name of the image.
        config: The apko config file (should define both x86_64 and aarch64 in archs list).
        contents: The apko contents (lock file).
        repository: The container registry repository (e.g., "ghcr.io/jomcgi/homelab/my-app").
                   Defaults to "ghcr.io/jomcgi/homelab/{package_name}".
        visibility: Visibility of the generated .push target. Defaults to ["//images:__pkg__"]
                   to allow access from the auto-generated //images:push_all multirun.

    Creates:
        :{name} - The apko image target
        :{name}.push - Target to push image to registry
    """
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

    # Push target - uses apko_push for proper multi-platform support
    apko_push(
        name = name + ".push",
        image = name,
        repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
        remote_tags = select({
            "//tools/oci:ci_build": name + "_stamped_tags_ci",
            "//conditions:default": name + "_stamped_tags_local",
        }),
        visibility = visibility,
    )
