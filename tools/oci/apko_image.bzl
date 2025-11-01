"apko_image - multi-platform apko OCI images"

load("@aspect_bazel_lib//lib:expand_template.bzl", "expand_template")
load("@aspect_bazel_lib//lib:transitions.bzl", "platform_transition_filegroup")
load("@rules_apko//apko:defs.bzl", _apko_image = "apko_image")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_image_index", "oci_push")
load("//tools/oci:apko_push.bzl", "apko_push")
load("//tools/oci:oci_run.bzl", "oci_run")

def apko_image(
        name,
        config,
        contents,
        repository = None,
        visibility = ["//images:__pkg__"],
        multiplatform_tars = None):
    """Create a multi-platform apko OCI image, optionally with additional tar layers.

    Args:
        name: The name of the image.
        config: The apko config file (should define both x86_64 and aarch64 in archs list).
        contents: The apko contents (lock file).
        repository: The container registry repository (e.g., "ghcr.io/jomcgi/homelab/my-app").
                   Defaults to "ghcr.io/jomcgi/homelab/{package_name}".
        visibility: Visibility of the generated .push target. Defaults to ["//images:__pkg__"]
                   to allow access from the auto-generated //images:push_all multirun.
        multiplatform_tars: Optional list of multiplatform tar dicts from multiplatform_tar().
                           Each dict should have "amd64" and/or "arm64" keys with tar targets.
                           Example: [ttyd_layers, another_layers]

    Creates:
        :{name} - The apko image target (or oci_image_index if multiplatform_tars are provided)
        :{name}.push - Target to push image to registry
        :{name}.run - Target to run image locally (without pushing)

    Example:
        ttyd_layers = multiplatform_tar(
            name = "ttyd_layer",
            amd64 = "@ttyd_amd64//file",
            arm64 = "@ttyd_aarch64//file",
            remap_to = "ttyd",
        )

        apko_image(
            name = "my_image",
            config = "apko.yaml",
            contents = "@apko_lock//:contents",
            multiplatform_tars = [ttyd_layers],
        )

    Notes:
        When multiplatform_tars are provided, separate platform-specific apko images are created
        and layered, then combined into a multi-platform index. This is necessary because apko's
        native multi-platform support doesn't allow adding platform-specific files after the fact.
    """

    # Extract platform-specific tars from the multiplatform_tars dicts
    tars_amd64 = []
    tars_arm64 = []
    if multiplatform_tars:
        for tar_dict in multiplatform_tars:
            if "amd64" in tar_dict:
                tars_amd64.append(tar_dict["amd64"])
            if "arm64" in tar_dict:
                tars_arm64.append(tar_dict["arm64"])

    # If no tars are provided, use the simple multi-platform apko image
    if not tars_amd64 and not tars_arm64:
        _apko_image(
            name = name,
            config = config,
            contents = contents,
            tag = "latest",
        )
        push_image = name
        use_oci_push = False
    else:
        # Create platform-specific base images
        _apko_image(
            name = name + "_base_amd64",
            architecture = "x86_64",
            config = config,
            contents = contents,
            tag = "latest",
        )

        _apko_image(
            name = name + "_base_arm64",
            architecture = "aarch64",
            config = config,
            contents = contents,
            tag = "latest",
        )

        # Use the extracted platform-specific tars

        # Layer tars on top of amd64 base
        oci_image(
            name = name + "_layered_amd64",
            base = ":" + name + "_base_amd64",
            tars = tars_amd64,
        )

        platform_transition_filegroup(
            name = name + "_amd64",
            srcs = [":" + name + "_layered_amd64"],
            target_platform = "@rules_go//go/toolchain:linux_amd64",
        )

        # Layer tars on top of arm64 base
        oci_image(
            name = name + "_layered_arm64",
            base = ":" + name + "_base_arm64",
            tars = tars_arm64,
        )

        platform_transition_filegroup(
            name = name + "_arm64",
            srcs = [":" + name + "_layered_arm64"],
            target_platform = "@rules_go//go/toolchain:linux_arm64",
        )

        # Create multi-platform index
        oci_image_index(
            name = name,
            images = [
                ":" + name + "_amd64",
                ":" + name + "_arm64",
            ],
        )

        push_image = name
        use_oci_push = True

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

    # Push target - uses oci_push when layering tars, apko_push for native apko images
    if use_oci_push:
        oci_push(
            name = name + ".push",
            image = ":" + push_image,
            repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
            remote_tags = select({
                "//tools/oci:ci_build": name + "_stamped_tags_ci",
                "//conditions:default": name + "_stamped_tags_local",
            }),
            visibility = visibility,
        )
    else:
        apko_push(
            name = name + ".push",
            image = push_image,
            repository = repository if repository else "ghcr.io/jomcgi/homelab/" + native.package_name(),
            remote_tags = select({
                "//tools/oci:ci_build": name + "_stamped_tags_ci",
                "//conditions:default": name + "_stamped_tags_local",
            }),
            visibility = visibility,
        )

    # Create .run target for local testing
    oci_run(
        name = name + ".run",
        image = ":" + name,
    )
